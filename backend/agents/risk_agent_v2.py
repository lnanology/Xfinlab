
class RiskAgentV2:
    @staticmethod
    def evaluate(volatility):
        if volatility > 70:
            return {"risk": "HIGH", "allocation_cap": 0.2}
        elif volatility < 30:
            return {"risk": "LOW", "allocation_cap": 0.8}
        return {"risk": "MEDIUM", "allocation_cap": 0.5}
