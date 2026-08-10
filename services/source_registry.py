"""
Source Registry — XFINLAB Architecture, Phase 1.

Central catalogue of every external data source XFINLAB pulls from, and
which internal service is responsible for talking to it. This exists so
that "which files touch Yahoo Finance?" or "what would we need to change
to swap market data providers?" becomes a lookup here instead of a grep
across the whole repo.

Works together with license_registry.py: this file answers "what/where",
license_registry answers "are we legally allowed to use it".

Pure bookkeeping — does not change any live request behaviour.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SourceRecord:
    source_id: str
    display_name: str
    category: str  # "market_data" | "news" | "crypto" | "vision_ai" | "text_ai"
    used_by: List[str] = field(default_factory=list)  # file paths that call it
    status: str = "active"  # "active" | "candidate" | "deprecated"
    notes: str = ""


_SOURCES: Dict[str, SourceRecord] = {
    "yahoo_finance": SourceRecord(
        source_id="yahoo_finance",
        display_name="Yahoo Finance (via yfinance)",
        category="market_data",
        used_by=[
            "services/market_data_service.py",
            "services/technical_analysis_service.py (fallback only — see alpaca_markets)",
        ],
        status="active",
        notes=(
            "See license_registry.get_license('yahoo_finance') for licensing "
            "risk. As of 2026-07, technical_analysis_service.py now tries "
            "Alpaca Markets first for US symbols; yfinance is the fallback "
            "there (non-US symbols, Alpaca not configured, or any Alpaca "
            "error). market_data_service.py (/api/market, /api/analyze) is "
            "still 100% yfinance — not yet migrated."
        ),
    ),
    # 2026-08-10: removed polygon_io/twelve_data/finnhub candidate entries
    # (never integrated, used_by=[] the whole time) as part of a full
    # cleanup dropping every non-commercial-use free-tier data source from
    # this codebase -- see services/license_registry.py's git history.
    "alpaca_markets": SourceRecord(
        source_id="alpaca_markets",
        display_name="Alpaca Markets (IEX feed)",
        category="market_data",
        used_by=["services/technical_analysis_service.py"],
        status="active",
        notes=(
            "Researched 2026-07. Free Data API, no brokerage account balance "
            "required. Terms explicitly permit displaying data to end users in "
            "a commercial app (unlike Twelve Data / Finnhub / Polygon free "
            "tiers, which are dev/internal-only). Limitation: US-listed "
            "symbols only (IEX feed) — does not cover HKEX/TWSE/TSE/European "
            "markets. Wired into technical_analysis_service.py behind "
            "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY env vars; falls back "
            "to yfinance automatically if those aren't set, or for any "
            "non-US symbol. Sign up at alpaca.markets to get free keys."
        ),
    ),
    "gemini_vision": SourceRecord(
        source_id="gemini_vision",
        display_name="Google Gemini 2.5 Flash (vision)",
        category="vision_ai",
        used_by=["ai/ai_router.py", "api/chart_analysis.py"],
        status="active",
        notes="Primary VISION_PROVIDER for chart image pattern recognition.",
    ),
    "groq": SourceRecord(
        source_id="groq",
        display_name="Groq (text + vision fallback)",
        category="text_ai",
        used_by=["ai/ai_router.py"],
        status="active",
        notes="AI_PROVIDER default; also VISION_PROVIDER fallback option.",
    ),
}


def get_source(source_id: str) -> Optional[SourceRecord]:
    return _SOURCES.get(source_id)


def list_sources(category: Optional[str] = None) -> List[SourceRecord]:
    if category is None:
        return list(_SOURCES.values())
    return [s for s in _SOURCES.values() if s.category == category]


def list_candidates(category: Optional[str] = None) -> List[SourceRecord]:
    """Sources registered as replacement candidates but not yet wired in."""
    return [
        s for s in list_sources(category)
        if s.status == "candidate"
    ]


def register_source(record: SourceRecord) -> None:
    _SOURCES[record.source_id] = record


if __name__ == "__main__":
    for s in list_sources("market_data"):
        print(f"[{s.status}] {s.display_name} — used by: {s.used_by or '(none yet)'}")
