
class PortfolioAgent:
    @staticmethod
    def allocate(risk, analyst):
        base = 1.0
        if risk["risk"] == "HIGH":
            base *= 0.5
        elif risk["risk"] == "LOW":
            base *= 1.2
        if analyst["confidence"] > 0.6:
            base *= 1.1
        return {"allocation_score": base}
