from fastapi import APIRouter
from ai.ai_router import get_ai_response
from services.market_data_service import MarketDataService
from services.i18n import ai_language_instruction

router = APIRouter()
market_svc = MarketDataService()

@router.post("/company-compare")
async def company_compare(body: dict):
    symbols = body.get("symbols", [])
    token = body.get("token")
    lang = body.get("lang")
    if not symbols:
        return {"status": "ok", "data": {"analysis": "請輸入公司代號"}}

    market_data = {}
    for s in symbols:
        try:
            data = market_svc.get_stock_data(s.upper())
            market_data[s] = data
        except:
            market_data[s] = {}

    summary = ", ".join([f"{s}: ${market_data[s].get('price', 'N/A')}" for s in symbols])

    prompt = (
        f"你是專業金融分析師。請比較以下公司：{', '.join(symbols)}。"
        f"當前價格：{summary}。"
        f"{ai_language_instruction(lang)} 內容需包含：1) 各公司優劣勢 2) 財務比較 3) 值得關注的比較觀點 4) 風險提示。"
        "這是客觀資訊整理，不是投資建議，請勿使用「建議買入」「建議賣出」等字眼。"
        "格式清晰，使用 ## 標題。"
    )
    from services.quota_middleware import check_token_budget, record_ai_token_usage
    user_id = check_token_budget(token)

    try:
        answer = get_ai_response(prompt, max_tokens=1000)
        record_ai_token_usage(user_id)
    except:
        answer = "比較分析服務暫時不可用，請稍後再試。"

    return {"status": "ok", "data": {"analysis": answer, "conclusion": answer, "market_data": market_data}}
