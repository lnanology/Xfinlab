import math
from typing import Any

from fastapi.responses import JSONResponse


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


class SafeJSONResponse(JSONResponse):
    """
    2026-07-25 fix ("Analysis failed" / "Scan failed: Failed to fetch"):
    Railway's live deploy logs caught a real 500 on GET /api/pipeline/AAPL --
    ValueError: Out of range float values are not JSON compliant: nan --
    raised from Starlette's OWN JSONResponse.render(), which calls
    json.dumps(..., allow_nan=False) for strict JSON-spec compliance
    (unlike Python's json module, which defaults to allow_nan=True and
    would have silently written the literal `NaN` instead of crashing).

    Any stray NaN/Infinity float anywhere in a response body -- e.g.
    np.corrcoef() on a zero-variance price window in quant/tensor_network.py,
    or a 0/0 division in any of MasterPipeline's 17 intentionally-
    unvalidated quant/alpha/agent modules (see backend/core/
    master_pipeline.py) -- crashes the WHOLE request with a raw 500, which
    the browser then surfaces as "Analysis failed" / "Failed to fetch".

    Recursively replacing NaN/Infinity with null (None) BEFORE Starlette's
    strict encoder ever runs makes every endpoint using this as its
    default_response_class immune to this entire class of bug, present and
    future, instead of chasing it module-by-module through a large formula
    pipeline that's explicitly not meant to be individually hardened (its
    docstrings note the formulas themselves are unvalidated/uncalibrated
    reference-only output, not the JSON-encoding layer that wraps them).
    """

    def render(self, content: Any) -> bytes:
        return super().render(_sanitize(content))
