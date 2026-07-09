import base64
import binascii
import json
from fastapi import APIRouter

from ai.ai_router import get_vision_response

router = APIRouter()

# --- Security limits ---
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB, after base64 decoding

# Real file signatures ("magic bytes") for the formats we accept.
# We check the ACTUAL decoded bytes, not whatever mime_type the client claims.
MAGIC_SIGNATURES = {
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/webp": [b"RIFF"],  # followed by size(4 bytes) + "WEBP", checked separately below
}


def detect_real_mime_type(raw_bytes: bytes) -> str | None:
    """
    Identify the file type from its actual binary signature, ignoring
    whatever mime_type the client (browser) claims. This stops a renamed
    or mislabeled file from slipping through as if it were an image.
    """
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw_bytes.startswith(b"RIFF") and raw_bytes[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/chart-analysis")
async def chart_analysis(body: dict):
    """
    Real chart image analysis using a vision-capable AI model.

    Expects:
        image: base64-encoded image data (no "data:" prefix)
        mime_type: image MIME type, e.g. "image/png" (advisory only — verified server-side)
        symbol: optional ticker/stock name for context

    Security notes:
        - We never write the uploaded image to disk, and never open it with
          a local image-processing library (Pillow/ImageMagick etc.) — it is
          only base64-encoded and forwarded to the vision API. This avoids
          the classic "malicious image exploits local image decoder" attack
          surface entirely.
        - We still enforce a size cap and verify the real file signature
          before doing anything else, so we reject bad/oversized payloads
          as early and cheaply as possible.
    """
    image_base64 = body.get("image")
    symbol = body.get("symbol", "")

    if not image_base64:
        return {
            "status": "error",
            "message": "冇收到圖片，請重新上傳K線圖。"
        }

    # --- Layer 1: decode + size check ---
    try:
        raw_bytes = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError):
        return {
            "status": "error",
            "message": "圖片格式無效，請重新上傳。"
        }

    if len(raw_bytes) > MAX_IMAGE_BYTES:
        return {
            "status": "error",
            "message": "圖片檔案過大（上限8MB），請上傳較細嘅圖片。"
        }

    if len(raw_bytes) == 0:
        return {
            "status": "error",
            "message": "圖片內容為空，請重新上傳。"
        }

    # --- Layer 2: verify the REAL file signature, not the client's claim ---
    real_mime_type = detect_real_mime_type(raw_bytes)
    if not real_mime_type:
        return {
            "status": "error",
            "message": "僅支援 JPG / PNG / WebP 格式嘅圖片，請重新上傳。"
        }

    prompt = (
        "你是專業技術分析師，正在觀察一張真實嘅K線圖截圖。"
        f"{'股票代號：' + symbol if symbol else ''}\n\n"
        "重要規則：\n"
        "1. 只可以根據你喺圖片入面實際睇到嘅刻度、數字、線條嚟分析，唔可以估計或者作大約數值。\n"
        "2. 支撐位/阻力位要參考圖表Y軸嘅實際刻度數字，逐格對照，唔好隨便估一個接近嘅數。\n"
        "3. 如果睇唔清楚、圖片太細或者冇顯示某項資訊（例如RSI、MACD），"
        "就照實寫「圖中未能清楚辨識」或者「圖中未顯示」，唔好亂up答案。\n"
        "4. 檢查圖表下方有冇獨立嘅指標窗格（RSI通常0-100，MACD通常有柱狀圖+兩條線），"
        "如果有先評論，如果冇就講明冇顯示。\n\n"
        "用繁體中文提供以下分析，只回覆一個JSON物件，唔好加任何其他文字：\n"
        "{\n"
        '  "trend": "上升/下降/橫盤（根據圖中K棒走勢判斷）",\n'
        '  "support": "根據Y軸刻度讀出嘅支撐位價格，睇唔清就寫『圖中未能清楚辨識』",\n'
        '  "resistance": "根據Y軸刻度讀出嘅阻力位價格，睇唔清就寫『圖中未能清楚辨識』",\n'
        '  "volume": "成交量分析，圖中冇顯示就寫『圖中未顯示成交量』",\n'
        '  "rsi": "RSI數值同解讀，圖中冇顯示就寫『圖中未顯示RSI』",\n'
        '  "macd": "MACD走勢同解讀，圖中冇顯示就寫『圖中未顯示MACD』",\n'
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
        answer = get_vision_response(prompt, image_base64, real_mime_type, max_tokens=700)
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
