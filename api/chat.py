from fastapi import APIRouter
from ai.ai_router import get_ai_response

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

    prompt = (
        "你是 XFINLAB AI 投資助手。專門回答股票、投資、市場分析問題。"
        "用繁體中文回答，專業但易懂。如果問題與投資無關，禮貌地引導回投資話題。"
        f"{history_text}\n\n用戶問題：{query}"
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
