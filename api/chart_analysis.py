from fastapi import APIRouter
from ai.ai_router import get_ai_response

router = APIRouter()

@router.post("/chart-analysis")
async def chart_analysis(body: dict):
    filename = body.get("filename", "chart")
    symbol = body.get("symbol", "")
    description = body.get("description", "")

    prompt = (
        f"你是專業技術分析師。分析以下K線圖資訊：\n"
        f"股票：{symbol or filename}\n"
        f"圖表描述：{description or '用戶上傳了一張K線圖'}\n\n"
        "請用繁體中文提供以下分析（JSON格式）：\n"
        "{\n"
        '  "trend": "上升/下降/橫盤",\n'
        '  "support": "支撐位價格",\n'
        '  "resistance": "阻力位價格",\n'
        '  "volume": "成交量分析",\n'
        '  "patterns": {\n'
        '    "p_double_top": "可能/不可能",\n'
        '    "p_double_bottom": "可能/不可能",\n'
        '    "p_head_shoulder_top": "可能/不可能",\n'
        '    "p_head_shoulder_bottom": "可能/不可能",\n'
        '    "p_triangle": "可能/不可能",\n'
        '    "p_breakback": "可能/不可能",\n'
        '    "p_0618": "可能/不可能"\n'
        '  },\n'
        '  "risk": "風險提示",\n'
        '  "recommendation": "建議操作"\n'
        "}"
    )

    try:
        import json
        answer = get_ai_response(prompt, max_tokens=600)
        answer = answer.replace("```json", "").replace("```", "").strip()
        # Extract JSON if wrapped in other text
        start = answer.find("{")
        end = answer.rfind("}") + 1
        if start != -1 and end > start:
            answer = answer[start:end]
        result = json.loads(answer)
        return {"status": "ok", "data": result}
    except:
        return {
            "status": "ok",
            "data": {
                "trend": "需要圖片才能分析",
                "support": "N/A",
                "resistance": "N/A",
                "volume": "N/A",
                "patterns": {
                    "p_double_top": "不可能",
                    "p_double_bottom": "不可能",
                    "p_head_shoulder_top": "不可能",
                    "p_head_shoulder_bottom": "不可能",
                    "p_triangle": "不可能",
                    "p_breakback": "不可能",
                    "p_0618": "不可能"
                },
                "risk": "請上傳K線圖後重新分析",
                "recommendation": "等待圖片分析"
            }
        }
