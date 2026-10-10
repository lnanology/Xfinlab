# XFINLAB benchmarks

Reproducible checks of the public API/MCP. Run it yourself:

```
XFINLAB_API_KEY=xfl_... python run_benchmarks.py
```

Each run appends a dated result file to `results/`. Failures are kept, not deleted.

## What is measured today (integrity, not accuracy)
1. Every successful response has an `evidence` block with the required fields.
2. Nonsense or empty requests return `insufficient_evidence` or an error, never a confident answer.
3. `data_as_of` is either a real timestamp or `null` with a note (never invented).
4. Latency per tool.

## Not measured yet (will be added here before any claim is made)
- Signal accuracy and confidence calibration (needs a pre-registered, append-only signal log).
- Point-in-time correctness of fundamentals (see `PIT_PILOT.md`).

Cases live in `cases.json` so anyone can add one by pull request.
