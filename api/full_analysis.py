from fastapi import APIRouter

from services.market_data_service import get_stock_data
from engines.strategy_engine import StrategyEngine
from engines.event_engine import EventEngine

router = APIRouter()

strategy_engine = StrategyEngine(
    "strategies/AJ_Strategy_V1.json"
)

event_engine = EventEngine()


@router.get("/full-analysis/{symbol}")
def full_analysis(symbol: str):

    market = get_stock_data(symbol)

    score = strategy_engine.calculate_score(
        {
            "price": market["price"],
            "volume": market["volume"],
            "volume_ratio": market["volume_ratio"]
        }
    )

    signal = strategy_engine.generate_signal(score)

    event = event_engine.analyze_event(
        "unusual_volume"
        if market["volume_ratio"] > 2
        else "earnings"
    )

    final_score = round(
        (
            score
            + event["event_score"]
            + (100 - event["risk_score"])
        ) / 3
    )

    recommendation = (
        "BUY"
        if final_score >= 70
        else "HOLD"
        if final_score >= 40
        else "SELL"
    )

    return {
        "symbol": symbol.upper(),

        "market": market,

        "strategy": {
            "score": score,
            "signal": signal
        },

        "event": event,

        "final_score": final_score,

        "recommendation": recommendation
    }