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
            "services/technical_analysis_service.py",
        ],
        status="active",
        notes="See license_registry.get_license('yahoo_finance') for licensing risk.",
    ),
    "polygon_io": SourceRecord(
        source_id="polygon_io",
        display_name="Polygon.io",
        category="market_data",
        used_by=[],
        status="candidate",
        notes="Commercial-license-friendly candidate replacement for Yahoo Finance. Not yet integrated.",
    ),
    "twelve_data": SourceRecord(
        source_id="twelve_data",
        display_name="Twelve Data",
        category="market_data",
        used_by=[],
        status="candidate",
        notes="Commercial-license-friendly candidate replacement for Yahoo Finance. Not yet integrated.",
    ),
    "finnhub": SourceRecord(
        source_id="finnhub",
        display_name="Finnhub",
        category="market_data",
        used_by=[],
        status="candidate",
        notes="Commercial-license-friendly candidate replacement for Yahoo Finance. Not yet integrated.",
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
