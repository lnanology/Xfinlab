from fastapi import APIRouter
from services.dify_service import DifyService

router = APIRouter()


@router.post("/dify/chat")
async def dify_chat(body: dict):
    query = body.get("query", "")
    user_id = body.get("user_id", "xfinlab-user")
    conversation_id = body.get("conversation_id", None)
    if not query:
        return {"status": "error", "answer": "請輸入問題"}
    return DifyService.chat(query, user_id, conversation_id)


@router.get("/dify/analyze/{ticker}")
async def dify_analyze(ticker: str):
    return DifyService.analyze_stock(ticker.upper())
