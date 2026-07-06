
class ReactionEngine:
    @staticmethod
    def react(signal):
        if signal == "AGGRESSIVE_BUY":
            return {"action": "BUY", "speed": "FAST"}
        if signal == "SELL":
            return {"action": "SELL", "speed": "IMMEDIATE"}
        return {"action": "WAIT"}
