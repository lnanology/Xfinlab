
import numpy as np

class TensorNetwork:
    @staticmethod
    def compute(matrix):
        m = np.array(matrix)
        # 2026-07-25 fix: np.corrcoef() divides by each row's own stddev, so
        # a zero-variance row (e.g. a price series that's flat/duplicated
        # over the window, which real OHLC data occasionally produces on a
        # thin-history ticker) yields a divide-by-zero -> NaN correlation.
        # That NaN used to flow straight through into "market_link", which
        # api/pipeline_api.py exposes directly as market_correlation in the
        # API response -- and Starlette's JSONResponse (allow_nan=False)
        # raises a hard ValueError on any NaN float, crashing the whole
        # request with a 500 ("Analysis failed"/"Failed to fetch" on the
        # frontend). nan_to_num() maps the undefined case to 0 (no
        # measurable correlation) instead of letting it become a live
        # 500 -- see also services/safe_json.py for the same class of bug
        # guarded at the response-encoding layer, belt-and-braces.
        corr = np.nan_to_num(np.corrcoef(m), nan=0.0, posinf=1.0, neginf=-1.0)
        return {"tensor_shape": list(corr.shape), "market_link": float(np.mean(np.abs(corr)))}
