
class PaperTrader:
    def __init__(self):
        self.cash = 100000
        self.position = {}

    def execute(self, ticker, signal, price):
        if signal == "BUY":
            self.position[ticker] = self.position.get(ticker, 0) + 1
            self.cash -= price
        elif signal == "SELL" and self.position.get(ticker, 0) > 0:
            self.position[ticker] -= 1
            self.cash += price
        return {"cash": self.cash, "position": self.position}
