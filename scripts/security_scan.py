#!/usr/bin/env python3
"""
XFINLAB Security Watch -- periodic "is the live site infected / does it
have known holes" check, run on a schedule (see the accompanying
scheduled task, every 6 hours) rather than as a live-attached WAF.

This is deliberately NOT real-time attack blocking (that needs a real
WAF like Cloudflare/Sucuri in front of the site) -- it's a recurring
after-the-fact health check covering the checks a small team can
realistically automate for free:

  1. Security headers   -- fetches the live site, checks for the
     standard hardening headers (HSTS/CSP/X-Frame-Options/etc).
  2. SSL certificate     -- connects directly, reports days until
     expiry and the negotiated TLS version.
  3. Dependency CVEs     -- runs pip-audit against requirements.txt,
     flags any known-vulnerable package version.
  4. Suspicious content  -- fetches the live homepage/key pages and
     greps for classic malware-injection patterns (obfuscated eval,
     hidden iframes, script tags pointing at unknown domains) that
     wouldn't be there unless someone tampered with the live deploy
     out-of-band from git.
  5. Malicious-site flag -- optional, only runs if GOOGLE_SAFE_BROWSING_
     API_KEY is set in the environment (free key from Google Cloud
     Console -- see README note at the bottom of this file). Checks
     whether Google has the domain flagged as unsafe.

Usage:
    python3 scripts/security_scan.py [--url https://www.xfinlab.com]

Exits 0 always (this is a reporting tool, not a CI gate) -- the report
itself flags anything that needs attention.
"""
import argparse
import json
import os
import re
import ssl
import socket
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

# Known-good script/iframe source domains -- anything outside this list
# found in a <script src="..."> or <iframe src="..."> on the live site
# is flagged for manual review (could be a legit new addition, could be
# an injected malicious include -- this tool can't tell the difference,
# it just surfaces it).
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
    print("\n=== 1. Security Headers ===")
    if requests is None:
        print("  SKIP: `requests` not installed.")
        return
    try:
        res = requests.get(base_url, timeout=15)
    except Exception as e:
        print(f"  ERROR: could not fetch {base_url}: {e}")
        return
    headers_lower = {k.lower(): v for k, v in res.headers.items()}
    any_missing = False
    for h, why in REQUIRED_HEADERS.items():
        if h in headers_lower:
            print(f"  OK   {h}: {headers_lower[h][:80]}")
        else:
            any_missing = True
            print(f"  MISSING  {h} -- {why}")
    if not any_missing:
        print("  All standard hardening headers present.")


def check_ssl(base_url):
    print("\n=== 2. SSL Certificate ===")
    host = urlparse(base_url).netloc or base_url
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                version = ssock.version()
        not_after = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days_left = (not_after - datetime.now(timezone.utc)).days
        print(f"  TLS version negotiated: {version}")
        print(f"  Certificate expires: {not_after.date()} ({days_left} days left)")
        if days_left < 14:
            print(f"  WARNING: certificate expires soon ({days_left} days) -- renew now")
        if version in ("TLSv1", "TLSv1.1"):
            print(f"  WARNING: outdated TLS version negotiated ({version})")
    except Exception as e:
        print(f"  ERROR: could not check SSL for {host}: {e}")


def check_dependencies(repo_root):
    print("\n=== 3. Dependency CVE Scan (pip-audit) ===")
    req_path = os.path.join(repo_root, "requirements.txt")
    if not os.path.exists(req_path):
        print(f"  SKIP: no requirements.txt found at {req_path}")
        return
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "-r", req_path, "-f", "json"],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode not in (0, 1):
            print(f"  ERROR running pip-audit: {result.stderr[:500]}")
            return
        data = json.loads(result.stdout or "[]")
        # pip-audit's JSON shape varies by version: either a top-level
        # list of {name, version, vulns:[...]} or {"dependencies": [...]}
        deps = data.get("dependencies", data) if isinstance(data, dict) else data
        found = False
        for dep in deps:
            vulns = dep.get("vulns") or []
            if vulns:
                found = True
                print(f"  VULNERABLE  {dep.get('name')} {dep.get('version')}:")
                for v in vulns:
                    print(f"      {v.get('id')} -- fixed in {v.get('fix_versions')}")
        if not found:
            print("  No known CVEs found in requirements.txt.")
    except FileNotFoundError:
        print("  SKIP: pip-audit not installed. Install with: pip install pip-audit --break-system-packages")
    except Exception as e:
        print(f"  ERROR: {e}")


def check_suspicious_content(base_url):
    print("\n=== 4. Suspicious Content / Injected Script Scan ===")
    if requests is None:
        print("  SKIP: `requests` not installed.")
        return
    any_flag = False
    for page in PAGES_TO_SCAN:
        url = base_url.rstrip("/") + page
        try:
            res = requests.get(url, timeout=15)
            html = res.text
        except Exception as e:
            print(f"  ERROR fetching {url}: {e}")
            continue

        for pattern, why in SUSPICIOUS_PATTERNS:
            if re.search(pattern, html, re.IGNORECASE):
                any_flag = True
                print(f"  FLAG  {page}: {why}")

        external_domains = _extract_external_srcs(html)
        unknown = [d for d in external_domains if not any(d == a or d.endswith("." + a) for a in ALLOWED_EXTERNAL_DOMAINS)]
        if unknown:
            any_flag = True
            print(f"  FLAG  {page}: unrecognized external script/iframe domain(s): {', '.join(unknown)}")

    if not any_flag:
        print(f"  No suspicious patterns or unknown external domains found across {len(PAGES_TO_SCAN)} pages.")


def check_safe_browsing(base_url):
    print("\n=== 5. Malicious-Site Flag Check (Google Safe Browsing) ===")
    api_key = os.getenv("GOOGLE_SAFE_BROWSING_API_KEY")
    if not api_key:
        print("  SKIP: GOOGLE_SAFE_BROWSING_API_KEY not set.")
        print("  Get a free key: https://developers.google.com/safe-browsing/v4/get-started")
        return
    if requests is None:
        print("  SKIP: `requests` not installed.")
        return
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
            print(f"  ALERT: Google Safe Browsing has flagged this URL: {data['matches']}")
        else:
            print("  Clean -- not flagged by Google Safe Browsing.")
    except Exception as e:
        print(f"  ERROR: {e}")


def main():
    parser = argparse.ArgumentParser(description="XFINLAB periodic security watch")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--repo-root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = parser.parse_args()

    print(f"XFINLAB Security Watch -- {datetime.now(timezone.utc).isoformat()}")
    print(f"Target: {args.url}")

    check_headers(args.url)
    check_ssl(args.url)
    check_dependencies(args.repo_root)
    check_suspicious_content(args.url)
    check_safe_browsing(args.url)

    print("\n=== Done ===")


if __name__ == "__main__":
    main()

# --- Setup note for GOOGLE_SAFE_BROWSING_API_KEY (free) ---
# 1. https://console.cloud.google.com/ -> create/select a project.
# 2. Enable the "Safe Browsing API".
# 3. Credentials -> Create Credentials -> API key.
# 4. Set it as an env var wherever this script runs:
#      export GOOGLE_SAFE_BROWSING_API_KEY=your_key_here
