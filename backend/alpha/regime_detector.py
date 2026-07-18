"""
Market Regime Detector -- classifies current market conditions from real,
already-computed signals instead of a single volatility number.

Step 2 of the Strategy Intelligence roadmap (2026-07-18): the previous
version of this file only ever looked at `volatility` and returned one of
HIGH_VOLATILITY / LOW_VOLATILITY / NORMAL. That's structurally unable to
tell a strong bull trend from a panic selloff from directionless chop --
all three can carry the same "volatility" reading. This version adds
trend direction + confidence (from TechnicalAnalysisService's Confluence
Engine, see services/technical_analysis_service.py's `_confluence()`) and
volume-vs-20-day-average (already computed there too, as `volume_ratio`)
as additional inputs. No new data source, no fabricated numbers -- every
input here is something the codebase was already computing and simply
wasn't being passed through to this classifier.

Deliberately NOT included: an "EVENT_DRIVEN" regime bucket. Detecting a
genuine news/event-driven regime honestly needs a historical baseline for
"normal" news volume per ticker to compare against, which doesn't exist
in this codebase yet -- guessing a threshold would be exactly the kind of
fabricated-looking-precise number this codebase avoids elsewhere. Same
reasoning kept "TREND_REVERSAL" as a secondary flag (driven by a real
Market Structure Engine CHOCH event) rather than inventing it as a
standalone primary regime with no reliable trigger condition.
"""

from typing import Dict, List


class RegimeDetector:

    # agree_ratio >= 0.6 (i.e. confidence_pct >= 60) is what
    # TechnicalAnalysisService._confluence() itself already calls "高"
    # (high) confidence -- reused here rather than inventing a new
    # threshold, so "strong" means the same thing everywhere in the
    # codebase.
    STRONG_CONFIDENCE_PCT = 60.0
    HIGH_VOLATILITY_THRESHOLD = 70.0
    LOW_VOLATILITY_THRESHOLD = 30.0
    LOW_LIQUIDITY_VOLUME_RATIO = 0.5

    @classmethod
    def detect(cls, market_data: Dict) -> str:
        """
        Backward-compatible entry point -- existing callers (e.g.
        backend/core/master_pipeline.py) only ever read a single regime
        string. Kept unchanged so nothing importing RegimeDetector.detect()
        breaks; new callers that want the full picture (secondary flags,
        the real inputs behind the label) should call classify() instead.
        """
        return cls.classify(market_data)["regime"]

    @classmethod
    def classify(cls, market_data: Dict) -> Dict:
        """
        Full multi-factor classification.

        Expected market_data keys (all optional -- missing ones fall back
        to neutral defaults rather than erroring):
          volatility            0-100 realized volatility (as before)
          trend_direction        '偏多' / '偏空' / anything else = neutral
                                  (straight from Confluence Engine's
                                  `direction` field)
          trend_confidence_pct   0-100 (Confluence Engine's `confidence_pct`)
          volume_ratio           latest volume / 20-day average volume
          structure_event        'BOS' / 'CHOCH' / 'liquidity_sweep' / None
                                  (Market Structure Engine's most recent
                                  event type, if any)
        """
        volatility = market_data.get("volatility", 50) or 50
        direction = market_data.get("trend_direction")
        confidence_pct = market_data.get("trend_confidence_pct", 0) or 0
        volume_ratio = market_data.get("volume_ratio")
        structure_event = market_data.get("structure_event")

        strong = confidence_pct >= cls.STRONG_CONFIDENCE_PCT
        high_vol = volatility >= cls.HIGH_VOLATILITY_THRESHOLD

        if direction == "偏多":
            if high_vol and strong:
                regime = "EUPHORIA"        # 狂熱
            elif high_vol:
                regime = "HIGH_VOLATILITY"  # 高波動
            elif strong:
                regime = "STRONG_BULLISH"   # 強勢多頭
            else:
                regime = "WEAK_BULLISH"     # 弱勢多頭
        elif direction == "偏空":
            if high_vol and strong:
                regime = "PANIC"            # 恐慌
            elif high_vol:
                regime = "HIGH_VOLATILITY"  # 高波動
            elif strong:
                regime = "STRONG_BEARISH"   # 強勢空頭
            else:
                regime = "WEAK_BEARISH"     # 弱勢空頭
        else:
            # neutral / '訊號分歧，中性' / '數據不足' -- no real directional
            # bias to report, so don't force one.
            regime = "HIGH_VOLATILITY" if high_vol else "RANGING"  # 區間震盪

        secondary_flags: List[str] = []
        if volume_ratio is not None and volume_ratio < cls.LOW_LIQUIDITY_VOLUME_RATIO:
            secondary_flags.append("LOW_LIQUIDITY")  # 流動性不足
            if regime == "RANGING":
                regime = "LOW_LIQUIDITY"
        if structure_event == "CHOCH":
            secondary_flags.append("TREND_REVERSAL_WATCH")  # 趨勢反轉觀察

        return {
            "regime": regime,
            "secondary_flags": secondary_flags,
            # Real inputs behind the label, for any caller/UI that wants to
            # show its working instead of just a bare tag.
            "inputs": {
                "volatility": volatility,
                "trend_direction": direction,
                "trend_confidence_pct": confidence_pct,
                "volume_ratio": volume_ratio,
                "structure_event": structure_event,
            },
        }
