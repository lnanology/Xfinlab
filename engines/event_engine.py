class EventEngine:
    """
    Event Risk Engine

    2026-07-23 note (platform audit finding): this class used to also
    expose find_similar_events()/analyze()/calculate_average_reaction()/
    calculate_success_rate() methods (still referenced by
    tests/test_suite.py's TestEventEngine, which has been failing on
    AttributeError since whenever this got refactored down to just
    analyze_event() below -- nobody had fixed or removed those tests
    until this audit found them).

    Deliberately NOT restoring those methods on top of what they used to
    read from (database/event_history.py + database/event_history.sql):
    that SQL file's own comment says "Sample Data" and its price_before/
    price_after_1d/7d/30d rows are hand-made placeholder numbers (e.g.
    AAPL '2024-01-25' 100.0 -> 108.0 -> 112.0 -> 120.0), not real recorded
    market history. Reviving "find similar historical earnings events and
    their average reaction" against that table would present fabricated
    numbers as real historical fact -- the exact anti-pattern already
    fixed elsewhere this session (feature_engine.py's fake volatility,
    stress-lab.html's fabricated loss/recovery figures, the fabricated-
    output MasterPipeline modules). api/pipeline_api.py already reaches
    this same conclusion independently (see its event_risk=50 comment:
    "event_history table only has historical patterns, not wired up as a
    real-time feed").

    A genuine version of this feature needs a real dataset: actual
    historical earnings/CEO-change/regulation dates per symbol cross-
    referenced with real price bars from MarketDataService/Alpaca around
    each date. That's a real, separate data-engineering project, not a
    quick restore -- flagged to the user rather than faked. The 5
    corresponding tests in tests/test_suite.py are marked skip with this
    same reasoning instead of being silently deleted.

    analyze_event() below is unrelated and unaffected: it returns a fixed
    per-category risk/event/market-impact estimate (not a claim about any
    specific historical instance), which is honest and still used live by
    api/event.py and api/full_analysis.py.
    """

    EVENT_RULES = {
        "earnings": {
            "risk_score": 30,
            "event_score": 80,
            "market_impact": 50
        },
        "ceo_change": {
            "risk_score": 60,
            "event_score": 70,
            "market_impact": 40
        },
        "regulation": {
            "risk_score": 90,
            "event_score": 50,
            "market_impact": 70
        },
        "unusual_volume": {
            "risk_score": 40,
            "event_score": 60,
            "market_impact": 30
        }
    }

    def analyze_event(self, event_type: str):

        return self.EVENT_RULES.get(
            event_type,
            {
                "risk_score": 50,
                "event_score": 50,
                "market_impact": 50
            }
        )