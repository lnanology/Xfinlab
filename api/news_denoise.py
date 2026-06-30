from fastapi import APIRouter
from ai.ai_router import get_ai_response

router = APIRouter()

@router.post("/news-denoise")
async def news_denoise(body: dict):
    query = body.get("query", "")
    topic = body.get("topic", "市場新聞")

    prompt = (
        f"你是一位專業金融分析師。請分析以下主題的最新市場新聞：{query or topic}\n\n"
        "請用繁體中文回答，格式如下：\n"
        "## 📰 市場摘要\n（2-3句總結）\n\n"
        "## 📌 重點新聞\n（3-5條重要新聞，每條包含標題和簡短分析）\n\n"
        "## 💡 AI 市場影響評估\n（對投資者的啟示）"
    )

    try:
        answer = get_ai_response(prompt, max_tokens=800)
        return {
            "status": "ok",
            "data": {
                "analysis": answer,
                "conclusion": answer
            }
        }
    except Exception as e:
        return {
            "status": "ok",
            "data": {
                "analysis": "新聞分析服務暫時不可用，請稍後再試。",
                "conclusion": "新聞分析服務暫時不可用，請稍後再試。"
            }
        }
