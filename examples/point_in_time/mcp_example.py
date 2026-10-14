"""Call the get_fundamentals_as_of MCP tool over plain JSON-RPC.

    pip install requests
    XFINLAB_API_KEY=xfl_... python mcp_example.py AAPL 2023-06-30

MCP clients (Claude Desktop etc.) do the same thing for you; see
https://www.xfinlab.com/intelligence-api.html#mcp for the connection config.
"""
import json
import os
import sys

import requests

URL = "https://api.xfinlab.com/api/mcp"


def rpc(key, method, params=None, id_=1):
    r = requests.post(URL, json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}},
                      headers={"X-API-Key": key}, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    key = os.environ.get("XFINLAB_API_KEY") or sys.exit("Set XFINLAB_API_KEY")
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    as_of = sys.argv[2] if len(sys.argv) > 2 else "2023-06-30"

    names = [t["name"] for t in rpc(key, "tools/list")["result"]["tools"]]
    print("tools:", names)

    res = rpc(key, "tools/call", {"name": "get_fundamentals_as_of",
                                   "arguments": {"symbol": symbol, "as_of": as_of}})["result"]
    payload = json.loads(res["content"][0]["text"])
    print("isError:", res["isError"])
    print(json.dumps(payload, indent=2)[:3000])


if __name__ == "__main__":
    main()
