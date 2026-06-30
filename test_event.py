"""
XFINLAB Event Intelligence V1
Test Script - Event Analysis Pipeline
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engines.event_engine import EventEngine


def print_analysis(result: dict):
    print("=" * 50)
    print(f"  Event Type     : {result['event_type'].upper()}")
    print(f"  Symbol         : {result['symbol']}")
    print("-" * 50)
    print(f"  Historical Cases : {result['historical_cases']}")
    print(f"  Avg Change 1D    : {result['avg_reaction']['avg_1d']:+.2f}%")
    print(f"  Avg Change 7D    : {result['avg_reaction']['avg_7d']:+.2f}%")
    print(f"  Avg Change 30D   : {result['avg_reaction']['avg_30d']:+.2f}%")
    print(f"  Success Rate     : {result['success_rate']}%")
    print(f"  Market Impact    : {result['market_impact_score']} / 100")
    print("=" * 50)


if __name__ == "__main__":
    engine = EventEngine()

    print("\n🧪 TEST 1: Earnings Events (All Symbols)")
    result = engine.analyze("earnings")
    print_analysis(result)

    print("\n🧪 TEST 2: Regulation Events (All Symbols)")
    result = engine.analyze("regulation")
    print_analysis(result)

    print("\n🧪 TEST 3: Merger Events (All Symbols)")
    result = engine.analyze("merger")
    print_analysis(result)

    print("\n🧪 TEST 4: Abnormal Volume Events")
    result = engine.analyze("abnormal_volume")
    print_analysis(result)

    print("\n🧪 TEST 5: Major News Events")
    result = engine.analyze("major_news")
    print_analysis(result)

    print("\n🧪 TEST 6: AAPL Earnings Only")
    result = engine.analyze("earnings", symbol="AAPL")
    print_analysis(result)
