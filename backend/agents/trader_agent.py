
class TraderAgent:
    @staticmethod
    def execute(signal, capital):
        if signal == "AGGRESSIVE_GROWTH":
            return capital * 0.7
        elif signal == "DEFENSIVE":
            return capital * 0.3
        return capital * 0.5
