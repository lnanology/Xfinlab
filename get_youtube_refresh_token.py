#!/usr/bin/env python3
"""
get_youtube_refresh_token.py -- ONE-TIME, LOCAL-ONLY script to obtain the
GOOGLE_YT_REFRESH_TOKEN that services/youtube_upload_service.py needs
(alongside GOOGLE_YT_CLIENT_ID / GOOGLE_YT_CLIENT_SECRET) before the Video
Engine's "upload to YouTube" feature can actually upload anything. See that
module's docstring for the full picture -- this script only produces the
one missing credential.

Deliberately plain `requests` + stdlib (http.server/webbrowser/threading),
no google-auth-oauthlib / google-api-python-client -- matches
youtube_upload_service.py's own "REST-only, no new SDK dependency"
convention, so this repo doesn't gain a new heavy dependency just to run
a script once and throw it away.

--------------------------------------------------------------------------
PREREQUISITES (do these once, manually, at https://console.cloud.google.com
-- nothing here can shortcut this part, it has to be done under AJ's own
Google identity):

  1. Create (or reuse) a Google Cloud project.

  2. Enable the "YouTube Data API v3" for that project:
     APIs & Services -> Library -> search "YouTube Data API v3" -> Enable.

  3. Configure the OAuth consent screen:
     APIs & Services -> OAuth consent screen
     - User type: External
     - Add the Google account that owns/manages XFINLAB's YouTube channel
       as a Test user, under "Test users". IMPORTANT: while the app stays
       in "Testing" publishing status (the default), only test users can
       complete this flow, AND refresh tokens issued this way expire after
       7 days of *inactivity* (Google's policy for unverified apps
       requesting the sensitive youtube.upload scope). If uploads that
       used to work start failing after a quiet period, that's why --
       either re-run this script for a fresh token, or (permanent fix)
       submit the app for Google's verification review and publish it to
       Production.

  4. Create OAuth client credentials:
     APIs & Services -> Credentials -> Create Credentials -> OAuth client ID
     - Application type: "Desktop app" -- NOT "Web application". Desktop-
       app clients are allowed to use the 127.0.0.1 loopback redirect this
       script relies on without pre-registering an exact redirect URI (Web
       application clients require every redirect URI to be pre-registered
       in the console, which this script's dynamic local port can't do).
     - Note the Client ID and Client Secret Google shows you.

--------------------------------------------------------------------------
USAGE:

    pip install requests   # already in requirements.txt if running inside
                            # this repo's venv -- only needed standalone
    python3 get_youtube_refresh_token.py

Run this ON THE SAME MACHINE as the browser you'll approve access from --
it opens a browser tab and starts a temporary local web server on
127.0.0.1 to catch Google's redirect. This talks only to Google's OAuth
endpoints and your own local machine; it never touches XFINLAB's
production servers.

At the end it prints the 3 environment variables to paste into Railway's
Variables tab (Settings -> Variables on the app.xfinlab.com service).
Keep them secret -- anyone with all 3 can upload videos to the channel.
"""

import http.server
import sys
import threading
import urllib.parse
import webbrowser

import requests

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/youtube.upload"
PORT = 8912  # arbitrary local port -- loopback only, never exposed publicly

_result = {}


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Catches Google's OAuth redirect (http://127.0.0.1:PORT/?code=...)
    just long enough to grab the one query param this script needs, then
    shows the user a plain "you can close this tab" page."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _result["code"] = params["code"][0]
            body = b"<html><body><h2>Done -- you can close this tab and return to the terminal.</h2></body></html>"
        else:
            _result["error"] = params.get("error", ["unknown_error"])[0]
            body = b"<html><body><h2>Something went wrong -- check the terminal for details.</h2></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # keep the terminal clean -- this script prints its own status lines


def main():
    print("XFINLAB -- YouTube refresh token generator (run this once, locally)\n")
    print("You'll need the Client ID and Client Secret from the Google Cloud")
    print("Console step in this script's docstring (Desktop app OAuth client).\n")

    client_id = input("Paste your OAuth Client ID: ").strip()
    client_secret = input("Paste your OAuth Client Secret: ").strip()
    if not client_id or not client_secret:
        print("\nBoth Client ID and Client Secret are required. Aborting.")
        sys.exit(1)

    redirect_uri = f"http://127.0.0.1:{PORT}"

    auth_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",  # required -- without this, Google never
                                    # issues a refresh_token, only a short-
                                    # lived access_token
        "prompt": "consent",       # forces a fresh refresh_token even if
                                    # this Google account already approved
                                    # this exact app once before (Google
                                    # otherwise silently skips re-issuing one)
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(auth_params)}"

    server = http.server.HTTPServer(("127.0.0.1", PORT), _CallbackHandler)
    # handle_request() serves exactly one request then returns -- no need
    # for a full serve_forever() loop or manual shutdown bookkeeping.
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    print(f"\nOpening your browser to approve access. If it doesn't open automatically, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for you to approve access in the browser (3 minute timeout)...")
    server_thread.join(timeout=180)

    if "error" in _result:
        print(f"\nGoogle returned an error: {_result['error']}")
        print(
            "Common cause: your Google account isn't added as a Test user "
            "on the OAuth consent screen yet (see step 3 in this script's "
            "docstring)."
        )
        sys.exit(1)

    code = _result.get("code")
    if not code:
        print("\nTimed out waiting for authorization. Run the script again.")
        sys.exit(1)

    print("Authorization code received. Exchanging it for a refresh token...")

    token_resp = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )

    if token_resp.status_code != 200:
        print(f"\nToken exchange failed ({token_resp.status_code}): {token_resp.text}")
        sys.exit(1)

    tokens = token_resp.json()
    refresh_token = tokens.get("refresh_token")

    if not refresh_token:
        print(
            "\nGoogle did not return a refresh_token this time. This usually "
            "means this Google account already granted this exact app access "
            "before, in a way 'prompt=consent' didn't override server-side. "
            "Go to https://myaccount.google.com/permissions, find and remove "
            "this app's access, then run this script again."
        )
        sys.exit(1)

    print("\n" + "=" * 66)
    print("SUCCESS. Set these 3 variables in Railway (Variables tab):")
    print("=" * 66)
    print(f"GOOGLE_YT_CLIENT_ID={client_id}")
    print(f"GOOGLE_YT_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_YT_REFRESH_TOKEN={refresh_token}")
    print("=" * 66)
    print(
        "\nKeep these secret -- anyone with all 3 can upload videos to your "
        "YouTube channel. Do not commit them to git or paste them anywhere "
        "public. Once set, also flip the 'video_engine' feature flag on in "
        "admin.html and either set upload_to_youtube=true per-call or wire "
        "a cron -- see services/youtube_upload_service.py's docstring."
    )


if __name__ == "__main__":
    main()
