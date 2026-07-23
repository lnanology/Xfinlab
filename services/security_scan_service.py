"""
Structured, importable core of the XFINLAB security watch (task #326).

scripts/security_scan.py originally did everything as print()-only side
effects, so its findings only ever existed in whatever terminal ran it --
there was no way to see the latest result from the admin panel, and no
way to hand a report to an AI assistant for remediation without manually
re-running the script and copy-pasting terminal output.

This module is the single source of truth for the actual checks (moved
here from scripts/security_scan.py, which now just calls into this
module and prints the result for CLI/cron use). Each check_* function
returns a plain JSON-serializable dict instead of printing, so the same
checks can power: (1) the CLI script, (2) an in-process APScheduler job
running every 6 hours directly on the live Railway server (writing
results into the same Litestream-backed xfinlab.db every other periodic
job already uses), and (3) an admin-triggered "run now" button.
"""
import json
import os
import re
import socket
import sqlite3
import ssl
import subprocess
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

try:
    import requests
except Exception:
    requests = None

DEFAULT_URL = "https://www.xfinlab.com"
PAGES_TO_SCAN = ["/", "/dashboard.html", "/login.html", "/pricing.html"]

INTEGRITY_FILES = [
    "index.html", "login.html", "dashboard.html",
    "js/autocomplete.js", "js/i18n.js", "js/theme-toggle.js",
    "js/nav.js", "js/share-widget.js",
]

ALLOWED_EXTERNAL_DOMAINS = [
    "fonts.googleapis.com", "fonts.gstatic.com",
    "cdnjs.cloudflare.com", "cdn.jsdelivr.net",
    "www.googletagmanager.com", "www.google-analytics.com",
    "t.me", "api.qrserver.com",
    "xfinlab.com", "www.xfinlab.com", "api.xfinlab.com",
]

SUSPICIOUS_PATTERNS = [
    (r"eval\s*\(\s*atob\s*\(", "obfuscated eval(atob(...)) -- classic malware-injection pattern"),
    (r"document\.write\s*\(\s*unescape\s*\(", "document.write(unescape(...)) -- classic obfuscated injection"),
    (r"fromCharCode\s*\([^)]{80,}\)", "very long String.fromCharCode(...) chain -- often obfuscated payload"),
    (r"<iframe[^>]+style=[\"'][^\"']*display\s*:\s*none", "hidden iframe (display:none) -- common malware/spam-injection technique"),
    (r"<iframe[^>]+style=[\"'][^\"']*(width|height)\s*:\s*0", "zero-size iframe -- common malware/spam-injection technique"),
]

REQUIRED_HEADERS = {
    "strict-transport-security": "HSTS missing -- browsers won't be forced to use HTTPS on repeat visits",
    "x-content-type-options": "X-Content-Type-Options missing -- allows MIME-sniffing attacks",
    "x-frame-options": "X-Frame-Options missing -- page can be framed/clickjacked by other sites (unless CSP frame-ancestors covers it)",
    "content-security-policy": "Content-Security-Policy missing -- no defense-in-depth against injected scripts",
}

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _extract_external_srcs(html):
    srcs = re.findall(r'(?:src|href)=["\']((?:https?:)?//[^"\']+)["\']', html)
    domains = set()
    for s in srcs:
        s = s if s.startswith("http") else "https:" + s
        try:
            domains.add(urlparse(s).netloc)
        except Exception:
            pass
    return domains


def check_headers(base_url):
    out = {"name": "Security Headers", "ok": True, "findings": []}
    if requests is None:
        out["ok"] = None
        out["findings"].append({"level": "skip", "message": "`requests` not installed."})
        return out
    try:
        res = requests.get(base_url, timeout=15)
    except Exception as e:
        out["ok"] = None
        out["findings"].append({"level": "error", "message": f"could not fetch {base_url}: {e}"})
        return out
    headers_lower = {k.lower(): v for k, v in res.headers.items()}
    for h, why in REQUIRED_HEADERS.items():
        if h in headers_lower:
            out["findings"].append({"level": "ok", "message": f"{h}: {headers_lower[h][:80]}"})
        else:
            out["ok"] = False
            out["findings"].append({"level": "missing", "message": f"{h} -- {why}"})
    return out


def check_ssl(base_url):
    out = {"name": "SSL Certificate", "ok": True, "findings": []}
    host = urlparse(base_url).netloc or base_url
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                version = ssock.version()
        not_after = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days_left = (not_after - datetime.now(timezone.utc)).days
        out["findings"].append({"level": "ok", "message": f"TLS version negotiated: {version}"})
        out["findings"].append({"level": "ok", "message": f"Certificate expires: {not_after.date()} ({days_left} days left)"})
        if days_left < 14:
            out["ok"] = False
            out["findings"].append({"level": "warning", "message": f"certificate expires soon ({days_left} days) -- renew now"})
        if version in ("TLSv1", "TLSv1.1"):
            out["ok"] = False
            out["findings"].append({"level": "warning", "message": f"outdated TLS version negotiated ({version})"})
    except Exception as e:
        out["ok"] = None
        out["findings"].append({"level": "error", "message": f"could not check SSL for {host}: {e}"})
    return out


def check_dependencies(repo_root, timeout=60):
    out = {"name": "Dependency CVE Scan (pip-audit)", "ok": True, "findings": []}
    req_path = os.path.join(repo_root, "requirements.txt")
    if not os.path.exists(req_path):
        out["ok"] = None
        out["findings"].append({"level": "skip", "message": f"no requirements.txt found at {req_path}"})
        return out
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "-r", req_path, "-f", "json"],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode not in (0, 1):
            out["ok"] = None
            out["findings"].append({"level": "error", "message": f"running pip-audit: {result.stderr[:500]}"})
            return out
        data = json.loads(result.stdout or "[]")
        deps = data.get("dependencies", data) if isinstance(data, dict) else data
        for dep in deps:
            vulns = dep.get("vulns") or []
            if vulns:
                out["ok"] = False
                for v in vulns:
                    out["findings"].append({
                        "level": "vulnerable",
                        "message": f"{dep.get('name')} {dep.get('version')}: {v.get('id')} -- fixed in {v.get('fix_versions')}",
                    })
        if out["ok"]:
            out["findings"].append({"level": "ok", "message": "No known CVEs found in requirements.txt."})
    except FileNotFoundError:
        out["ok"] = None
        out["findings"].append({"level": "skip", "message": "pip-audit not installed. Install with: pip install pip-audit --break-system-packages"})
    except subprocess.TimeoutExpired:
        out["ok"] = None
        out["findings"].append({"level": "skip", "message": f"pip-audit timed out after {timeout}s -- skipped this run"})
    except Exception as e:
        out["ok"] = None
        out["findings"].append({"level": "error", "message": str(e)})
    return out


def check_suspicious_content(base_url):
    out = {"name": "Suspicious Content / Injected Script Scan", "ok": True, "findings": []}
    if requests is None:
        out["ok"] = None
        out["findings"].append({"level": "skip", "message": "`requests` not installed."})
        return out
    for page in PAGES_TO_SCAN:
        url = base_url.rstrip("/") + page
        try:
            res = requests.get(url, timeout=15)
            html = res.text
        except Exception as e:
            out["findings"].append({"level": "error", "message": f"fetching {url}: {e}"})
            continue

        for pattern, why in SUSPICIOUS_PATTERNS:
            if re.search(pattern, html, re.IGNORECASE):
                out["ok"] = False
                out["findings"].append({"level": "flag", "message": f"{page}: {why}"})

        external_domains = _extract_external_srcs(html)
        unknown = [d for d in external_domains if not any(d == a or d.endswith("." + a) for a in ALLOWED_EXTERNAL_DOMAINS)]
        if unknown:
            out["ok"] = False
            out["findings"].append({"level": "flag", "message": f"{page}: unrecognized external script/iframe domain(s): {', '.join(unknown)}"})

    if out["ok"]:
        out["findings"].append({"level": "ok", "message": f"No suspicious patterns or unknown external domains found across {len(PAGES_TO_SCAN)} pages."})
    return out


def check_safe_browsing(base_url):
    out = {"name": "Malicious-Site Flag Check (Google Safe Browsing)", "ok": True, "findings": []}
    api_key = os.getenv("GOOGLE_SAFE_BROWSING_API_KEY")
    if not api_key:
        out["ok"] = None
        out["findings"].append({"level": "skip", "message": "GOOGLE_SAFE_BROWSING_API_KEY not set. Get a free key: https://developers.google.com/safe-browsing/v4/get-started"})
        return out
    if requests is None:
        out["ok"] = None
        out["findings"].append({"level": "skip", "message": "`requests` not installed."})
        return out
    try:
        payload = {
            "client": {"clientId": "xfinlab-security-watch", "clientVersion": "1.0"},
            "threatInfo": {
                "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
                "platformTypes": ["ANY_PLATFORM"],
                "threatEntryTypes": ["URL"],
                "threatEntries": [{"url": base_url}],
            },
        }
        res = requests.post(
            f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={api_key}",
            json=payload, timeout=15,
        )
        data = res.json()
        if data.get("matches"):
            out["ok"] = False
            out["findings"].append({"level": "alert", "message": f"Google Safe Browsing has flagged this URL: {data['matches']}"})
        else:
            out["findings"].append({"level": "ok", "message": "Clean -- not flagged by Google Safe Browsing."})
    except Exception as e:
        out["ok"] = None
        out["findings"].append({"level": "error", "message": str(e)})
    return out


def check_file_integrity(base_url, repo_root):
    out = {"name": "File Integrity Check (live site vs. git HEAD)", "ok": True, "findings": []}
    if requests is None:
        out["ok"] = None
        out["findings"].append({"level": "skip", "message": "`requests` not installed."})
        return out

    checked_count = 0
    for rel_path in INTEGRITY_FILES:
        local_path = os.path.join(repo_root, rel_path)
        if not os.path.exists(local_path):
            out["findings"].append({"level": "skip", "message": f"{rel_path}: not found in local repo copy"})
            continue

        with open(local_path, "rb") as f:
            local_bytes = f.read()

        url = base_url.rstrip("/") + "/" + rel_path
        try:
            res = requests.get(url, timeout=15)
            live_bytes = res.content
        except Exception as e:
            out["findings"].append({"level": "error", "message": f"fetching {url}: {e}"})
            continue

        checked_count += 1
        if live_bytes == local_bytes:
            out["findings"].append({"level": "ok", "message": f"{rel_path}: matches git HEAD exactly"})
        else:
            out["ok"] = False
            size_delta = len(live_bytes) - len(local_bytes)
            msg = f"{rel_path}: live version differs from git HEAD (size delta: {size_delta:+d} bytes)"
            try:
                live_lines = live_bytes.decode("utf-8", errors="replace").splitlines()
                local_lines = local_bytes.decode("utf-8", errors="replace").splitlines()
                for i, (a, b) in enumerate(zip(live_lines, local_lines)):
                    if a != b:
                        msg += f" | first differing line ({i + 1}): repo={b[:100]!r} live={a[:100]!r}"
                        break
                else:
                    if len(live_lines) != len(local_lines):
                        msg += f" | line count differs: repo={len(local_lines)} live={len(live_lines)}"
            except Exception:
                pass
            out["findings"].append({"level": "flag", "message": msg})

    if checked_count == 0:
        out["ok"] = None
        out["findings"].append({"level": "skip", "message": f"Could not fetch any of the {len(INTEGRITY_FILES)} files to compare -- integrity NOT verified this run."})
    elif out["ok"]:
        out["findings"].append({"level": "ok", "message": f"All {checked_count}/{len(INTEGRITY_FILES)} successfully-fetched files match git HEAD exactly."})
    else:
        out["findings"].append({"level": "note", "message": "A mismatch can also just mean the live deploy hasn't picked up the latest git push yet -- check deploy timestamps before assuming tampering."})
    return out


def render_report_text(result):
    """Plain-text rendering of a full scan result -- this is exactly what
    the admin panel's "Copy Report" button copies, so a human can paste
    the whole thing straight into an AI assistant for remediation."""
    lines = [
        f"XFINLAB Security Watch -- {result['timestamp']}",
        f"Target: {result['target']}",
        f"Overall: {'ISSUES FOUND' if result['any_flags'] else 'CLEAN'}",
        "",
    ]
    for i, check in enumerate(result["checks"], 1):
        lines.append(f"=== {i}. {check['name']} ===")
        for f in check["findings"]:
            lines.append(f"  [{f['level'].upper()}] {f['message']}")
        lines.append("")
    return "\n".join(lines)


def run_full_scan(base_url=DEFAULT_URL, repo_root=None, skip_dependency_scan=False):
    if repo_root is None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    checks = [
        check_headers(base_url),
        check_ssl(base_url),
    ]
    if not skip_dependency_scan:
        checks.append(check_dependencies(repo_root))
    checks.append(check_suspicious_content(base_url))
    checks.append(check_safe_browsing(base_url))
    checks.append(check_file_integrity(base_url, repo_root))

    any_flags = any(c["ok"] is False for c in checks)
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target": base_url,
        "any_flags": any_flags,
        "checks": checks,
    }
    result["report_text"] = render_report_text(result)
    return result


# --- Persistence (xfinlab.db, same Litestream-backed DB every other
# periodic job in this codebase already uses) --------------------------

def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table():
    conn = _get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS security_scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            target TEXT NOT NULL,
            any_flags INTEGER NOT NULL,
            result_json TEXT NOT NULL
        )"""
    )
    conn.commit()
    conn.close()


def save_scan_result(result):
    """Best-effort: a DB write failure here should never crash the
    caller (a background cron job or an admin-triggered scan) -- the
    scan itself already ran and its findings matter more than whether
    this particular run got persisted."""
    try:
        _ensure_table()
        conn = _get_db()
        conn.execute(
            "INSERT INTO security_scan_runs (created_at, target, any_flags, result_json) VALUES (?, ?, ?, ?)",
            (result["timestamp"], result["target"], 1 if result["any_flags"] else 0, json.dumps(result)),
        )
        # keep only the most recent 50 runs so this table can't grow unbounded
        conn.execute(
            "DELETE FROM security_scan_runs WHERE id NOT IN (SELECT id FROM security_scan_runs ORDER BY id DESC LIMIT 50)"
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_latest_scan_result():
    try:
        _ensure_table()
        conn = _get_db()
        row = conn.execute(
            "SELECT result_json, created_at FROM security_scan_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            return None
        return json.loads(row["result_json"])
    except Exception:
        return None


def get_scan_history(limit=10):
    try:
        _ensure_table()
        conn = _get_db()
        rows = conn.execute(
            "SELECT created_at, target, any_flags FROM security_scan_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [{"created_at": r["created_at"], "target": r["target"], "any_flags": bool(r["any_flags"])} for r in rows]
    except Exception:
        return []


def run_and_save(base_url=DEFAULT_URL, repo_root=None, skip_dependency_scan=False):
    result = run_full_scan(base_url=base_url, repo_root=repo_root, skip_dependency_scan=skip_dependency_scan)
    save_scan_result(result)
    return result
