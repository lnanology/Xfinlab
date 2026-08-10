"""
Formula Catalog (task #773, extended in task #779 per AJ: "建議的全加入
我要生產比市場更強的去賺錢" -- adding the license-vetted QuantLib and
SymPy modules from task #776-778). Builds the public, human-readable
directory of every formula across all Formula Engine modules -- used by
api/formulas.py's GET /api/formulas listing and by formula-engine.html's
catalog page.

Rather than hand-maintain a second copy of each formula's name/params/
description (which would drift out of sync with the source modules the
first time someone adds or edits a formula there), this module
introspects each module directly via `inspect`: parameter names, types,
and defaults come from each function's real signature, and the one-line
summary comes from the first line of its docstring. The only thing that
genuinely can't be introspected -- which category a formula belongs to --
is the one hand-maintained mapping below (_CATEGORY_MAP), matching each
module's own section comments.

Pulls from THREE modules:
  - services.formula_engine        -- stdlib-only, always available (70
    formulas: technical/risk/options/portfolio/tvm/stats/structure)
  - services.formula_engine_quantlib -- fixed_income + advanced options,
    requires the `QuantLib` package (Modified BSD, verified commercial-
    safe -- see that module's docstring)
  - services.formula_engine_symbolic -- solver (reverse-solve) formulas,
    requires the `sympy` package (BSD, verified commercial-safe)

The two optional modules are imported in a try/except: if QuantLib or
sympy aren't installed in a given environment, that category simply
doesn't appear in the catalog instead of crashing the whole Formula
Engine (and by extension, the whole backend, since backend/main.py
imports api/formulas.py at startup).

Also builds an ID-keyed lookup (FORMULA_REGISTRY) so api/formulas.py's
POST /api/formulas/compute/{formula_id} endpoint can resolve a formula_id
string straight to the actual callable, without a second hardcoded
if/elif dispatch table to keep in sync.
"""

import inspect

from services import formula_engine as fe

try:
    from services import formula_engine_quantlib as fe_ql
except ImportError:
    fe_ql = None

try:
    from services import formula_engine_symbolic as fe_sym
except ImportError:
    fe_sym = None

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

    # services.formula_engine_quantlib (task #777) -- fixed income, real
    # day-count/schedule bond math + dividend-aware American options.
    "bond_clean_price": "fixed_income", "bond_dirty_price": "fixed_income",
    "bond_yield_to_maturity": "fixed_income", "bond_duration_convexity": "fixed_income",
    "zero_coupon_bond_price": "fixed_income", "forward_rate": "fixed_income",
    "american_option_price": "fixed_income",

    # services.formula_engine_symbolic (task #778) -- reverse-solvers.
    "implied_growth_rate_dcf": "solver", "solve_gordon_growth_for_rate": "solver",
    "solve_gordon_growth_for_growth": "solver", "find_all_irr_roots": "solver",
    "solve_black_scholes_strike_from_delta": "solver",
}

CATEGORIES = {
    "technical": {"label": "Technical Indicators", "label_zh": "技術指標"},
    "risk": {"label": "Risk & Performance Metrics", "label_zh": "風險與表現指標"},
    "options": {"label": "Options Pricing & Derivatives", "label_zh": "期權定價與衍生工具"},
    "portfolio": {"label": "Portfolio Theory", "label_zh": "投資組合理論"},
    "tvm": {"label": "Time Value of Money", "label_zh": "資金時間價值"},
    "stats": {"label": "Statistics & Probability", "label_zh": "統計與概率"},
    "structure": {"label": "Market Structure / Chart Math", "label_zh": "市場結構與圖表數學"},
    "fixed_income": {"label": "Fixed Income & Advanced Derivatives (QuantLib)", "label_zh": "固定收益與進階衍生工具"},
    "solver": {"label": "Reverse Solvers (SymPy)", "label_zh": "反解求解器"},
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


_SOURCE_MODULES = [m for m in (fe, fe_ql, fe_sym) if m is not None]


def _build_catalog():
    entries = []
    registry = {}
    for module in _SOURCE_MODULES:
        for name, func in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("_") or name not in _CATEGORY_MAP or name in registry:
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
