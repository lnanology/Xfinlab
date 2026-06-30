class EventEngine:
    """
    Event Risk Engine
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