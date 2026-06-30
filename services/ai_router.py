class AIRouter:
    """
    AI Router™ 用於根據任務類型選擇最佳的 AI 模型。
    支持的模型：DeepSeek Flash, DeepSeek Pro, GPT, Claude, Gemini。
    """

    def __init__(self):
        self.model_map = {
            "DeepSeek Flash": "效率優先，適合簡單任務",
            "DeepSeek Pro": "高效且精確，適合研究任務",
            "GPT": "複雜且智能，適合複雜任務",
            "Claude": "事件分析專家",
            "Gemini": "通用回退模型",
        }

    def route_request(self, task_type):
        """
        根據任務類型路由到合適的 AI 模型。

        參數：
        task_type (str): 任務類型，支持：
            - "simple": 簡單任務
            - "research": 研究任務
            - "complex": 複雜任務
            - "event": 事件分析
            - "fallback": 回退任務

        返回：
        dict: 包含模型名稱和描述。
        """
        if task_type == "simple":
            return self._mock_response("DeepSeek Flash")
        elif task_type == "research":
            return self._mock_response("DeepSeek Pro")
        elif task_type == "complex":
            return self._mock_response("GPT")
        elif task_type == "event":
            return self._mock_response("Claude")
        elif task_type == "fallback":
            return self._mock_response("Gemini")
        else:
            raise ValueError(f"不支持的任務類型: {task_type}")

    def _mock_response(self, model_name):
        """
        模擬 AI 模型的回傳結果。

        參數：
        model_name (str): 模型名稱

        返回：
        dict: 包含模型名稱和描述。
        """
        return {
            "model": model_name,
            "description": self.model_map[model_name],
        }


# 示例用法
if __name__ == "__main__":
    router = AIRouter()

    # 測試路由
    print(router.route_request("simple"))  # DeepSeek Flash
    print(router.route_request("research"))  # DeepSeek Pro
    print(router.route_request("complex"))  # GPT
    print(router.route_request("event"))  # Claude
    print(router.route_request("fallback"))  # Gemini
