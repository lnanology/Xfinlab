"""Integrity benchmarks for the XFINLAB MCP endpoint.
pip install requests ; XFINLAB_API_KEY=xfl_... python run_benchmarks.py"""
import getpass, json, os, sys, time, datetime, pathlib, requests

URL = os.environ.get("XFINLAB_MCP_URL", "https://api.xfinlab.com/api/mcp")
KEY = os.environ.get("XFINLAB_API_KEY") or getpass.getpass("Paste your XFINLAB API key (hidden): ").strip()
if not KEY:
    sys.exit("No API key given.")
if KEY.startswith("xf1_"):  # digit one -> letter L (easy to mistype)
    KEY = "xfl_" + KEY[4:]
    print("note: corrected prefix xf1_ -> xfl_")
print(f"key check: prefix={KEY[:4]!r} length={len(KEY)} (a valid key is 47 characters starting with xfl_)")
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
        try:
            res, ms = call(c["tool"], c["arguments"])
        except requests.RequestException as e:
            failed += 1
            out.append({"id": c["id"], "tool": c["tool"], "ok": False, "status": None,
                        "latency_ms": None, "detail": f"request failed: {type(e).__name__}"})
            print("FAIL", c["id"], f"request failed: {type(e).__name__}")
            continue
        result = res.get("result", {})
        problems = []
        if result.get("isError"):
            status = "tool_error"
            text = result["content"][0]["text"] if result.get("content") else ""
            detail = text[:160]
            low = text.lower()
            # Auth/quota/config errors mean the case was NOT actually tested.
            not_tested = any(k in low for k in ("missing credentials", "invalid", "quota", "unauthor", "temporarily unavailable", "internal error"))
            ok = not not_tested
            if not_tested:
                detail = "NOT TESTED (auth/quota/server error): " + detail
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

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"{stamp}.json").write_text(json.dumps({"run_at": stamp, "results": out}, indent=2))
    print(f"{len(out) - failed}/{len(out)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
