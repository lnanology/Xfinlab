"""
2026-07-19 Stage 3 roadmap rewrite ("歷史事件蒙地卡羅模擬"): this endpoint
used to build a prompt asking an LLM to "estimate" a loss percentage and
recovery time for a hardcoded historical-scenario description -- a
number the model invented with zero grounding in actual price data, a
real violation of this codebase's "never fabricate a number" principle.

By the time this was found, stress-lab.html had already stopped calling
this endpoint (see that file's own 2026-07-11 inline comment) in favor
of a transparent, clearly-labelled client-side calculation using assumed
per-strategy drawdown profiles -- so this dead code wasn't actually
reaching any live user. Rather than just delete it, it's rewritten here
to do something genuinely real: a Monte Carlo bootstrap simulation over
a symbol's own real historical daily returns (services/
monte_carlo_service.py), wired back into stress-lab.html as a new,
complementary section alongside its existing historical-scenario cards.
"""

from fastapi import APIRouter
from services.monte_carlo_service import simulate

router = APIRouter()


@router.post("/stress-lab")
async def stress_lab(body: dict):
    symbol = body.get("symbol", "")
    amount = body.get("amount", 100000)
    horizon_days = body.get("horizon_days", 252)

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 100000

    try:
        horizon_days = int(horizon_days)
    except (TypeError, ValueError):
        horizon_days = 252

    result = simulate(symbol, amount=amount, horizon_days=horizon_days)
    return {"status": "ok", "data": result}
