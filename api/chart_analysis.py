import json
from fastapi import APIRouter

from ai.ai_router import get_vision_response

router = APIRouter()


@router.post("/chart-analysis")
async def chart_analysis(body: dict):
    """
    Real chart image analysis using a vision-capable AI model.

    Expects:
        image: base64-encoded image data (no "data:" prefix)
        mime_type: image MIME type, e.g. "image/png"
        symbol: optional ticker/stock name for context
    """
    image_base64 = body.get("image")
    mime_type = body.get("mime_type", "image/jpeg")
    symbol = body.get("symbol", "")

    if not image_base64:
        return {
            "status": "error",
            "message": "冇收到圖片，請重新上傳K線圖。"
        }

    prompt = (
        "你是專業技術分析師。請仔細觀察呢張K線圖圖片，"
        f"{'股票代號：' + symbol if symbol else ''}\n\n"
        "根據圖片入面實際睇到嘅走勢、K棒、成交量同型態，用繁體中文提供以下分析，"
        "只回覆一個JSON物件，唔好加任何其他文字：\n"
        "{\n"
        '  "trend": "上升/下降/橫盤（根據圖中走勢判斷）",\n'
        '  "support": "圖中觀察到嘅支撐位價格",\n'
        '  "resistance": "圖中觀察到嘅阻力位價格",\n'
        '  "volume": "成交量分析（如果圖中有顯示）",\n'
        '  "patterns": {\n'
        '    "p_double_top": "可能/不可能",\n'
        '    "p_double_bottom": "可能/不可能",\n'
        '    "p_head_shoulder_top": "可能/不可能",\n'
        '    "p_head_shoulder_bottom": "可能/不可能",\n'
        '    "p_triangle": "可能/不可能",\n'
        '    "p_breakback": "可能/不可能",\n'
        '    "p_0618": "可能/不可能"\n'
        '  },\n'
        '  "risk": "根據圖中型態嘅風險提示",\n'
        '  "recommendation": "建議操作"\n'
        "}"
    )

    try:
        answer = get_vision_response(prompt, image_base64, mime_type, max_tokens=700)
        answer = answer.replace("```json", "").replace("```", "").strip()
        start = answer.find("{")
        end = answer.rfind("}") + 1
        if start != -1 and end > start:
            answer = answer[start:end]
        result = json.loads(answer)
        return {"status": "ok", "data": result}
    except Exception as e:
        return {
            "status": "error",
            "message": f"分析失敗，請重試：{str(e)}"
        }
