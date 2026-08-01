"""
Agent Society / AI Debate Service -- Tier 3 layered-UX addition
(2026-07-18).

Multi-persona debate (Bull / Bear / Risk Manager, then an Arbiter that
reads all three and synthesizes) over the SAME real data every other
part of this codebase uses -- confluence signals, regime, decision
levels -- never a separate "made up" data source. Each persona is asked
to ground its argument in the specific numbers it's given, not invent
new ones.

Cost/latency design (see the 2026-07-18 conversation that scoped this):
  - Always forced onto DeepSeek V4 Flash via ai_router.get_ai_response(
    ..., provider="deepseek") regardless of the site's global AI_PROVIDER
    default -- at this model's pricing this whole debate costs a fraction
    of a cent, versus Groq's shared 1,000-requests/day free-tier cap
    (which this feature alone could exhaust site-wide) or Claude's
    per-token cost at ~15-20x this feature's actual cost. (2026-07-20:
    ai_router._deepseek() now calls this model via DeepInfra rather than
    DeepSeek's own API -- same model, cheaper/simpler since the only key
    on hand is a DeepInfra one; see ai/ai_router.py's docstring there.)
  - 3 personas x 1 round + 1 arbiter synthesis = 4 sequential calls, not
    4 personas x 2 rounds = 8 -- half the latency/cost of the originally
    discussed design for the same "multiple viewpoints -> synthesis"
    value, since nothing about the feature's purpose requires a second
    rebuttal round.
  - Gated entirely behind DEEPINFRA_API_KEY being configured (see
    is_available()) -- the frontend hides this feature's entry point
    entirely when the key isn't set, rather than showing a button that
    would just error, per the user's "未能用先隱藏" instruction.

This is a genuinely more expensive/slower feature than everything else
on this page (4 sequential LLM calls vs. the page's usual pure-Python
scoring), so it is deliberately opt-in (a button the user clicks), never
auto-run on every search.
"""

import logging
import os
from typing import Dict

from ai import ai_router
from ai.ai_router import get_ai_response
from services.i18n import ai_language_instruction

logger = logging.getLogger(__name__)

_PROVIDER = "deepseek"
_MAX_TOKENS = 300  # keep each persona's argument short -- this is a quick read, not an essay


def is_available() -> bool:
    """DEEPINFRA_API_KEY must be configured -- see this module's docstring
    for why this feature is deliberately pinned to DeepSeek only."""
    return bool(os.getenv("DEEPINFRA_API_KEY"))


def _context_summary(symbol: str, context: Dict) -> str:
    """Renders the real data every persona argues from into plain text --
    same numbers already shown elsewhere on the page (confluence signals,
    regime, decision levels), never invented for this feature."""
    confluence = context.get("confluence") or {}
    regime = context.get("regime") or {}
    decision_levels = context.get("decision_levels") or {}
    lines = [
        f"股票代號：{symbol}",
        f"Confluence方向：{confluence.get('direction', '數據不足')}（信心度 {confluence.get('confidence_pct', '-')}%）",
        f"利好訊號：{'; '.join(confluence.get('bullish_signals', []) or ['無'])}",
        f"利淡訊號：{'; '.join(confluence.get('bearish_signals', []) or ['無'])}",
        f"市場regime：{regime.get('regime', '未知')}",
    ]
    if decision_levels:
        lines.append(
            f"現有Entry/Stop/Target：{decision_levels.get('entry')}/"
            f"{decision_levels.get('stop_loss')}/{decision_levels.get('take_profits')}"
        )
    return "\n".join(lines)


_PERSONA_PROMPTS = {
    "bull": "你係一個睇好嘅股票分析員（Bull）。淨係用返下面提供嘅真實數據，用2-3句講你點解睇好，唔好引用未提供嘅數據或者捏造數字。",
    "bear": "你係一個睇淡嘅股票分析員（Bear）。淨係用返下面提供嘅真實數據，用2-3句講你點解睇淡，唔好引用未提供嘅數據或者捏造數字。",
    "risk_manager": "你係一個風控經理（Risk Manager）。淨係用返下面提供嘅真實數據，用2-3句指出最大嘅風險係咩，唔好引用未提供嘅數據或者捏造數字。",
}


def run_debate(symbol: str, context: Dict, lang: str = None) -> Dict:
    """
    Returns:
        {"available": False, "message": "..."}  -- if DEEPINFRA_API_KEY isn't set
        {"available": True, "arguments": {...}, "verdict": "...", "error": None}
        {"available": True, "error": "..."}      -- if a call failed mid-debate

    2026-08-02 fix (task #611, "開始辯論...在用英文時顯示中文，跟進所有語言
    轉換"): this function used to hardcode its unavailable-message and
    disclaimer in Traditional Chinese, and never told the 4 underlying LLM
    calls what language to answer in at all -- so every Bull/Bear/Risk
    Manager argument and the Arbiter's verdict always came back in
    Cantonese regardless of the site's selected UI language. `lang` (the
    same I18N.currentLang code every other endpoint on this page already
    threads through) now does two things: (1) picks the Chinese vs English
    static string below (same is_zh_default convention used elsewhere in
    this codebase, e.g. api/ai_analysis.py's `conclusion` field) and (2) is
    passed through services/i18n.py's ai_language_instruction() helper --
    the exact same helper api/chat.py, api/company_compare.py,
    api/chart_analysis.py and api/news_denoise.py already use -- and
    appended to every persona/arbiter prompt so DeepSeek actually answers
    in the requested language instead of always defaulting to Chinese.

    2026-07-20 fix: this feature previously had ZERO resource accounting --
    api/agent_debate.py's endpoint took no token param and never called
    services/quota_middleware.py at all, so it rode entirely outside the
    site's token-quota system despite being a genuinely more expensive
    feature (4 sequential LLM calls vs. every other AI feature's single
    call). ai/ai_router.py's get_ai_response() only tracks the MOST
    RECENT call's usage in its shared _LAST_USAGE_TOKENS slot (see its
    docstring), so a single record_ai_token_usage() call after this
    function returns would have only captured the 4th (arbiter) call's
    tokens, silently dropping the other 3 personas' real cost. Fixed by
    summing every call's actual usage here into `total_tokens` and
    writing that real (not fabricated/multiplied) sum back into
    ai_router's shared slot just before returning, so the API layer's
    existing record_ai_token_usage(user_id) call (same pattern as
    api/chat.py) now bills the honest total. No arbitrary "5x" multiplier
    is applied -- the sum of 4 real calls already naturally costs ~4x a
    single-call feature, which correctly reflects this feature's real
    resource weight without inventing a number.
    """
    is_zh_default = not lang or lang in ("zh-HK", "zh-TW", "zh-CN")
    if not is_available():
        return {
            "available": False,
            "message": (
                "AI辯論功能需要設定 DEEPINFRA_API_KEY 先可以使用，暫時未開放。"
                if is_zh_default
                else "The AI Debate feature is not yet enabled."
            ),
        }

    # Empty for the Chinese default (the persona prompts below are already
    # written in Cantonese) -- only appended when a non-Chinese lang was
    # requested, same guard api/ai_analysis.py's is_zh_default check uses.
    lang_instruction = "" if is_zh_default else f" {ai_language_instruction(lang)}"

    summary = _context_summary(symbol, context)
    arguments = {}
    total_tokens = 0

    try:
        for persona, instruction in _PERSONA_PROMPTS.items():
            prompt = f"{instruction}{lang_instruction}\n\n真實數據：\n{summary}"
            arguments[persona] = get_ai_response(prompt, max_tokens=_MAX_TOKENS, provider=_PROVIDER).strip()
            total_tokens += ai_router.get_last_usage_tokens()

        arbiter_prompt = (
            "你係一個中立嘅仲裁者。下面有3個分析員嘅意見（Bull/Bear/Risk Manager），"
            "睇完之後用3-4句總結邊一方論點比較有數據支持，並且指出如果要跟，最需要留意嘅一點係咩。"
            f"唔好加入你自己未提供嘅新數據，只可以評論返3個分析員已經講嘅嘢。{lang_instruction}\n\n"
            f"Bull：{arguments['bull']}\n\n"
            f"Bear：{arguments['bear']}\n\n"
            f"Risk Manager：{arguments['risk_manager']}"
        )
        verdict = get_ai_response(arbiter_prompt, max_tokens=_MAX_TOKENS, provider=_PROVIDER).strip()
        total_tokens += ai_router.get_last_usage_tokens()

        # Overwrite the shared slot with the honest 4-call total so the
        # caller's record_ai_token_usage(user_id) bills the real cost,
        # not just this last arbiter call.
        ai_router.set_last_usage_tokens(total_tokens)

        return {
            "available": True,
            "arguments": arguments,
            "verdict": verdict,
            "disclaimer": (
                "以上由AI角色扮演生成，僅供參考角度，並非投資建議。"
                if is_zh_default
                else "The above is AI role-play generated content, for reference only -- not investment advice."
            ),
            "error": None,
        }
    except Exception as e:
        ai_router.set_last_usage_tokens(total_tokens)
        logger.info("agent_debate_service: debate failed for %s: %s", symbol, e)
        return {"available": True, "arguments": arguments or None, "verdict": None, "error": str(e)}
