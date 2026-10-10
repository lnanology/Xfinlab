# Validation gates (internal, but public by design)

Rule: do not add features until the gate before them passes. Each gate has a stop condition.

## Gate 1 - Is the problem real? (weeks 1-2)
Talk to 10 developers or quant researchers (people building financial AI agents, backtests, or data pipelines).
Ask only: what do you use today; which step wastes the most time; how do you solve it; would you pay, and how much?
Record answers in a table: name/handle, role, tool used, pain, willing-to-pay (yes/no/amount).
Pass: 5+ describe the same pain unprompted. Stop/adjust: no repeated pain.

## Gate 2 - Do they come back? (weeks 3-6)
Measure weekly (from API usage logs; no personal data beyond the key hash):
- new keys; keys with 2+ distinct days of use in a week (repeat use); keys that hit the daily cap.
Pass: repeat-use keys grow week over week. Stop/adjust: users try once and leave.

## Gate 3 - Will they pay? (weeks 7-12)
Offer a paid option to 5+ repeat users (higher quota, validation reports, PIT access).
Pass: 3+ say yes at a stated price. Stop/adjust: nobody asks for pricing.

## Metrics sheet (fill weekly)
| week | new keys | repeat-use keys | cap-hit keys | interviews done | pricing questions | paying |
|---|---|---|---|---|---|---|

Targets here are experiment goals, not industry benchmarks or revenue promises.
