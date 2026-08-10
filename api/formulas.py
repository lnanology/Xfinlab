"""
Formula Engine API (task #773, follows services/formula_engine.py +
services/formula_catalog.py from task #772). Exposes the ~70-formula
library (technical indicators, risk/performance metrics, options pricing,
portfolio theory, time-value-of-money, statistics, market-structure math)
both as a browsable catalog and as a callable compute endpoint, so other
XFINLAB engines/products -- and, per the Intelligence API precedent in
api/intelligence.py, third-party developers -- can call a named formula
by ID with plain JSON params instead of re-deriving the same math.

Three endpoints:
  GET  /api/formulas                    -> full catalog grouped by category
  GET  /api/formulas/{formula_id}       -> one formula's metadata
  POST /api/formulas/compute/{formula_id} -> run it, return the result

compute deliberately takes a generic dict of kwargs (validated against
the target function's own real signature via FORMULA_REGISTRY, not a
duplicated schema) rather than one Pydantic model per formula -- with 70
formulas spanning wildly different signatures (single floats, price-array
sequences, 2D covariance matrices), one shared request shape keeps this
endpoint maintainable as the library grows.
"""

import inspect

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict

from services.formula_catalog import FORMULA_CATALOG, FORMULA_REGISTRY, CATEGORIES, get_catalog_by_category

router = APIRouter()


class ComputeRequest(BaseModel):
    params: Dict[str, Any] = {}


@router.get("/formulas")
def list_formulas():
    """Full catalog, grouped by category -- what formula-engine.html renders."""
    return {"categories": CATEGORIES, "grouped": get_catalog_by_category(), "count": len(FORMULA_CATALOG)}


@router.get("/formulas/{formula_id}")
def get_formula(formula_id: str):
    """Metadata (params, description, category) for one formula by ID."""
    entry = next((e for e in FORMULA_CATALOG if e["id"] == formula_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Unknown formula_id")
    return entry


@router.post("/formulas/compute/{formula_id}")
def compute_formula(formula_id: str, body: ComputeRequest):
    """Runs one formula with the given kwargs, returns its result.
    400 on a bad/missing required param (surfaced as the underlying
    TypeError message -- e.g. "missing a required argument: 'strike'" --
    which is specific enough for API callers to fix their request without
    needing a hand-written validator per formula)."""
    func = FORMULA_REGISTRY.get(formula_id)
    if not func:
        raise HTTPException(status_code=404, detail="Unknown formula_id")
    try:
        sig = inspect.signature(func)
        sig.bind(**body.params)
    except TypeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        result = func(**body.params)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Computation error: {e}")
    return {"formula_id": formula_id, "result": result}
