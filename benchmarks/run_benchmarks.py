"""Integrity benchmarks for the XFINLAB MCP endpoint.
pip install requests ; XFINLAB_API_KEY=xfl_... python run_benchmarks.py"""
import json, os, sys, time, datetime, pathlib, requests

URL = os.environ.get("XFINLAB_MCP_URL", "https://api.xfinlab.com/api/mcp")
KEY = os.environ["XFINLAB_API_KEY"]
HERE = pathlib.Path(__file__).parent
REQUIRED = {"schema", "tool", "retrieved_at", "data_as_of", "sources", "method_version",
            "data_status", "limitations", "not_investment_advice"}


def call(tool, args):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}
    t0 = time.time()
    r = requests.post(URL, json=body, headers={"X-API-Key": KEY}, timeout=60)
    return r.json(), round((time.time() - t0) * 1000)


def main():
    cases = json.load(open(HERE / "cases.json"))["cases"]
    out, failed = [], 0
    for c in cases:
        res, ms = call(c["tool"], c["arguments"])
        result = res.get("result", {})
        problems = []
        if result.get("isError"):
            status = "tool_error"
            text = result["content"][0]["text"] if result.get("content") else ""
            # An explicit error is acceptable behaviour for bad input; record it.
            ok = True
            detail = text[:160]
        else:
            payload = json.loads(result["content"][0]["text"])
            e = payload.get("evidence")
            if not e:
                problems.append("missing evidence block")
                status = None
            else:
                missing = REQUIRED - set(e)
                if missing:
                    problems.append(f"missing fields: {sorted(missing)}")
                status = e.get("data_status")
                if status not in c["expect_status"]:
                    problems.append(f"unexpected status {status}")
                if e.get("data_as_of") is None and not e.get("data_as_of_note"):
                    problems.append("data_as_of null without note")
            ok, detail = not problems, "; ".join(problems)
        failed += 0 if ok else 1
        out.append({"id": c["id"], "tool": c["tool"], "ok": ok, "status": status,
                    "latency_ms": ms, "detail": detail})
        print(("PASS " if ok else "FAIL ") + c["id"], status, f"{ms}ms", detail)

    stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"{stamp}.json").write_text(json.dumps({"run_at": stamp, "results": out}, indent=2))
    print(f"{len(out) - failed}/{len(out)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
