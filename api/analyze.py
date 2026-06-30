from fastapi import APIRouter, HTTPException
from services.market_data_service import get_stock_data
from engines.strategy_engine import StrategyEngine

router = APIRouter(
    prefix="/api",
    tags=["Analysis"]
)

@router.get("/analyze/{symbol}")
def analyze_stock(symbol: str):
    """
    Analyze a stock using market data and trading strategy.
    
    Parameters:
    - symbol (str): Stock ticker symbol
    
    Returns:
    - dict: Analysis results containing:
        - symbol: Normalized symbol
        - market: Market data
        - strategy: Dictionary with score and signal
    """
    try:
        # Get market data
        market = get_stock_data(symbol)
        if not market:
            raise HTTPException(status_code=404, detail="Market data not found")
            
        # Initialize strategy engine with specified strategy file
        strategy_engine = StrategyEngine("strategies/AJ_Strategy_V1.json")
        
        # Calculate strategy score based on market data
        score = strategy_engine.calculate_score({
            "price": market.get("price", 0),
            "volume": market.get("volume", 0),
            "volume_ratio": market.get("volume_ratio", 0)
        })
        
        # Generate trading signal
        signal = strategy_engine.generate_signal(score)
        
        # Return formatted response
        return {
            "symbol": symbol.upper(),
            "market": market,
            "strategy": {
                "score": score,
                "signal": signal
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))