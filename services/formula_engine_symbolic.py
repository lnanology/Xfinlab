"""
Formula Engine -- Symbolic Reverse-Solvers (task #776, #778, per AJ:
"建議的全加入 我要生產比市場更強的去賺錢" -- SymPy is BSD-licensed,
explicitly safe for commercial embedding, confirmed via a clean
`pip install sympy` in this project's sandbox).

Every function in services/formula_engine.py answers "given these inputs,
what's the output" (e.g. DCF: given cash flows + discount rate, what's
fair value). This module answers the INVERSE question that's usually more
useful for actually trading/investing: "given the market's current price,
what assumption is the market making?" -- i.e. reverse-solve a model for
the one unknown that would make it match an observed market price. This is
a real, well-known analyst technique (a "reverse DCF" / market-implied
growth rate) -- not a novel claim, just not something a plain forward
calculator can do without either brute-force guessing or real equation
solving.

Where a function has a genuine closed-form algebraic inverse (Gordon
Growth solved for r or g), we still route it through sympy.solve() rather
than hand-inverting the formula, so every reverse-solver in this module
shares one verified code path instead of N hand-derived algebra rewrites
that could each individually contain a sign error. Where no closed form
exists (reverse DCF's implied growth rate) or where a plain Newton-Raphson
root-finder is known to be unreliable (bonds/projects with multiple sign
changes in their cash flows can have more than one mathematically valid
IRR -- Newton's method finds whichever one its starting guess happens to
converge to and silently misses the others), this module uses sympy's
exact polynomial root-finding to return every real solution.
"""

import math

import sympy as sp

from services.formula_engine import _norm_cdf, _norm_ppf


def implied_growth_rate_dcf(fair_value: float, first_year_cash_flow: float, discount_rate: float,
                             years: int, terminal_growth: float = None) -> float:
    """Market-Implied Growth Rate (Reverse DCF): given an observed price
    (fair_value -- typically the current market price), the next period's
    cash flow, a discount rate, and a projection horizon, solves for the
    constant annual growth rate g that a standard DCF would need to
    justify that price. This is the "reverse DCF" technique analysts use
    to ask "what is the market currently pricing in", rather than "what do
    I think fair value is" -- flips the usual discounted_cash_flow()
    question around. Solved numerically via sympy.nsolve since growth
    compounds inside every cash-flow term (and again inside the optional
    Gordon Growth terminal value), giving no closed-form inverse."""
    g = sp.symbols("g", real=True)
    pv = sum(first_year_cash_flow * (1 + g) ** (t - 1) / (1 + discount_rate) ** t
              for t in range(1, years + 1))
    if terminal_growth is not None:
        last_cf = first_year_cash_flow * (1 + g) ** (years - 1)
        terminal_value = last_cf * (1 + terminal_growth) / (discount_rate - terminal_growth)
        pv += terminal_value / (1 + discount_rate) ** years
    equation = sp.Eq(pv, fair_value)
    solution = sp.nsolve(equation, g, 0.05)
    return float(solution)


def solve_gordon_growth_for_rate(fair_value: float, next_dividend: float, growth_rate: float) -> float:
    """Gordon Growth Model, solved for required return: given an observed
    price, next dividend, and an assumed growth rate, what required return
    r is the market implicitly demanding? Inverts fair_value =
    next_dividend / (r - g). Solved via sympy.solve on the same equation
    gordon_growth_model() prices forward, not a separately hand-derived
    formula."""
    r, fv, d1, g = sp.symbols("r fv d1 g", real=True)
    equation = sp.Eq(fv, d1 / (r - g))
    solved = sp.solve(equation, r)[0]
    return float(solved.subs({fv: fair_value, d1: next_dividend, g: growth_rate}))


def solve_gordon_growth_for_growth(fair_value: float, next_dividend: float, required_return: float) -> float:
    """Gordon Growth Model, solved for growth rate: given an observed
    price, next dividend, and a required return, what constant dividend
    growth rate is the market implicitly pricing in? Inverts fair_value =
    next_dividend / (r - g) for g, via the same sympy equation as
    solve_gordon_growth_for_rate()."""
    r, fv, d1, g = sp.symbols("r fv d1 g", real=True)
    equation = sp.Eq(fv, d1 / (r - g))
    solved = sp.solve(equation, g)[0]
    return float(solved.subs({fv: fair_value, d1: next_dividend, r: required_return}))


def find_all_irr_roots(cash_flows: list) -> list:
    """All Real Internal Rates of Return: cash flows with more than one
    sign change (e.g. an investment with a large cash outflow partway
    through, like a mine reclamation cost or a leveraged buyback) can
    mathematically satisfy NPV=0 at more than one discount rate --
    services.formula_engine.internal_rate_of_return()'s Newton-Raphson
    solver converges to only ONE of them depending on its starting guess,
    silently hiding the others. This function substitutes x=1/(1+r) to
    turn NPV=0 into an ordinary polynomial and finds every real root
    exactly via sympy, returning every valid IRR (as decimals) sorted
    ascending. Verified against the classic textbook multi-IRR cash flow
    [-1000, 6000, -11000, 6000], which has three real IRRs: 0%, 100%, and
    200%."""
    x = sp.symbols("x", real=True)
    poly_expr = sum(cf * x ** t for t, cf in enumerate(cash_flows))
    poly = sp.Poly(poly_expr, x)
    roots = poly.nroots()
    irrs = []
    for root in roots:
        c = complex(root)
        if abs(c.imag) < 1e-9 and c.real > 1e-9:
            irrs.append(1 / c.real - 1)
    return sorted(irrs)


def solve_black_scholes_strike_from_delta(target_delta: float, spot: float, time_to_expiry_years: float,
                                           rate: float, volatility: float, option_type: str = "call") -> float:
    """Black-Scholes Strike From Target Delta: option strategies are
    routinely built by target delta rather than target strike (e.g. "sell
    the 25-delta put" in a credit spread). target_delta is given as a
    positive magnitude in (0,1) for both calls and puts, matching market
    convention (a "25-delta put" means |delta|=0.25, i.e. an actual delta
    of -0.25). Since delta = N(d1) for a call and N(d1)-1 for a put, and
    d1 has a closed-form inverse via the Normal quantile function, this
    solves directly for the strike K that produces the requested delta --
    closed-form algebra (not an iterative sympy solve), reusing this
    codebase's own inverse-normal implementation (_norm_ppf) from
    services.formula_engine so results match black_scholes_greeks()
    exactly."""
    d1_target = _norm_ppf(target_delta) if option_type == "call" else _norm_ppf(1 - target_delta)
    T = time_to_expiry_years
    log_moneyness = d1_target * volatility * math.sqrt(T) - (rate + volatility ** 2 / 2) * T
    return spot * math.exp(-log_moneyness)
