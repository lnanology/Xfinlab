from fastapi import APIRouter
from ai.ai_router import get_ai_response_with_escalation
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

    # 2026-07-23 follow-up ("AI而家會老實話冇即時數據...咁加入卡片比佢選擇按
    # 所有回答無方向都要比方向用戶"): chat.html's numbered-options-cards
    # feature (2026-07-23, "1. AAPL 2. TSLA" style choices become clickable
    # cards) already turns any 2+-line numbered list in the answer into
    # cards; the honesty redirect below is now phrased as exactly that kind
    # of list, in the model's OWN language, so the redirect becomes 3
    # clickable cards instead of a wall of prose. chat.html's
    # resolveNavTarget() recognizes "Free Signals"/"AI Analysis"/"Chart
    # Analysis" by name and routes those specific cards to the real page
    # instead of re-asking the same question in chat -- so the model should
    # keep using those exact English feature names (never translate/rename
    # them) even when the rest of its answer is in another language.
    NAV_CARD_NAMES = "Free Signals、AI Analysis、Chart Analysis"

    # 2026-07-23 fix ("打口語唔得...可以做到好似CLAUDE咁嗎", then "口語同俚語
    # 全世界都要加入"): the old prompt (a) told the model to steer any
    # non-investment question back to finance, which reads as gatekeeping/
    # robotic in normal chat use, and (b) said nothing about tone/
    # register, so answers defaulted to a stiff, formal, template-heavy
    # voice even for a casual colloquial question. Neither is a model-
    # capability limit -- openai/gpt-oss-120b (the underlying Groq model)
    # already understands casual speech/slang in any of the site's 46
    # supported languages fine; it just wasn't being asked to answer that
    # way. The colloquial/slang instruction below is deliberately written
    # to apply to WHATEVER language ai_language_instruction(lang) tells it
    # to answer in (not hardcoded to Cantonese), since every one of the
    # 46 languages has its own equivalent of casual slang/shorthand.
    # User explicitly chose "keep the free Groq model, just make the
    # prompt itself more natural" over switching this endpoint to the
    # already-wired but paid `claude` provider in ai/ai_router.py.
    prompt = (
        "你是 XFINLAB 嘅AI助手，識股票、投資、市場分析，但唔淨係得呢啲——用戶問乜都可以自然咁答，"
        "唔使成日拉番去投資話題；如果佢想隨便傾偈、問日常嘢，就好似朋友噉傾返，唔使勉強扣題。"
        f"{ai_language_instruction(lang)} "
        "無論用戶用邊種語言傾偈（包括粵語、國語、英文、西班牙文等呢站支援嘅全部46種語言），"
        "你都要聽得明同識用返嗰種語言真正日常人用嘅口語、俚語、簡寫、網絡用語去回應"
        "（例如粵語「而家邊隻股票掂」「呢排點呀」，英文「what's up with」「no cap」呢類日常講法），"
        "唔好因為用戶打得隨便就切去生硬嘅書面/正式語氣，配合返用戶自己嘅語氣同用語習慣；"
        "唔明就直接問返佢想講乜，唔好靠估。"
        "回答盡量似真人傾偈噉自然有溫度，唔好成日都用標題／項目符號嘅公式化格式——"
        "淨係真係有好多資訊/數字需要分項嗰陣先用列表，普通閒聊或者簡單問題就用返一兩句直接、口語化咁答。"
        "誠實好緊要：呢個chat endpoint本身冇連接即時股價/新聞數據源，如果用戶問嘅係具體、"
        "即市嘅數字（例如「而家AAPL幾多錢」「今日邊隻升得最勁」），千祈唔好夾一個聽落去好肯定嘅假數字出嚟，"
        "要老實話畀用戶知你冇即時數據；跟住用返用戶自己嗰種語言，"
        "以編號列表形式（1. 2. 3.）畀返最多3個選擇，叫佢去下面3個真係接返即市數據嘅功能度睇實際數字——"
        f"呢3個功能嘅名一定要原字照用（唔好翻譯/改寫/加多餘字）：{NAV_CARD_NAMES}，例如：\n"
        "1. 去 Free Signals 睇每日免費即市信號\n"
        "2. 去 AI Analysis 做完整技術分析\n"
        "3. 去 Chart Analysis 睇即時K線走勢\n"
        "（呢個列表格式好緊要，因為前端會將呢啲編號選項自動變成可以直接撳入去嗰功能嘅卡片，"
        "唔好將呢3個名夾雜喺一般段落入面，一定要用返呢種獨立編號列表格式）；"
        "一般知識性/歷史性/解釋性嘅嘢（例如點解某個指標咁計、某間公司做乜生意）就照答，"
        "唔識就話唔識，唔好靠估當肯定講畀用戶聽。"
        "呢個原則仲要再廣泛啲：唔淨止得冇即時數據呢個情況先咁做——但凡你嘅答案冇辦法畀到用戶一個好清晰、"
        "肯定嘅方向（例如問題太廣泛、你資訊唔夠齊全、或者答案本質上就有好多可能性），"
        "都應該喺答完之後主動提出2-3個具體、用戶可以即刻跟住做嘅下一步方向（例如再問邊個具體問題、"
        "去邊個功能頁睇實際數據、定係提供邊啲資訊等你再仔細答），唔好淨係留低一個冇方向、"
        "用戶唔知點跟落去嘅答案。"
        "如果係投資問題，就保持專業準確；如果用戶嘅問題有歧義（例如唔清楚想問邊個具體資產、邊個時間框架、"
        "定係想要邊種分析角度），可以先簡短反問1-2個問題澄清，等用戶下次回覆講清楚先再詳細分析；"
        "但如果已經有足夠資訊（包括下面嘅背景資訊已經識別到具體資產），"
        "就唔好淨係反問，應該直接畀返仔細、有針對性嘅分析，答到point。"
        f"{history_text}\n\n{context_note}用戶問題：{query}"
    )

    from services.quota_middleware import check_token_budget, record_ai_token_usage
    user_id = check_token_budget(token)

    try:
        # 2026-07-30: this is the site's flagship "talk to AI" feature --
        # the one users most directly compare against a paid model like
        # Claude/GPT. Two additive changes from the plain get_ai_response()
        # call this used before: (1) reasoning_effort="high" asks Groq's
        # gpt-oss-120b to actually think harder before answering (was
        # hardcoded "low" everywhere purely for speed); max_tokens is
        # raised from 800->1200 alongside it since "high" reasoning eats
        # more of the budget on hidden thinking tokens before writing the
        # visible answer (see ai/ai_router.py's _groq() docstring -- this
        # exact failure mode caused a real empty-response bug before).
        # (2) get_ai_response_with_escalation() falls back to Claude ONCE
        # if Groq's answer ever comes back empty/degenerate, rather than
        # immediately showing the canned "AI 服務暫時不可用" message. This
        # does NOT reverse the earlier decision to keep Groq as the
        # default for cost reasons -- Claude is only ever called on the
        # rare failure case, not on every request.
        answer = get_ai_response_with_escalation(prompt, max_tokens=1200, reasoning_effort="high")
        if not answer.strip():
            # get_ai_response_with_escalation() deliberately never raises
            # (it returns "" if both Groq and the Claude escalation fail
            # or aren't configured) -- turn that into the SAME "service
            # unavailable" UX this endpoint always showed on failure,
            # instead of silently returning an empty answer to the user.
            raise RuntimeError("AI response empty after Groq + escalation attempt")
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
