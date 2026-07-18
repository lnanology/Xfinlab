from fastapi import APIRouter, HTTPException
from services.decision_journal_service import DecisionJournalService
from backend.auth.jwt_handler import verify_token

router = APIRouter()


@router.post("/decision-journal/add/{symbol}")
def add_journal_entry(symbol: str, token: str, body: dict):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return DecisionJournalService.add(payload["id"], symbol, body)


@router.get("/decision-journal")
def get_journal(token: str):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    entries = DecisionJournalService.get_all(payload["id"])
    return {"status": "ok", "entries": entries}


@router.delete("/decision-journal/{entry_id}")
def remove_journal_entry(entry_id: int, token: str):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return DecisionJournalService.remove(payload["id"], entry_id)
