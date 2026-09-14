from fastapi import APIRouter, Request
from ai.ai_router import get_ai_response
from services.i18n import ai_language_instruction
from services.rate_limiter import limiter

router = APIRouter()

# 2026-09-14 fix (site-wide pain-points audit finding #6): this is a real,
# unauthenticated LLM call (get_ai_response, max_tokens=800) that had NO
# protection beyond the blanket 100/minute per-IP default in backend/
# main.py -- unlike every other AI-calling endpoint in this codebase, which
# either requires a login + services/quota_middleware.py token budget
# (api/chat.py, api/ai_analysis.py) or, for the public/no-login tools it's
# most similar to, a tight per-IP cap (api/free_tools_demo.py's
# `_DEMO_LIMIT = "8/minute"`). This is exactly that second case -- news-
# denoise.html and the news-denoise widgets across several pages are
# intentionally usable without logging in -- so it gets the same 8/minute
# per-IP cap free_tools_demo.py already uses for the same reason, rather
# than a login-gated budget that would break the no-login UX.
_NEWS_DENOISE_LIMIT = "8/minute"

@router.post("/news-denoise")
@limiter.limit(_NEWS_DENOISE_LIMIT)
async def news_denoise(request: Request, body: dict):
    query = body.get("query", "")
    topic = body.get("topic", "市場新聞")
    lang = body.get("lang")

    prompt = (
        f"你是一位專業金融分析師。請分析以下主題的最新市場新聞：{query or topic}\n\n"
        f"{ai_language_instruction(lang)} 格式如下：\n"
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
    except Exception:
        return {
            "status": "ok",
            "data": {
                "analysis": "新聞分析服務暫時不可用，請稍後再試。",
                "conclusion": "新聞分析服務暫時不可用，請稍後再試。"
            }
        }
