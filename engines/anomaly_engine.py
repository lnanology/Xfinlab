from typing import Dict

class AnomalyEngine:
    """XFINLAB Anomaly Engine - Detects unusual market activity"""

    @staticmethod
    def detect(current_volume: float, average_volume: float, price_change_pct: float) -> Dict:
        volume_ratio = round(current_volume / average_volume, 2) if average_volume > 0 else 1.0
        anomalies = []

        if volume_ratio > 2.0:
            anomalies.append({"type": "volume_spike", "detail": f"Volume {volume_ratio}x above average"})

        if abs(price_change_pct) > 5.0:
            direction = "up" if price_change_pct > 0 else "down"
            anomalies.append({"type": "price_spike", "detail": f"Price moved {price_change_pct}% {direction}"})

        if volume_ratio > 2.0 and abs(price_change_pct) > 5.0:
            anomalies.append({"type": "combined_signal", "detail": "High volume + large price move detected"})

        # 2026-09-14 addition (AJ: "XFINLAB 量縮信號有嗎" -- confirmed there
        # was no volume-CONTRACTION signal at all, only the volume_spike
        # check above; this adds the missing other half. 0.5x is the
        # symmetric mirror of volume_spike's 2.0x threshold (same distance
        # on a log scale: 2x above / 2x below average), not an arbitrary
        # second number. `average_volume > 0` guard matches the ratio
        # calculation above -- avoids a false "contraction" read on a
        # symbol with no real average-volume data yet.
        if average_volume > 0 and volume_ratio < 0.5:
            anomalies.append({"type": "volume_contraction", "detail": f"Volume {volume_ratio}x below average -- possible consolidation/dry-up (量縮)"})

        # Classic pre-breakout "量縮盤整" read -- low volume AND a tight
        # price range together (not just either alone) is the actual
        # tradeable setup (cf. Minervini's VCP / Chinese TA "量縮價穩"):
        # the stock is quietly building a base rather than just being an
        # illiquid non-story on a random quiet day. 1.0% mirrors
        # combined_signal's use of the price-spike check above, just at
        # the opposite (tight, not wide) end of the price-move scale.
        if average_volume > 0 and volume_ratio < 0.5 and abs(price_change_pct) < 1.0:
            anomalies.append({"type": "consolidation_signal", "detail": f"Low volume ({volume_ratio}x avg) + tight price range ({price_change_pct}%) -- possible pre-breakout quiet phase"})

        severity = "HIGH" if len(anomalies) >= 2 else "MEDIUM" if len(anomalies) == 1 else "NONE"

        return {
            "volume_ratio": volume_ratio,
            "price_change_pct": price_change_pct,
            "anomalies": anomalies,
            "anomaly_count": len(anomalies),
            "severity": severity
        }
