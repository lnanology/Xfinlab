
class BacktestEngine:
    @staticmethod
    def run(signals, prices):
        cash = 100000
        position = 0
        for i in range(len(signals)):
            if signals[i] == "BUY":
                position += 1
                cash -= prices[i]
            elif signals[i] == "SELL" and position > 0:
                position -= 1
                cash += prices[i]
        return {"final_cash": cash, "position": position, "return": (cash - 100000) / 100000}
