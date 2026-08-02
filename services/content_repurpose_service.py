"""
Content repurposing service -- "Level 1: Content Leverage" from the
2026-07-27 growth-strategy discussion ("一篇內容,可變成數十個曝光點").

Turns the SAME real daily top-signals data that already powers
free-signals.html + the Telegram daily push (api/market_pulse.py's
_compute_free_signals()/_notify_free_signals_ready(), services/
telegram_push_service.py) into ready-to-copy-paste post text for
platforms XFINLAB has no direct posting API/OAuth app for yet: X/
Twitter, Threads, LinkedIn, Facebook, plus an email newsletter draft and
a mobile push notification pair.

Deliberately does NOT post anywhere itself -- there's no Meta/X/LinkedIn
developer app or OAuth token on file for this project, and auto-posting
to public social accounts requires the account owner to review/approve
each post, not something to automate silently. This module only
generates the text; a human (AJ) copies it from the admin panel into
each platform's own composer. If/when real posting API access exists
for a given platform, that platform's text variant here is already in
the exact shape needed -- only a "post it" call needs adding then, the
copy itself doesn't change.

Anti-fabrication note (consistent with the rest of this codebase): every
number here (ticker, price direction, confidence %) comes straight from
the same real technical-analysis signals object already served by /api/
free-signals -- nothing here is invented or AI-hallucinated text dressed
up as data.
"""
import json
import os
import sqlite3
from datetime import date

from services.telegram_push_service import _tr, _LABEL_KEYS, _DIRECTION_KEYS

SITE_URL = "https://www.xfinlab.com"
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _get_db():
    return sqlite3.connect(_DB_PATH)


def _ensure_table():
    conn = _get_db()
    try:
        # 2026-07-27: persisted so the admin panel can show "today's ready
        # -to-post content" even after a process restart (in-memory-only
        # would lose it on every Railway redeploy) -- same rationale as
        # services/push_service.py's push_send_log table.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS content_variants_log (
                log_date TEXT PRIMARY KEY,
                variants_json TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_variants(date_str: str, variants: dict) -> None:
    _ensure_table()
    conn = _get_db()
    try:
        conn.execute(
            """
            INSERT INTO content_variants_log (log_date, variants_json)
            VALUES (?, ?)
            ON CONFLICT(log_date) DO UPDATE SET variants_json = excluded.variants_json
            """,
            (date_str, json.dumps(variants, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_variants() -> dict:
    """Read-only lookup for the admin panel: today's variants if they
    exist, otherwise the most recently generated day's (e.g. right after
    a fresh deploy before today's daily job has run yet) rather than a
    blank screen. Returns {"available": False} if nothing has ever been
    generated."""
    _ensure_table()
    conn = _get_db()
    try:
        today_str = date.today().isoformat()
        row = conn.execute(
            "SELECT variants_json FROM content_variants_log WHERE log_date = ?",
            (today_str,),
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT variants_json FROM content_variants_log ORDER BY log_date DESC LIMIT 1"
            ).fetchone()
        if not row:
            return {"available": False}
        return json.loads(row[0])
    finally:
        conn.close()


def _dir_emoji(raw_direction: str) -> str:
    if raw_direction == "偏多":
        return "🟢"
    if raw_direction == "偏空":
        return "🔴"
    return "⚪"


_CONFIDENCE_LABEL = {"zh": "信心度", "en": "confidence", "es": "confianza"}


def _signal_plain_line(sig: dict, lang: str = "zh") -> str:
    """Same information as telegram_push_service._fmt_signal_line(), but
    without Telegram's Markdown asterisks -- X/LinkedIn/Facebook/Threads
    don't render Markdown, so a literal `*NVDA*` would show up as junk
    asterisks in the actual post.

    2026-08-02 fix: the "confidence" label word itself used to be
    hardcoded Chinese ("信心度") regardless of `lang`, so an "en"-language
    line like the Reddit variant would read "Bullish（信心度 82%）" --
    correct ticker/direction translation, wrong label word. Now looked up
    per-language same as everything else here, falling back to the
    Chinese word for any language not in _CONFIDENCE_LABEL (matches _tr's
    own fallback-to-raw philosophy elsewhere in this file)."""
    ticker = sig.get("ticker", "?")
    raw_label = sig.get("label") or sig.get("asset_class_label") or ""
    raw_direction = sig.get("confluence_direction", "")
    conf = sig.get("confluence_confidence_pct")
    conf_str = f"{conf}%" if conf is not None else "N/A"
    label = _tr(raw_label, _LABEL_KEYS, lang)
    direction = _tr(raw_direction, _DIRECTION_KEYS, lang)
    conf_label = _CONFIDENCE_LABEL.get(lang, _CONFIDENCE_LABEL["zh"])
    # Individual stock tickers (NVDA, TSLA...) have no entry in _LABEL_KEYS
    # (that map only covers indices/futures/crypto shorthand), so `label`
    # falls back to the raw ticker itself -- printing "NVDA NVDA — ..."
    # would be a redundant-looking duplication a human editor would never
    # write. Only show the label when it adds real information.
    name_part = ticker if not label or label == ticker else f"{ticker} {label}"
    return f"{_dir_emoji(raw_direction)} {name_part} — {direction}（{conf_label} {conf_str}）"


def generate_content_variants(cache: dict, lang: str = "zh") -> dict:
    """Build every platform's ready-to-copy text from today's
    free-signals cache (see api/market_pulse.py's _compute_free_signals()
    -- same dict shape: {"date": ..., "signals": [...]}).

    Returns {"available": False} if there are no signals today (e.g. a
    data outage) rather than generating misleading empty-handed copy.
    """
    signals = (cache.get("signals") or [])[:3]
    date_str = cache.get("date") or date.today().isoformat()

    if not signals:
        return {"available": False, "date": date_str}

    top = signals[0]
    top_line = _signal_plain_line(top, lang)
    all_lines = [_signal_plain_line(s, lang) for s in signals]
    link = f"{SITE_URL}/free-signals.html"
    disclaimer = "⚠️ 僅供參考，不構成投資建議。"

    # X / Twitter -- hard 280-character ceiling, so build short and
    # truncate defensively as a last resort (should never actually need
    # to truncate given how short top_line is in practice).
    twitter = (
        f"🎯 今日焦點 {date_str}\n"
        f"{top_line}\n\n"
        f"完整AI分析（免費）👉 {link}\n"
        f"#投資 #股票 #AI分析"
    )
    if len(twitter) > 280:
        twitter = twitter[:277] + "..."

    # Threads -- same voice as X, slightly more room (Threads' limit is
    # 500 chars), so include the #2 signal too when there's space.
    threads = (
        f"🎯 今日焦點 {date_str}\n"
        + "\n".join(all_lines[:2])
        + f"\n\n完整AI分析（免費）👉 {link}\n#投資 #股票 #AI分析"
    )

    # Facebook -- casual, all 3 signals, slightly warmer opening line.
    facebook = (
        f"📊 XFINLAB 每日免費訊號 — {date_str}\n\n"
        + "\n".join(all_lines)
        + f"\n\n呢啲全部係即市真實技術數據，唔係憑估。免費睇齊全部分析：{link}\n\n{disclaimer}"
    )

    # LinkedIn -- longer-form, professional tone, brief methodology note
    # (LinkedIn audiences respond to credibility/process signals).
    linkedin = (
        f"XFINLAB 每日市場訊號 — {date_str}\n\n"
        f"今日技術面信心度最高的標的：\n\n"
        + "\n".join(all_lines)
        + "\n\n"
        "以上排名based on即市技術分析（趨勢、動能、成交量confluence），"
        "並非人手篩選或AI憑空生成。\n\n"
        f"完整每日訊號（免費）：{link}\n\n{disclaimer}"
    )

    email_subject = f"XFINLAB 每日訊號：{_tr(top.get('label') or top.get('ticker', ''), _LABEL_KEYS, lang)} 今日信心度最高"
    email_body = (
        f"你好，\n\n以下係XFINLAB今日（{date_str}）技術面信心度最高嘅標的：\n\n"
        + "\n".join(all_lines)
        + f"\n\n即市睇齊完整分析同埋歷史數據：{link}\n\n{disclaimer}\n\nXFINLAB 團隊"
    )

    push_title = "📊 今日訊號已更新"
    push_body = f"{top_line[:60]}… 立即睇" if len(top_line) > 60 else f"{top_line} 立即睇"

    # 2026-08-02 (Growth OS Phase 2): Instagram/Discord/Reddit variants,
    # added on top of the original 4 platforms + email/push. Same
    # copy-paste-only philosophy as the rest of this file -- no auto-
    # posting, no OAuth app on file for any of these three either.
    instagram = (
        f"📊 XFINLAB 每日免費訊號 — {date_str}\n\n"
        + "\n".join(all_lines)
        + f"\n\n真實即市技術數據，唔係AI憑空估。免費睇齊全部分析 👉 連結在個人簡介\n\n{disclaimer}\n"
        "#投資 #股票 #AI分析 #XFINLAB #Fintech"
    )

    # Discord -- announcement-channel voice, slightly more compact than
    # Facebook/LinkedIn since Discord readers scan fast in a feed of many
    # servers' messages.
    discord = (
        f"**📊 XFINLAB 每日訊號 — {date_str}**\n"
        + "\n".join(all_lines)
        + f"\n\n完整分析（免費）：{link}\n{disclaimer}"
    )

    # Reddit -- title/body kept separate (Reddit's submission form has two
    # fields). Body is deliberately more measured/informational than the
    # other platforms' promo tone, since most finance subreddits' rules
    # explicitly penalize hype-y self-promotion; this reads like a
    # findings post, not an ad. Always in English regardless of `lang`
    # (English-language subreddits are the realistic distribution target
    # for this format) -- reusing `all_lines` here would leak untranslated
    # Chinese ticker labels/directions into an English post whenever this
    # function is called with the default lang="zh".
    reddit_lines = [_signal_plain_line(s, "en") for s in signals]
    reddit_title = f"Today's highest-confidence technical signals ({date_str}) — free daily scan"
    reddit_body = (
        f"Ran today's confluence scan across the usual watchlist. Highest-confidence names:\n\n"
        + "\n".join(reddit_lines)
        + f"\n\nMethodology: real-time technical confluence (trend/momentum/volume), not AI-generated guesses. "
        f"Full breakdown (free, no signup for this page): {link}\n\n"
        "Not financial advice -- posting for discussion/feedback."
    )

    return {
        "available": True,
        "date": date_str,
        "twitter": twitter,
        "threads": threads,
        "facebook": facebook,
        "linkedin": linkedin,
        "instagram": instagram,
        "discord": discord,
        "reddit_title": reddit_title,
        "reddit_body": reddit_body,
        "email_subject": email_subject,
        "email_body": email_body,
        "push_title": push_title,
        "push_body": push_body,
    }


# 2026-08-02 (Growth OS Phase 2): scaffold phrases for the two languages
# that already have a real, live distribution channel on this site
# (services/telegram_push_service.py's EN/ES Telegram channels) --
# deliberately NOT all 47 i18n languages, because unlike the website UI
# (where every language has real visiting users) there is no actual
# audience yet for e.g. a Hindi or Arabic X/Facebook post. Scoping this to
# the languages that already have a live channel avoids generating dozens
# of variants nobody will ever post, while still making it a one-line
# change to add a language here once a new channel exists for it.
_SCAFFOLD = {
    "en": {
        "focus": "🎯 Today's Top Signal",
        "full_analysis": "Full AI analysis (free)",
        "disclaimer": "⚠️ For informational purposes only, not investment advice.",
        "daily_title": "XFINLAB Daily Free Signals",
        "methodology": "Ranking based on live technical analysis (trend, momentum, volume confluence) -- not hand-picked or AI-invented.",
        "hashtags": "#investing #stocks #AI",
        "intro": "Here's today's highest-confidence signal, straight from real-time technical data:",
    },
    "es": {
        "focus": "🎯 Señal Destacada de Hoy",
        "full_analysis": "Análisis completo de IA (gratis)",
        "disclaimer": "⚠️ Solo con fines informativos, no es asesoría de inversión.",
        "daily_title": "Señales Gratuitas Diarias de XFINLAB",
        "methodology": "Clasificación basada en análisis técnico en tiempo real (tendencia, momentum, volumen) -- no elegido a mano ni inventado por IA.",
        "hashtags": "#inversión #acciones #IA",
        "intro": "Esta es la señal de mayor confianza de hoy, directamente de datos técnicos en tiempo real:",
    },
}


def generate_content_variants_multilang(cache: dict, langs=("zh", "en", "es")) -> dict:
    """Growth OS Phase 2: fan out the same real signals data into
    per-language social variants. "zh" reuses generate_content_variants()
    as-is (it already is the Chinese-first original). "en"/"es" translate
    ticker labels + direction via the same i18n keys the Telegram push
    already uses (services/telegram_push_service._tr), plus localized
    scaffold text from _SCAFFOLD above -- so a French or Hindi request
    here intentionally isn't supported yet (see _SCAFFOLD's comment)."""
    signals = (cache.get("signals") or [])[:3]
    date_str = cache.get("date") or date.today().isoformat()
    out = {}
    for lang in langs:
        if lang == "zh":
            out["zh"] = generate_content_variants(cache, lang="zh")
            continue
        scaffold = _SCAFFOLD.get(lang)
        if not scaffold or not signals:
            out[lang] = {"available": False, "date": date_str}
            continue
        lines = [_signal_plain_line(s, lang) for s in signals]
        link = f"{SITE_URL}/free-signals.html"
        twitter = f"{scaffold['focus']} {date_str}\n{lines[0]}\n\n{scaffold['full_analysis']} 👉 {link}\n{scaffold['hashtags']}"
        if len(twitter) > 280:
            twitter = twitter[:277] + "..."
        facebook = (
            f"📊 {scaffold['daily_title']} — {date_str}\n\n"
            + "\n".join(lines)
            + f"\n\n{scaffold['intro']} {link}\n\n{scaffold['disclaimer']}"
        )
        linkedin = (
            f"{scaffold['daily_title']} — {date_str}\n\n"
            + "\n".join(lines)
            + f"\n\n{scaffold['methodology']}\n\nFull daily signals (free): {link}\n\n{scaffold['disclaimer']}"
        )
        out[lang] = {
            "available": True,
            "date": date_str,
            "twitter": twitter,
            "facebook": facebook,
            "linkedin": linkedin,
        }
    return out
