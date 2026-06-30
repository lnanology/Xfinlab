from fastapi import APIRouter

from engines.event_engine import EventEngine

router = APIRouter()

engine = EventEngine()


@router.get("/event/{event_type}")
def get_event(event_type: str):

    return engine.analyze_event(event_type)