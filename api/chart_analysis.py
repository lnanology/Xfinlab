import base64
import binascii
import json
import re
from fastapi import APIRouter

from ai.ai_router import get_vision_response
from services.technical_analysis_service import get_technical_analysis

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

    # --- Try to get REAL market data first (if a symbol was supplied) ---
    # This is the Chart Analysis MVP: numeric levels (支撐/阻力/RSI/MACD/
    # Fibonacci) come from real historical OHLC data, not from an AI
    # "eyeballing" a screenshot. The AI is only asked to do what a human eye
    # is actually needed for: visual pattern recognition.
    tech = None
    if symbol:
        tech = get_technical_analysis(symbol)
        if tech and "error" in tech:
            tech = None  # fall back to AI-only flow below, silently

    if tech:
        prompt = (
            "你是專業技術分析師，正在觀察一張真實嘅K線圖截圖，"
            f"股票代號：{symbol}。\n\n"
            "以下係用真實歷史股價數據（唔係AI估計）精確計算出嚟嘅數值，"
            "你唔需要、亦都唔應該再自己估呢啲數字：\n"
            f"- 現價：{tech['last_close']}\n"
            f"- 趨勢（相對MA50）：{tech['trend']}\n"
            f"- RSI(14)：{tech['rsi']}\n"
            f"- MACD：{tech['macd']['trend']}（柱狀圖 {tech['macd']['histogram']}）\n"
            f"- 支撐位：{tech['support']['level'] if tech['support'] else '未偵測到'}\n"
            f"- 阻力位：{tech['resistance']['level'] if tech['resistance'] else '未偵測到'}\n"
            f"- 0.618 Fibonacci回調位：{tech['fibonacci_0618']['level_0618'] if tech['fibonacci_0618'] else '未偵測到'}\n"
            f"- 成交量：{tech['volume_desc']}\n"
            f"- 綜合訊號評分（Confluence）：{tech['confluence']['direction']}"
            f"（分數{tech['confluence']['score']}，信心{tech['confluence']['confidence']}）\n"
            f"  睇多訊號：{'、'.join(tech['confluence']['bullish_signals']) or '無'}\n"
            f"  睇淡訊號：{'、'.join(tech['confluence']['bearish_signals']) or '無'}\n\n"
            "你嘅任務淨係兩樣：\n"
            "1. 純粹用眼睇圖，辨識圖表入面嘅視覺型態（雙頂/雙底/頭肩頂/頭肩底/三角收斂/突破回測/0.618回調結構）。\n"
            "2. 結合上面提供嘅真實數據 + Confluence評分 + 你睇到嘅視覺型態，畀出簡短風險提示同建議，"
            "如果你睇到嘅型態同Confluence評分方向一致，要喺建議入面講明「型態同數據訊號一致」；"
            "如果矛盾，要講明邊樣同邊樣有衝突，唔好扮冇睇到。\n"
            "唔好自己再估支撐位/阻力位/RSI/MACD數值，一律以上面提供嘅真實數據為準。\n"
            "每個欄位答案要精簡，唔好超過20隻字。\n\n"
            "只回覆一個JSON物件，唔好加任何其他文字、唔好加markdown、唔好加解釋：\n"
            "{\n"
            '  "patterns": {\n'
            '    "p_double_top": "可能/不可能",\n'
            '    "p_double_bottom": "可能/不可能",\n'
            '    "p_head_shoulder_top": "可能/不可能",\n'
            '    "p_head_shoulder_bottom": "可能/不可能",\n'
            '    "p_triangle": "可能/不可能",\n'
            '    "p_breakback": "可能/不可能",\n'
            '    "p_0618": "可能/不可能"\n'
            '  },\n'
            '  "risk": "簡短風險提示，15隻字內",\n'
            '  "recommendation": "簡短建議，15隻字內"\n'
            "}"
        )
        max_tokens = 1500
    else:
        prompt = (
            "你是專業技術分析師，正在觀察一張真實嘅K線圖截圖。"
            f"{'股票代號：' + symbol if symbol else ''}\n\n"
            "重要規則：\n"
            "1. 只可以根據你喺圖片入面實際睇到嘅刻度、數字、線條嚟分析，唔可以估計或者作大約數值。\n"
            "2. 支撐位/阻力位要參考圖表Y軸嘅實際刻度數字，逐格對照，唔好隨便估一個接近嘅數。\n"
            "3. 如果睇唔清楚、圖片太細或者冇顯示某項資訊（例如RSI、MACD），"
            "就照實寫「圖中未能清楚辨識」或者「圖中未顯示」，唔好亂up答案。\n"
            "4. 檢查圖表下方有冇獨立嘅指標窗格（RSI通常0-100，MACD通常有柱狀圖+兩條線），"
            "如果有先評論，如果冇就講明冇顯示。\n"
            "5. 每個欄位嘅答案要精簡，唔好超過15隻字，唔好寫長句子。\n\n"
            "用繁體中文提供以下分析，只回覆一個JSON物件，唔好加任何其他文字，"
            "唔好加markdown、唔好加解釋，只回覆單一個完整JSON：\n"
            "{\n"
            '  "trend": "上升/下降/橫盤",\n'
            '  "support": "價格數字或『未能辨識』",\n'
            '  "resistance": "價格數字或『未能辨識』",\n'
            '  "volume": "簡短描述或『未顯示』",\n'
            '  "rsi": "數值+簡短描述或『未顯示』",\n'
            '  "macd": "簡短描述或『未顯示』",\n'
            '  "patterns": {\n'
            '    "p_double_top": "可能/不可能",\n'
            '    "p_double_bottom": "可能/不可能",\n'
            '    "p_head_shoulder_top": "可能/不可能",\n'
            '    "p_head_shoulder_bottom": "可能/不可能",\n'
            '    "p_triangle": "可能/不可能",\n'
            '    "p_breakback": "可能/不可能",\n'
            '    "p_0618": "可能/不可能"\n'
            '  },\n'
            '  "risk": "簡短風險提示，15隻字內",\n'
            '  "recommendation": "簡短建議，15隻字內"\n'
            "}"
        )
        max_tokens = 3000

    try:
        raw_answer = get_vision_response(prompt, image_base64, real_mime_type, max_tokens=max_tokens)
        answer = raw_answer.replace("```json", "").replace("```", "").strip()
        start = answer.find("{")
        end = answer.rfind("}") + 1
        if start != -1 and end > start:
            answer = answer[start:end]

        # AI models sometimes leave a trailing comma before } or ] which
        # breaks strict JSON parsing — strip those before parsing.
        answer_cleaned = re.sub(r",\s*([}\]])", r"\1", answer)

        try:
            ai_result = json.loads(answer_cleaned)
        except json.JSONDecodeError as e:
            # Temporary debug aid: include a snippet of what the AI actually
            # returned so we can see exactly what's malformed.
            snippet = answer_cleaned[:300]
            return {
                "status": "error",
                "message": f"AI回覆格式有問題：{str(e)} | 原始回覆片段：{snippet}"
            }

        # --- Merge: real market data (numeric levels) + AI (visual patterns) ---
        if tech:
            result = {
                "trend": tech["trend"],
                "support": tech["support"]["level"] if tech["support"] else "未偵測到",
                "resistance": tech["resistance"]["level"] if tech["resistance"] else "未偵測到",
                "volume": tech["volume_desc"],
                "rsi": tech["rsi"],
                "macd": tech["macd"]["trend"],
                "fibonacci_0618": tech["fibonacci_0618"]["level_0618"] if tech["fibonacci_0618"] else None,
                "confluence": tech["confluence"],
                "patterns": ai_result.get("patterns", {}),
                "risk": ai_result.get("risk", ""),
                "recommendation": ai_result.get("recommendation", ""),
                "data_source": "real_market_data+ai_vision_patterns",
            }
        else:
            result = ai_result
            result["data_source"] = "ai_vision_only"

        return {"status": "ok", "data": result}
    except Exception as e:
        return {
            "status": "error",
            "message": f"分析失敗，請重試：{str(e)}"
        }
