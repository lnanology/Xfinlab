from fastapi import APIRouter
from ai.ai_router import get_ai_response

router = APIRouter()

conversation_store = {}

@router.post("/chat")
async def chat(body: dict):
    query = body.get("query", "")
    conversation_id = body.get("conversation_id", "default")
    
    if not query:
        return {"status": "ok", "answer": "請輸入問題", "conversation_id": conversation_id}

    # 建立對話歷史
    if conversation_id not in conversation_store:
        conversation_store[conversation_id] = []
    
    history = conversation_store[conversation_id]
    
    prompt = (
        "你是 XFINLAB AI 投資助手。專門回答股票、投資、市場分析問題。"
        "用繁體中文回答，專業但易懂。如果問題與投資無關，禮貌地引導回投資話題。\n\n"
        f"用戶問題：{query}"
    )
    
    try:
        answer = get_ai_response(prompt, max_tokens=800)
        history.append({"q": query, "a": answer})
        if len(history) > 10:
            history.pop(0)
        return {
            "status": "ok",
            "answer": answer,
            "conversation_id": conversation_id
        }
    except Exception as e:
        return {
            "status": "ok", 
            "answer": "AI 服務暫時不可用，請稍後再試。",
            "conversation_id": conversation_id
        }
