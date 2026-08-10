"""
Formula Catalog (task #773, follows services/formula_engine.py from task
#772). Builds the public, human-readable directory of every formula in
formula_engine.py -- used by api/formulas.py's GET /api/formulas listing
and by formula-engine.html's catalog page.

Rather than hand-maintain a second copy of each formula's name/params/
description (which would drift out of sync with formula_engine.py the
first time someone adds or edits a formula there), this module
introspects formula_engine.py directly via `inspect`: parameter names,
types, and defaults come from each function's real signature, and the
one-line description comes from the first line of its docstring. The
only thing that genuinely can't be introspected -- which of the 7
sections a formula belongs to -- is the one hand-maintained mapping
below (_CATEGORY_MAP), matching formula_engine.py's own section comments.

Also builds an ID-keyed lookup (FORMULA_REGISTRY) so api/formulas.py's
POST /api/formulas/compute/{formula_id} endpoint can resolve a formula_id
string straight to the actual callable, without a second hardcoded
if/elif dispatch table to keep in sync.
"""

import inspect

from services import formula_engine as fe

_CATEGORY_MAP = {
    "sma": "technical", "ema": "technical", "wma": "technical", "rsi": "technical",
    "macd": "technical", "bollinger_bands": "technical", "stochastic_oscillator": "technical",
    "atr": "technical", "adx": "technical", "cci": "technical", "williams_r": "technical",
    "obv": "technical", "vwap": "technical", "money_flow_index": "technical",
    "rate_of_change": "technical", "parabolic_sar": "technical", "donchian_channel": "technical",
    "keltner_channel": "technical",

    "sharpe_ratio": "risk", "sortino_ratio": "risk", "treynor_ratio": "risk",
    "calmar_ratio": "risk", "max_drawdown": "risk", "value_at_risk_historical": "risk",
    "value_at_risk_parametric": "risk", "conditional_value_at_risk": "risk",
    "beta_coefficient": "risk", "jensens_alpha": "risk", "information_ratio": "risk",
    "annualized_volatility": "risk", "downside_deviation": "risk", "r_squared": "risk",
    "ulcer_index": "risk",

    "black_scholes": "options", "black_scholes_greeks": "options",
    "binomial_option_price": "options", "put_call_parity": "options",
    "implied_volatility": "options",

    "capm_expected_return": "portfolio", "portfolio_variance_two_asset": "portfolio",
    "portfolio_return": "portfolio", "portfolio_variance": "portfolio",
    "kelly_criterion": "portfolio", "fama_french_3factor": "portfolio",
    "min_variance_weights_two_asset": "portfolio", "covariance_matrix": "portfolio",

    "present_value": "tvm", "future_value": "tvm", "net_present_value": "tvm",
    "internal_rate_of_return": "tvm", "cagr": "tvm", "compound_interest": "tvm",
    "loan_payment": "tvm", "gordon_growth_model": "tvm", "discounted_cash_flow": "tvm",

    "z_score": "stats", "normal_pdf": "stats", "normal_cdf": "stats",
    "linear_regression": "stats", "pearson_correlation": "stats", "standard_error": "stats",
    "confidence_interval": "stats", "monte_carlo_gbm": "stats", "kalman_filter_1d": "stats",
    "garch_1_1_variance": "stats",

    "fibonacci_retracement": "structure", "fibonacci_extension": "structure",
    "pivot_points_classic": "structure", "pivot_points_camarilla": "structure",
    "regression_channel": "structure",
}

CATEGORIES = {
    "technical": {"label": "Technical Indicators", "label_zh": "技術指標"},
    "risk": {"label": "Risk & Performance Metrics", "label_zh": "風險與表現指標"},
    "options": {"label": "Options Pricing & Derivatives", "label_zh": "期權定價與衍生工具"},
    "portfolio": {"label": "Portfolio Theory", "label_zh": "投資組合理論"},
    "tvm": {"label": "Time Value of Money", "label_zh": "資金時間價值"},
    "stats": {"label": "Statistics & Probability", "label_zh": "統計與概率"},
    "structure": {"label": "Market Structure / Chart Math", "label_zh": "市場結構與圖表數學"},
}

_TYPE_LABELS = {
    "float": "number", "int": "number", "str": "string", "bool": "boolean",
}


def _param_type(annotation) -> str:
    if annotation is inspect.Parameter.empty:
        return "number"
    name = getattr(annotation, "__name__", str(annotation))
    if "Sequence" in str(annotation) or "list" in str(annotation).lower():
        return "array"
    return _TYPE_LABELS.get(name, "number")


def _build_catalog():
    entries = []
    registry = {}
    for name, func in inspect.getmembers(fe, inspect.isfunction):
        if name.startswith("_") or name not in _CATEGORY_MAP:
            continue
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or ""
        first_line = doc.split("\n")[0].strip()
        description = " ".join(doc.split())  # full docstring, whitespace-normalized
        params = []
        for pname, p in sig.parameters.items():
            params.append({
                "name": pname,
                "type": _param_type(p.annotation),
                "required": p.default is inspect.Parameter.empty,
                "default": None if p.default is inspect.Parameter.empty else p.default,
            })
        entry = {
            "id": name,
            "label": name.replace("_", " ").title(),
            "category": _CATEGORY_MAP[name],
            "summary": first_line,
            "description": description,
            "params": params,
        }
        entries.append(entry)
        registry[name] = func
    entries.sort(key=lambda e: (e["category"], e["id"]))
    return entries, registry


FORMULA_CATALOG, FORMULA_REGISTRY = _build_catalog()


def get_catalog_by_category() -> dict:
    """Returns {category_id: {label, label_zh, formulas: [...]}} -- the
    shape formula-engine.html renders directly, one section per category."""
    out = {cid: {**meta, "formulas": []} for cid, meta in CATEGORIES.items()}
    for entry in FORMULA_CATALOG:
        out[entry["category"]]["formulas"].append(entry)
    return out
