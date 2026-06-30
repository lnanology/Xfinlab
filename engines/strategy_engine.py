import json


class StrategyEngine:
    """
    Strategy Engine™ 用於加載策略規則、計算分數和生成信號。
    """

    def __init__(self, strategy_filepath):
        """
        初始化引擎並加載策略規則。

        參數：
        strategy_filepath (str): JSON 策略文件的相對路徑。
        """
        self.strategy_filepath = strategy_filepath
        self.strategy_rules = self._load_strategy()

    def _load_strategy(self):
        """
        從 JSON 文件中加載策略規則。

        返回：
        dict: 策略規則。
        """
        with open(self.strategy_filepath, "r") as f:
            return json.load(f)

    def calculate_score(self, data):
        """
        根據策略規則計算分數（0-100）。

        參數：
        data (dict): 輸入數據，包含策略規則所需的所有參數。

        返回：
        int: 分數（0-100）。
        """
        score = 0
        for rule in self.strategy_rules.get("rules", []):
            condition = rule.get("condition")
            weight = rule.get("weight")
            if self._evaluate_condition(condition, data):
                score += weight
        return min(max(score, 0), 100)  # 確保分數在 0-100 之間

    def generate_signal(self, score):
        """
        根據分數生成信號（Bullish/Neutral/Bearish）。

        參數：
        score (int): 計算出的分數（0-100）。

        返回：
        str: 信號（Bullish/Neutral/Bearish）。
        """
        if score >= 70:
            return "Bullish"
        elif 30 <= score < 70:
            return "Neutral"
        else:
            return "Bearish"

    def _evaluate_condition(self, condition, data):
        """
        評估條件是否成立。

        參數：
        condition (str): 條件表達式，例如 "data['price'] > 100"。
        data (dict): 輸入數據。

        返回：
        bool: 條件是否成立。
        """
        return eval(condition, {"data": data})  # 使用 eval 執行條件表達式


# 示例用法
if __name__ == "__main__":
    # 示例策略 JSON 文件
    strategy_filepath = "strategies/AJ_Strategy_V1.json"

    # 初始化引擎
    engine = StrategyEngine(strategy_filepath)

    # 示例輸入數據
    data = {
        "price": 120,
        "volume": 1000,
        "sentiment": "Bullish",
    }

    # 計算分數
    score = engine.calculate_score(data)
    print(f"Score: {score}")

    # 生成信號
    signal = engine.generate_signal(score)
    print(f"Signal: {signal}")
