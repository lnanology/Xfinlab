from typing import Dict


class AnomalyEngine:
    """
    XFINLAB Anomaly Engine
    Detect unusual market activity
    """

    @staticmethod
    def detect(
        current_volume: float,
        average_volume: float,
        price_change_pct: float
    ) -> Dict:

        volume_ratio = (
            current_volume / average_volume
            if average_volume > 0
            else 1
        )

        anomalies = []

        if volume_ratio >= 2:
            anomalies.append("High Volume")

        if abs(price_change_pct) >= 5:
            anomalies.append("Large Price Move")

        anomaly_score = min(
            100,
            round(
                ((volume_ratio - 1) * 25)
                + abs(price_change_pct) * 5,
                2
            )
        )

        return {
            "anomaly_detected": len(anomalies) > 0,
            "anomaly_score": anomaly_score,
            "volume_ratio": round(volume_ratio, 2),
            "signals": anomalies
        }