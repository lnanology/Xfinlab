from fastapi import APIRouter
from ai.ai_router import get_ai_response
from services.i18n import ai_language_instruction

router = APIRouter()

SCENARIOS = {
    "crash2008": "2008年金融海嘯（標普500跌57%，持續18個月）",
    "covid2020": "2020年COVID崩盤（標普500跌34%，持續1個月）",
    "dotcom2000": "2000年科網泡沫（納斯達克跌78%，持續30個月）",
    "inflation2022": "2022年加息周期（標普500跌25%，持續12個月）",
    "custom": "自定義壓力測試場景",
}

@router.post("/stress-lab")
async def stress_lab(body: dict):
    strategy = body.get("strategy", "crash2008")
    amount = body.get("amount", 100000)
    token = body.get("token")
    lang = body.get("lang")
    scenario = SCENARIOS.get(strategy, SCENARIOS["crash2008"])

    prompt = (
        f"你是風險分析師。針對投資金額 ${amount:,} 進行壓力測試。"
        f"測試場景：{scenario}。"
        f"{ai_language_instruction(lang)} 內容需包含：\n"
        "## 📉 預估損失\n（金額和百分比）\n"
        "## ⏱ 恢復時間\n（預估恢復所需時間）\n"
        "## 🛡 風險緩解建議\n（3-5個具體建議）\n"
        "## 💡 歷史啟示\n（從歷史事件學到的教訓）"
    )
    from services.quota_middleware import check_token_budget, record_ai_token_usage
    user_id = check_token_budget(token)

    try:
        answer = get_ai_response(prompt, max_tokens=800)
        record_ai_token_usage(user_id)
    except:
        answer = "壓力測試服務暫時不可用，請稍後再試。"

    return {"status": "ok", "data": {"analysis": answer, "conclusion": answer, "scenario": scenario}}
