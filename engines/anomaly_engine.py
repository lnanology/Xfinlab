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

        severity = "HIGH" if len(anomalies) >= 2 else "MEDIUM" if len(anomalies) == 1 else "NONE"

        return {
            "volume_ratio": volume_ratio,
            "price_change_pct": price_change_pct,
            "anomalies": anomalies,
            "anomaly_count": len(anomalies),
            "severity": severity
        }
