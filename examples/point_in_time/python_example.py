"""First Point-in-Time request in a few minutes.

    pip install requests
    XFINLAB_API_KEY=xfl_... python python_example.py AAPL 2023-06-30

Prints exactly what the API returns for "what was knowable about <ticker> on
<date>": the figures, the period each one describes (data_time), when it became
public (publication_time), what is unavailable, and the limitations.
Nothing is simulated: if the API has no data, you see its error.
"""
import json
import os
import sys

import requests

BASE = "https://api.xfinlab.com/api/intelligence/v1"


def main():
    key = os.environ.get("XFINLAB_API_KEY")
    if not key:
        sys.exit("Set XFINLAB_API_KEY (free key: https://www.xfinlab.com/intelligence-api.html)")
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    as_of = sys.argv[2] if len(sys.argv) > 2 else "2023-06-30"

    r = requests.get(f"{BASE}/fundamentals/{ticker}/as-of", params={"as_of_date": as_of},
                     headers={"X-API-Key": key}, timeout=30)
    body = r.json()
    if not body.get("success"):
        # standard envelope: {"success": false, "data": null, "meta": {...}, "error": "..."}
        print(f"HTTP {r.status_code}: {body.get('error')}  (code: {body.get('meta', {}).get('error_code')})")
        return
    data = body["data"]
    print(f"{data['ticker']} as of {data['as_of_date']}")
    for name, f in data["facts"].items():
        print(f"  {name:20s} {f['value']:>18,.2f} {f['unit']:<10s} "
              f"period_end={f['data_time']}  filed={f['publication_time']}  available_at={f['available_at']}")
    print("unavailable:", data.get("unavailable_fields"))
    print(json.dumps(data.get("quality"), indent=2))
    # Provenance: keep these with your research result to reproduce it later.
    ev = data.get("evidence") or {}
    print("research_id:", data.get("research_id"), "| source:", (data.get("source") or {}).get("source"),
          "| newest filing used:", ev.get("data_as_of"), "| status:", ev.get("data_status"))


if __name__ == "__main__":
    main()
