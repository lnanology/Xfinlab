from fastapi import APIRouter

from engines.anomaly_engine import AnomalyEngine

router = APIRouter()


@router.get("/anomaly")
def anomaly():

    return AnomalyEngine.detect(
        current_volume=2500000,
        average_volume=900000,
        price_change_pct=6.8
    )