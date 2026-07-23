from fastapi import APIRouter
from ai.ai_router import get_ai_response
from services.i18n import ai_language_instruction
from services.ticker_shorthand import build_context_note

router = APIRouter()

conversation_store = {}
MAX_HISTORY_TURNS = 6  # keep prompt short so cost/latency stays predictable


@router.post("/chat")
async def chat(body: dict):
    """
    XFINLAB AI 投資助手 chat endpoint.

    Previously proxied to Dify (services/dify_service.py). Now uses the same
    ai/ai_router.py provider (Groq by default) already trusted elsewhere in
    the codebase (e.g. chart_analysis.py) — no external Dify account needed.
    Request/response shape is unchanged, so the frontend (chat.html) needs
    no changes.
    """
    query = body.get("query", "")
    conversation_id = body.get("conversation_id", "default")
    token = body.get("token")
    lang = body.get("lang")

    if not query:
        return {"status": "ok", "answer": "請輸入問題", "conversation_id": conversation_id}

    if conversation_id not in conversation_store:
        conversation_store[conversation_id] = []

    history = conversation_store[conversation_id]

    # Fold recent turns into the prompt so multi-turn context isn't lost now
    # that there's no Dify-side conversation_id to carry it for us.
    history_text = ""
    if history:
        recent = history[-MAX_HISTORY_TURNS:]
        history_text = "\n\n之前對話：\n" + "\n".join(
            f"用戶：{turn['query']}\n助手：{turn['answer']}" for turn in recent
        )

    # 2026-07-23 fix: "打HK50都唔知係期貨" -- there was no lookup anywhere
    # for CFD-style index/futures shorthand (HK50/US30/NAS100/etc.), so
    # the model had to guess blind. This gives it the actual asset
    # identity up front instead of leaving it to free-text guessing.
    context_note = build_context_note(query)

    prompt = (
        "你是 XFINLAB AI 投資助手。專門回答股票、投資、市場分析問題。"
        f"{ai_language_instruction(lang)} 專業但易懂。如果問題與投資無關，禮貌地引導回投資話題。"
        "如果用戶嘅問題有歧義（例如唔清楚想問邊個具體資產、邊個時間框架、定係想要邊種分析角度），"
        "可以先簡短反問1-2個問題澄清，等用戶下次回覆講清楚先再詳細分析；"
        "但如果已經有足夠資訊（包括下面嘅背景資訊已經識別到具體資產），"
        "就唔好淨係反問，應該直接畀返仔細、有針對性嘅分析，答到point。"
        f"{history_text}\n\n{context_note}用戶問題：{query}"
    )

    from services.quota_middleware import check_token_budget, record_ai_token_usage
    user_id = check_token_budget(token)

    try:
        answer = get_ai_response(prompt, max_tokens=800)
        record_ai_token_usage(user_id)
        history.append({"query": query, "answer": answer})
        conversation_store[conversation_id] = history[-MAX_HISTORY_TURNS:]
        return {
            "status": "ok",
            "answer": answer,
            "conversation_id": conversation_id,
        }
    except Exception:
        return {
            "status": "ok",
            "answer": "AI 服務暫時不可用，請稍後再試。",
            "conversation_id": conversation_id,
        }
