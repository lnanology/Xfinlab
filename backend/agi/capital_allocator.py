
class CapitalAllocator:
    @staticmethod
    def allocate(plan, capital=100000):
        if plan == "AGGRESSIVE_EXPAND":
            return {"stocks": 0.8 * capital, "cash": 0.2 * capital}
        if plan == "DEFENSIVE_MODE":
            return {"stocks": 0.3 * capital, "cash": 0.7 * capital}
        return {"stocks": 0.5 * capital, "cash": 0.5 * capital}
