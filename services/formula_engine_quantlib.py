"""
Formula Engine -- Fixed Income & Advanced Derivatives (task #776-777, per
AJ: "建議的全加入 我要生產比市場更強的去賺錢" -- after directly verifying
QuantLib's license at https://www.quantlib.org/license.shtml (Modified
BSD / "QuantLib License", explicitly written to permit proprietary,
commercial use with no obligation to open-source the calling application),
this module adds the one category services/formula_engine.py's pure-Python
functions genuinely couldn't cover well: real bond pricing off an actual
day-count/coupon-schedule convention, Macaulay/Modified duration,
convexity, yield-to-maturity solving, and American-exercise option pricing
with a dividend yield (our own binomial_option_price() in formula_engine.py
has neither real day-count handling nor dividend support).

Kept as a SEPARATE module from formula_engine.py on purpose: it has a real
third-party runtime dependency (the `QuantLib` PyPI package -- ships as a
precompiled wheel, no system build tools needed, confirmed via a clean
`pip install QuantLib` in this project's sandbox). formula_engine.py stays
stdlib-only by design, so nothing there can ever break if this optional
module fails to import on some platform. services/formula_catalog.py
guards the import of this module in a try/except, so the rest of the
Formula Engine (and the API) keeps working even where QuantLib isn't
installed.

zero_coupon_bond_price() and forward_rate() don't strictly need QuantLib
(they're closed-form algebra) but live here for category cohesion with the
rest of the fixed-income formulas -- a caller browsing "fixed income" gets
all of it in one place.
"""

import math

import QuantLib as ql

_FREQ_MAP = {1: ql.Annual, 2: ql.Semiannual, 4: ql.Quarterly, 12: ql.Monthly}


def _flat_bond(coupon_rate: float, ytm: float, years_to_maturity: float, frequency: int = 2):
    """Internal helper: builds a QuantLib FixedRateBond with faceAmount=100
    (QuantLib's native "percent of face" convention) on a flat yield curve
    at `ytm`, using Actual/Actual (ISDA) day count -- the standard US
    Treasury / most-government-bond convention. Not part of the public
    catalog; every public function below scales the 100-face result to the
    caller's actual face_value."""
    today = ql.Date.todaysDate()
    ql.Settings.instance().evaluationDate = today
    calendar = ql.NullCalendar()
    day_count = ql.ActualActual(ql.ActualActual.ISDA)
    freq = _FREQ_MAP.get(frequency, ql.Semiannual)
    tenor = ql.Period(freq)
    maturity_date = today + ql.Period(int(round(years_to_maturity * 12)), ql.Months)
    schedule = ql.Schedule(today, maturity_date, tenor, calendar,
                            ql.Unadjusted, ql.Unadjusted,
                            ql.DateGeneration.Backward, False)
    bond = ql.FixedRateBond(0, 100.0, schedule, [coupon_rate], day_count)
    curve = ql.YieldTermStructureHandle(ql.FlatForward(today, ytm, day_count, ql.Compounded, freq))
    bond.setPricingEngine(ql.DiscountingBondEngine(curve))
    return bond, day_count, freq


def bond_clean_price(face_value: float, coupon_rate: float, ytm: float,
                      years_to_maturity: float, frequency: int = 2) -> float:
    """Fixed-Rate Bond Clean Price: present value of a bond's remaining
    coupon + principal cash flows discounted at a flat yield-to-maturity,
    using a real Actual/Actual day-count and coupon schedule (QuantLib
    FixedRateBond + DiscountingBondEngine) rather than the "assume exactly
    N whole periods" shortcut most textbook formulas use. Excludes accrued
    interest (use bond_dirty_price for the settlement amount)."""
    bond, _, _ = _flat_bond(coupon_rate, ytm, years_to_maturity, frequency)
    return bond.cleanPrice() / 100.0 * face_value


def bond_dirty_price(face_value: float, coupon_rate: float, ytm: float,
                      years_to_maturity: float, frequency: int = 2) -> float:
    """Fixed-Rate Bond Dirty (Full) Price: clean price plus accrued
    interest since the last coupon date -- the actual amount a buyer pays
    at settlement."""
    bond, _, _ = _flat_bond(coupon_rate, ytm, years_to_maturity, frequency)
    return bond.dirtyPrice() / 100.0 * face_value


def bond_yield_to_maturity(face_value: float, coupon_rate: float, clean_price: float,
                            years_to_maturity: float, frequency: int = 2) -> float:
    """Bond Yield-to-Maturity (solved): the single discount rate that makes
    a bond's discounted cash flows equal its observed market clean_price.
    Solved numerically by QuantLib against the same real day-count/coupon
    schedule bond_clean_price() uses (so YTM and price round-trip
    consistently), rather than the usual closed-form approximation."""
    bond, day_count, freq = _flat_bond(coupon_rate, 0.05, years_to_maturity, frequency)
    price_per_100 = clean_price / face_value * 100.0
    bp = ql.BondPrice(price_per_100, ql.BondPrice.Clean)
    return bond.bondYield(bp, day_count, ql.Compounded, freq)


def bond_duration_convexity(face_value: float, coupon_rate: float, ytm: float,
                             years_to_maturity: float, frequency: int = 2) -> dict:
    """Bond Duration & Convexity: Macaulay Duration (weighted-average time
    to receive cash flows), Modified Duration (% price change per 1
    unit change in yield, = Macaulay / (1 + ytm/frequency)), and Convexity
    (the curvature correction term -- how much Modified Duration itself
    understates price sensitivity for large yield moves). Computed via
    QuantLib's BondFunctions against the real coupon schedule."""
    bond, day_count, freq = _flat_bond(coupon_rate, ytm, years_to_maturity, frequency)
    rate = ql.InterestRate(ytm, day_count, ql.Compounded, freq)
    macaulay = ql.BondFunctions.duration(bond, rate, ql.Duration.Macaulay)
    modified = ql.BondFunctions.duration(bond, rate, ql.Duration.Modified)
    convexity = ql.BondFunctions.convexity(bond, rate)
    return {"macaulay_duration": macaulay, "modified_duration": modified, "convexity": convexity}


def zero_coupon_bond_price(face_value: float, years_to_maturity: float, yield_rate: float,
                            compounding: str = "annual") -> float:
    """Zero-Coupon Bond Price: PV of a single face-value payment at
    maturity, no coupons. Annual compounding: face/(1+y)^t. Continuous
    compounding: face * e^(-y*t). Closed-form -- doesn't need QuantLib's
    engine, kept here for fixed-income category cohesion."""
    if compounding == "continuous":
        return face_value * math.exp(-yield_rate * years_to_maturity)
    return face_value / (1 + yield_rate) ** years_to_maturity


def forward_rate(near_rate: float, far_rate: float, near_years: float, far_years: float) -> float:
    """Implied Forward Rate: the rate the market implies for the period
    BETWEEN two spot (zero-coupon) rates of different maturities --
    (1+far_rate)^far_years = (1+near_rate)^near_years * (1+f)^(far_years-
    near_years), solved for f. E.g. given the 1-year and 2-year spot
    rates, this is the 1-year rate the market expects one year from now
    under the pure expectations hypothesis."""
    span = far_years - near_years
    if span <= 0:
        raise ValueError("far_years must exceed near_years")
    growth = (1 + far_rate) ** far_years / (1 + near_rate) ** near_years
    return growth ** (1 / span) - 1


def american_option_price(spot: float, strike: float, time_to_expiry_years: float, rate: float,
                           volatility: float, option_type: str = "call",
                           dividend_yield: float = 0.0, steps: int = 200) -> float:
    """American Option Price (Cox-Ross-Rubinstein binomial via QuantLib):
    unlike services.formula_engine.binomial_option_price() (which has no
    dividend support), this prices against a continuous dividend_yield --
    material for equity index options and high-dividend stocks, where
    American calls can be worth exercising early specifically to capture
    a dividend. Uses QuantLib's BinomialVanillaEngine on a Black-Scholes-
    Merton process."""
    today = ql.Date.todaysDate()
    ql.Settings.instance().evaluationDate = today
    calendar = ql.NullCalendar()
    day_count = ql.Actual365Fixed()

    maturity = today + ql.Period(max(1, int(round(time_to_expiry_years * 365))), ql.Days)
    ql_type = ql.Option.Call if option_type == "call" else ql.Option.Put
    payoff = ql.PlainVanillaPayoff(ql_type, strike)
    exercise = ql.AmericanExercise(today, maturity)
    option = ql.VanillaOption(payoff, exercise)

    spot_h = ql.QuoteHandle(ql.SimpleQuote(spot))
    rate_ts = ql.YieldTermStructureHandle(ql.FlatForward(today, rate, day_count))
    div_ts = ql.YieldTermStructureHandle(ql.FlatForward(today, dividend_yield, day_count))
    vol_ts = ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, calendar, volatility, day_count))
    process = ql.BlackScholesMertonProcess(spot_h, div_ts, rate_ts, vol_ts)

    engine = ql.BinomialVanillaEngine(process, "crr", max(2, steps))
    option.setPricingEngine(engine)
    return option.NPV()
