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
  6. File integrity      -- fetches the live static files (index.html
     + the JS files most worth tampering with) and byte-compares them
     against this repo's own git-tracked copies at HEAD. Unlike check
     #4 (which only catches KNOWN malware patterns), this catches ANY
     unauthorized change at all -- the real "did someone actually get
     in and modify the live deploy outside of git" check. www.xfinlab.com
     is a static deploy of this exact repo (api.xfinlab.com is the
     separate backend service), so at rest they should always match
     byte-for-byte; a mismatch means either a legitimate deploy lag
     (the live site hasn't picked up the latest push yet) or real
     tampering -- this tool can't tell the difference automatically,
     it just flags a mismatch for you to look at.

Usage:
    python3 scripts/security_scan.py [--url https://www.xfinlab.com]

Exits 0 always (this is a reporting tool, not a CI gate) -- the report
itself flags anything that needs attention.

2026-07-23 (task #326): the actual check logic now lives in
services/security_scan_service.py as structured, importable functions
(each returns a dict instead of just printing), so the exact same
checks also power (a) an in-process APScheduler job that runs every 6
hours directly on the live Railway server and persists results into
the shared xfinlab.db, and (b) a "Run Scan Now" button + results view
in admin.html, with a one-click "Copy Report" so a human can hand the
whole thing to an AI assistant for remediation without re-running
anything by hand. This script is now just a thin CLI wrapper that
prints the same report to the terminal for the external scheduled
task that already calls it.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.security_scan_service import DEFAULT_URL, run_and_save


def main():
    parser = argparse.ArgumentParser(description="XFINLAB periodic security watch")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--repo-root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument("--no-save", action="store_true", help="Print only, don't persist to xfinlab.db")
    args = parser.parse_args()

    print(f"XFINLAB Security Watch -- target: {args.url}")

    if args.no_save:
        from services.security_scan_service import run_full_scan
        result = run_full_scan(base_url=args.url, repo_root=args.repo_root)
    else:
        result = run_and_save(base_url=args.url, repo_root=args.repo_root)

    print(result["report_text"])
    print("=== Done ===")


if __name__ == "__main__":
    main()

# --- Setup note for GOOGLE_SAFE_BROWSING_API_KEY (free) ---
# 1. https://console.cloud.google.com/ -> create/select a project.
# 2. Enable the "Safe Browsing API".
# 3. Credentials -> Create Credentials -> API key.
# 4. Set it as an env var wherever this script runs:
#      export GOOGLE_SAFE_BROWSING_API_KEY=your_key_here
