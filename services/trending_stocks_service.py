"""
Country-prioritized "trending / most actively traded" stocks.

Used by js/autocomplete.js to show locally-relevant stocks first in the
autocomplete "trending" section, based on the visitor's IP-detected
country (api/i18n.py's /i18n/detect already resolves country from IP;
the frontend caches that country in localStorage and passes it here --
see js/i18n.js's cached 'xfinlab_country').

Two strategies per country (researched July 2026):
  1. Taiwan (TW): TWSE publishes a genuinely free, anonymous, official
     JSON endpoint for "today's top 20 securities by trading volume/
     value" (MI_INDEX20) -- used directly, real full-market ranking.
     This official feed has no per-stock sector data and is always
     "today", so `sector`/`days` filters below don't apply to it.
  2. Everywhere else: no exchange publishes an equivalent free official
     ranking without a paid subscription or account registration (HKEX,
     LSE, Euronext, Deutsche Börse, ASX, B3, KRX, SGX, Bursa, SET, IDX
     all checked). So for all other countries: a small curated basket of
     that country's best-known large-cap tickers, ranked by actual
     trailing trading volume via fetch_ohlc_history() -- real volume
     data, just scoped to a known basket rather than the whole exchange.

2026-09-28 (AJ: "可以加選擇，唔同行業的最活躍股票，可選近3/7/14/30天"):
added two optional filters on top of the existing per-country basket --
`sector` (GICS-style label, see SECTORS below) and `days` (one of
ALLOWED_DAYS). Each basket entry is now (ticker, name, sector) instead
of (ticker, name); the US basket was also expanded from 8 to 50 tickers
(5 per sector across 10 sectors) since the original 8-ticker basket was
too small for a sector filter to return anything meaningful. Other
countries keep their original ticker count -- each existing entry just
gained a best-effort sector tag, so a sector filter there returns
whatever (often just 0-1) of that country's curated tickers happen to
match, which is an honest reflection of how small those baskets are.

Bug fixed in the same pass: `_fetch_basket_ranked()` used to ask
fetch_ohlc_history() for period="7d" literally. For US tickers with
Alpaca configured, TechnicalAnalysisService._fetch_alpaca() looks
that period string up in ALPACA_PERIOD_DAYS, which had no "7d" entry --
so it silently fell back to that dict's `.get(period, 182)` default of
*182 days*, not 7. Every "trailing volume" number this service ever
returned for an Alpaca-routed US ticker was actually a ~6-month sum
mislabelled as 7-day. Fixed by no longer depending on period-string
lookups at all: fetch a fixed, generous "3mo" window once (a period key
that's correctly mapped for both Alpaca and yfinance) and slice the
last `days` real trading sessions out of the returned DataFrame in
Python -- exact, and immune to whatever period-string quirks either
data source has.

Cached per (country, sector, days) per calendar day (module-level
dict), same pattern as api/market_pulse.py's free-signals cache, so
this only does real network work once per combination per day rather
than on every autocomplete focus / admin lookup.
"""
from datetime import date

from services.outbound_http import get_with_backoff

# 2026-07-18 data-compliance pass: was a direct `yfinance` call, now
# routed through TechnicalAnalysisService's Alpaca-first/yfinance-
# fallback fetcher for the same reason as services/anomaly_history_
# service.py (see fetch_ohlc_history()'s docstring).
try:
    from services.technical_analysis_service import fetch_ohlc_history
except Exception:
    fetch_ohlc_history = None

# Fixed fetch window: big enough to always cover the largest ALLOWED_DAYS
# value (30 trading sessions) with room to spare for holidays/weekends,
# and it's a period string both Alpaca (ALPACA_PERIOD_DAYS["3mo"] = 90
# days) and yfinance handle correctly -- see module docstring.
_FETCH_PERIOD = "3mo"

ALLOWED_DAYS = (3, 7, 14, 30)
DEFAULT_DAYS = 7

# Best-effort GICS-style sector labels. Used both to tag each basket
# entry below and as the canonical list a frontend dropdown should
# offer (see api/trending.py's /trending-stocks/sectors).
SECTORS = [
    "Technology", "Communication Services", "Consumer Discretionary",
    "Consumer Staples", "Financials", "Healthcare", "Energy",
    "Industrials", "Utilities", "Real Estate", "Materials",
]

# 2026-09-28 (AJ: "期貨，加密貨幣，外匯，商品，指數 都加入可選"): non-equity
# asset classes. "Stocks" (the country baskets above) is the implicit
# default/6th option. Each entry: (ticker, name). Deliberately real,
# liquid, US-listed proxies rather than raw futures/forex tickers --
# same reasoning services/video_engine_service.py's
# _COMMODITY_FOREX_KEYWORDS already established for this codebase:
#   - Forex: spot FX pairs (EURUSD=X etc.) report zero/no real volume
#     via yfinance since OTC FX has no consolidated tape -- a currency
#     ETF (FXE, UUP, ...) is a real, exchange-traded, actually-volumed
#     instrument instead of a volume number that would misleadingly
#     read as real but isn't.
#   - Indices: cash indices (^GSPC etc.) don't trade and have no real
#     volume either -- the tracking ETF (SPY, QQQ, ...) does.
#   - Futures/Commodities: unlike forex/indices, exchange-traded futures
#     (ES=F, GC=F, ...) DO report real contract volume via yfinance, so
#     those two classes use the actual futures tickers rather than an
#     ETF proxy -- "most active futures contract" should mean the
#     contract itself, not a fund that merely holds one.
#   - Crypto: exchange volume (BTC-USD, ...) via yfinance is real
#     (major-exchange-aggregated), so this uses the actual coin pairs
#     rather than a crypto ETF -- "most active crypto" should mean the
#     coin's own trading activity, not one ETF's flows.
ASSET_CLASSES = ["Stocks", "Futures", "Crypto", "Forex", "Commodities", "Indices"]

ASSET_CLASS_BASKETS = {
    "futures": [
        ("ES=F", "S&P 500 Futures"), ("NQ=F", "Nasdaq 100 Futures"),
        ("YM=F", "Dow Futures"), ("RTY=F", "Russell 2000 Futures"),
        ("VX=F", "VIX Futures"),
    ],
    "commodities": [
        ("GC=F", "Gold Futures"), ("SI=F", "Silver Futures"),
        ("CL=F", "Crude Oil WTI Futures"), ("NG=F", "Natural Gas Futures"),
        ("HG=F", "Copper Futures"), ("ZC=F", "Corn Futures"),
    ],
    "crypto": [
        ("BTC-USD", "Bitcoin"), ("ETH-USD", "Ethereum"), ("SOL-USD", "Solana"),
        ("BNB-USD", "BNB"), ("XRP-USD", "XRP"), ("DOGE-USD", "Dogecoin"),
    ],
    "forex": [
        ("UUP", "US Dollar Index (ETF)"), ("FXE", "Euro (ETF)"),
        ("FXY", "Japanese Yen (ETF)"), ("FXB", "British Pound (ETF)"),
        ("FXA", "Australian Dollar (ETF)"), ("FXC", "Canadian Dollar (ETF)"),
    ],
    "indices": [
        ("SPY", "S&P 500 (ETF)"), ("QQQ", "Nasdaq 100 (ETF)"),
        ("DIA", "Dow Jones (ETF)"), ("IWM", "Russell 2000 (ETF)"),
        ("EFA", "Developed Intl (ETF)"), ("EEM", "Emerging Markets (ETF)"),
    ],
}

# ---- Tier 2 fallback baskets: well-known large caps per country ----
# Deliberately small and curated (not an attempt at full-market coverage)
# -- see module docstring for why a real full-market ranking isn't
# freely available outside Taiwan. Each entry: (ticker, name, sector).
# US is intentionally the deepest basket (5 tickers x 10 sectors) since
# it's the one this sector filter is actually meant to be used against;
# every other country keeps its original small ticker list with just a
# sector tag added.
COUNTRY_BASKETS = {
    "US": [
        ("AAPL", "Apple", "Technology"), ("MSFT", "Microsoft", "Technology"),
        ("NVDA", "NVIDIA", "Technology"), ("AVGO", "Broadcom", "Technology"),
        ("ORCL", "Oracle", "Technology"),
        ("GOOGL", "Alphabet", "Communication Services"), ("META", "Meta", "Communication Services"),
        ("NFLX", "Netflix", "Communication Services"), ("DIS", "Disney", "Communication Services"),
        ("VZ", "Verizon", "Communication Services"),
        ("AMZN", "Amazon", "Consumer Discretionary"), ("TSLA", "Tesla", "Consumer Discretionary"),
        ("HD", "Home Depot", "Consumer Discretionary"), ("MCD", "McDonald's", "Consumer Discretionary"),
        ("NKE", "Nike", "Consumer Discretionary"),
        ("WMT", "Walmart", "Consumer Staples"), ("PG", "Procter & Gamble", "Consumer Staples"),
        ("KO", "Coca-Cola", "Consumer Staples"), ("PEP", "PepsiCo", "Consumer Staples"),
        ("COST", "Costco", "Consumer Staples"),
        ("JPM", "JPMorgan Chase", "Financials"), ("BAC", "Bank of America", "Financials"),
        ("GS", "Goldman Sachs", "Financials"), ("V", "Visa", "Financials"),
        ("MA", "Mastercard", "Financials"),
        ("UNH", "UnitedHealth", "Healthcare"), ("JNJ", "Johnson & Johnson", "Healthcare"),
        ("LLY", "Eli Lilly", "Healthcare"), ("PFE", "Pfizer", "Healthcare"),
        ("ABBV", "AbbVie", "Healthcare"),
        ("XOM", "ExxonMobil", "Energy"), ("CVX", "Chevron", "Energy"),
        ("COP", "ConocoPhillips", "Energy"), ("SLB", "SLB", "Energy"),
        ("OXY", "Occidental Petroleum", "Energy"),
        ("BA", "Boeing", "Industrials"), ("CAT", "Caterpillar", "Industrials"),
        ("GE", "GE Aerospace", "Industrials"), ("HON", "Honeywell", "Industrials"),
        ("UPS", "UPS", "Industrials"),
        ("NEE", "NextEra Energy", "Utilities"), ("DUK", "Duke Energy", "Utilities"),
        ("SO", "Southern Company", "Utilities"), ("AEP", "American Electric Power", "Utilities"),
        ("EXC", "Exelon", "Utilities"),
        ("PLD", "Prologis", "Real Estate"), ("AMT", "American Tower", "Real Estate"),
        ("EQIX", "Equinix", "Real Estate"), ("SPG", "Simon Property Group", "Real Estate"),
        ("O", "Realty Income", "Real Estate"),
    ],
    "HK": [("0700.HK", "Tencent", "Communication Services"), ("9988.HK", "Alibaba", "Consumer Discretionary"),
           ("0005.HK", "HSBC", "Financials"), ("0941.HK", "China Mobile", "Communication Services"),
           ("3690.HK", "Meituan", "Consumer Discretionary"), ("1299.HK", "AIA", "Financials"),
           ("0388.HK", "HKEX", "Financials"), ("2318.HK", "Ping An", "Financials"),
           ("0016.HK", "Sun Hung Kai", "Real Estate"), ("1398.HK", "ICBC", "Financials"),
           ("0027.HK", "Galaxy Entertainment", "Consumer Discretionary"), ("2020.HK", "ANTA Sports", "Consumer Discretionary")],
    "TW": [("2330.TW", "TSMC", "Technology"), ("2317.TW", "Hon Hai", "Technology"),
           ("2454.TW", "MediaTek", "Technology"), ("2412.TW", "Chunghwa Telecom", "Communication Services"),
           ("1301.TW", "Formosa Plastics", "Materials"), ("2308.TW", "Delta Electronics", "Technology"),
           ("2882.TW", "Cathay Financial", "Financials"), ("3008.TW", "Largan", "Technology")],
    "CN": [("600519.SS", "Kweichow Moutai", "Consumer Staples"), ("601318.SS", "Ping An", "Financials"),
           ("600036.SS", "China Merchants Bank", "Financials"), ("000858.SZ", "Wuliangye", "Consumer Staples"),
           ("601857.SS", "PetroChina", "Energy"), ("600030.SS", "CITIC Securities", "Financials")],
    "JP": [("7203.T", "Toyota", "Consumer Discretionary"), ("6758.T", "Sony", "Technology"),
           ("9984.T", "SoftBank Group", "Communication Services"), ("6501.T", "Hitachi", "Industrials"),
           ("8306.T", "Mitsubishi UFJ", "Financials"), ("9432.T", "NTT", "Communication Services"),
           ("7974.T", "Nintendo", "Communication Services"), ("6098.T", "Recruit Holdings", "Industrials")],
    "KR": [("005930.KS", "Samsung Electronics", "Technology"), ("000660.KS", "SK Hynix", "Technology"),
           ("373220.KS", "LG Energy Solution", "Industrials"), ("005380.KS", "Hyundai Motor", "Consumer Discretionary"),
           ("006400.KS", "Samsung SDI", "Industrials"), ("035420.KS", "Naver", "Communication Services"),
           ("051910.KS", "LG Chem", "Materials")],
    "SG": [("D05.SI", "DBS Group", "Financials"), ("O39.SI", "OCBC", "Financials"),
           ("U11.SI", "UOB", "Financials"), ("Z74.SI", "Singtel", "Communication Services")],
    "MY": [("1155.KL", "Maybank", "Financials"), ("1023.KL", "CIMB", "Financials"),
           ("5183.KL", "Petronas Chemicals", "Materials")],
    "TH": [("PTT.BK", "PTT", "Energy"), ("AOT.BK", "Airports of Thailand", "Industrials"),
           ("CPALL.BK", "CP All", "Consumer Staples")],
    "ID": [("BBCA.JK", "Bank Central Asia", "Financials"), ("BBRI.JK", "Bank Rakyat Indonesia", "Financials"),
           ("TLKM.JK", "Telkom Indonesia", "Communication Services")],
    "VN": [("VNM.VN", "Vinamilk", "Consumer Staples"), ("VIC.VN", "Vingroup", "Real Estate")],
    "IN": [("RELIANCE.NS", "Reliance Industries", "Energy"), ("TCS.NS", "TCS", "Technology"),
           ("HDFCBANK.NS", "HDFC Bank", "Financials"), ("INFY.NS", "Infosys", "Technology"),
           ("ICICIBANK.NS", "ICICI Bank", "Financials"), ("BHARTIARTL.NS", "Bharti Airtel", "Communication Services")],
    "AU": [("BHP.AX", "BHP Group", "Materials"), ("CBA.AX", "Commonwealth Bank", "Financials"),
           ("CSL.AX", "CSL", "Healthcare"), ("NAB.AX", "NAB", "Financials"),
           ("WBC.AX", "Westpac", "Financials"), ("WES.AX", "Wesfarmers", "Consumer Staples")],
    "GB": [("SHEL.L", "Shell", "Energy"), ("AZN.L", "AstraZeneca", "Healthcare"),
           ("HSBA.L", "HSBC", "Financials"), ("ULVR.L", "Unilever", "Consumer Staples"),
           ("BP.L", "BP", "Energy"), ("GSK.L", "GSK", "Healthcare"), ("RIO.L", "Rio Tinto", "Materials")],
    "DE": [("SAP.DE", "SAP", "Technology"), ("SIE.DE", "Siemens", "Industrials"),
           ("ALV.DE", "Allianz", "Financials"), ("DTE.DE", "Deutsche Telekom", "Communication Services"),
           ("VOW3.DE", "Volkswagen", "Consumer Discretionary"), ("BAS.DE", "BASF", "Materials")],
    "FR": [("MC.PA", "LVMH", "Consumer Discretionary"), ("OR.PA", "L'Oreal", "Consumer Staples"),
           ("TTE.PA", "TotalEnergies", "Energy"), ("SAN.PA", "Sanofi", "Healthcare"),
           ("AI.PA", "Air Liquide", "Materials"), ("AIR.PA", "Airbus", "Industrials")],
    "BR": [("PETR4.SA", "Petrobras", "Energy"), ("VALE3.SA", "Vale", "Materials"),
           ("ITUB4.SA", "Itau Unibanco", "Financials"), ("BBDC4.SA", "Bradesco", "Financials"),
           ("ABEV3.SA", "Ambev", "Consumer Staples"), ("WEGE3.SA", "WEG", "Industrials")],
    "CA": [("RY.TO", "Royal Bank of Canada", "Financials"), ("TD.TO", "TD Bank", "Financials"),
           ("SHOP.TO", "Shopify", "Technology"), ("ENB.TO", "Enbridge", "Energy")],
}

DEFAULT_COUNTRY = "US"

_cache = {}  # (country, sector, days) -> {"date": iso_date_str, "data": {...}}


def _fetch_taiwan_official():
    """TWSE's free, anonymous, official 'today's top 20 by volume/value' feed."""
    today_str = date.today().strftime("%Y%m%d")
    url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX20?response=json&date={today_str}"
    try:
        # 2026-07-18 compliance pass: honest User-Agent + 429/503 backoff
        # (see services/outbound_http.py) even though this is an official
        # free public feed -- being a good citizen towards it costs nothing.
        res = get_with_backoff(url, timeout=6)
        if res.status_code != 200:
            return None
        payload = res.json()
        rows = payload.get("data") or []
        if not rows:
            return None
        stocks = []
        for row in rows[:20]:
            # TWSE row shape: [排名, 證券代號, 證券名稱, 成交股數, 成交金額, 成交筆數, ...]
            if len(row) < 3:
                continue
            code, name = str(row[1]).strip(), str(row[2]).strip()
            if not code:
                continue
            stocks.append({"symbol": f"{code}.TW", "name": name, "source": "TWSE"})
        return stocks or None
    except Exception:
        return None


def _fetch_basket_ranked(country, sector=None, days=DEFAULT_DAYS):
    basket = COUNTRY_BASKETS.get(country)
    if not basket or fetch_ohlc_history is None:
        return None
    if sector:
        sector_lower = sector.strip().lower()
        basket = [b for b in basket if b[2].lower() == sector_lower]
    ranked = []
    for ticker, name, tkr_sector in basket:
        volume = 0
        sparkline = []
        try:
            hist = fetch_ohlc_history(ticker, period=_FETCH_PERIOD)
            if not hist.empty and "Volume" in hist:
                window = hist.tail(days)
                volume = int(window["Volume"].sum())
            # 2026-08-23 (AJ: "9張卡片加小K線圖" -- the homepage 9-category
            # board's "trending" card uses stocks[0] from this list): same
            # free-reuse pattern used elsewhere on this data -- hist is
            # already fetched for the volume sum above, just also keep the
            # last ~20 real closes for a glance-able sparkline, no new call.
            if not hist.empty and "Close" in hist:
                closes = hist["Close"].dropna().tail(20)
                sparkline = [round(float(v), 4) for v in closes.tolist()]
        except Exception:
            volume = 0
        ranked.append({
            "symbol": ticker, "name": name, "sector": tkr_sector,
            "volume": volume, "days": days, "source": "basket_volume", "sparkline": sparkline,
        })
    ranked.sort(key=lambda s: s["volume"], reverse=True)
    return ranked


def _fetch_asset_class_ranked(asset_class, days=DEFAULT_DAYS):
    """Same ranking logic as _fetch_basket_ranked() above, just over one
    of ASSET_CLASS_BASKETS instead of a per-country equity basket --
    country/sector don't apply to these (a futures contract or a coin
    doesn't have a "country" in the same sense a listed stock does)."""
    basket = ASSET_CLASS_BASKETS.get((asset_class or "").strip().lower())
    if not basket or fetch_ohlc_history is None:
        return None
    ranked = []
    for ticker, name in basket:
        volume = 0
        sparkline = []
        try:
            hist = fetch_ohlc_history(ticker, period=_FETCH_PERIOD)
            if not hist.empty and "Volume" in hist:
                window = hist.tail(days)
                volume = int(window["Volume"].sum())
            if not hist.empty and "Close" in hist:
                closes = hist["Close"].dropna().tail(20)
                sparkline = [round(float(v), 4) for v in closes.tolist()]
        except Exception:
            volume = 0
        ranked.append({
            "symbol": ticker, "name": name, "sector": None,
            "volume": volume, "days": days, "source": "asset_class_volume", "sparkline": sparkline,
        })
    ranked.sort(key=lambda s: s["volume"], reverse=True)
    return ranked


def get_trending_for_country(country, sector=None, days=DEFAULT_DAYS, asset_class=None):
    """Returns {"country": <resolved code>, "source": "...", "stocks": [...]}.
    Always returns something usable -- falls back to the US basket if the
    requested country has no basket and isn't Taiwan.

    `asset_class` (optional, 2026-09-28): one of ASSET_CLASSES. When
    given and not "Stocks", `country`/`sector` are ignored entirely and
    the ranking runs over ASSET_CLASS_BASKETS instead -- see that dict's
    comment for why each class uses the ticker format it does (ETF proxy
    vs. raw futures/forex/crypto symbol).

    `sector` (optional): one of SECTORS above (case-insensitive). Only
    affects the basket_volume strategy -- ignored for Taiwan's official
    feed, which carries no sector data.

    `days` (optional): trailing trading-session window for the volume
    sum, one of ALLOWED_DAYS. Silently snapped to DEFAULT_DAYS if given
    an unrecognized value, rather than raising -- this is a ranking
    convenience, not a strict API contract."""
    country = (country or DEFAULT_COUNTRY).upper()
    sector = (sector or "").strip() or None
    asset_class = (asset_class or "").strip() or None
    days = days if days in ALLOWED_DAYS else DEFAULT_DAYS
    today = date.today().isoformat()

    is_non_stock_class = bool(asset_class) and asset_class.lower() != "stocks"

    cache_key = (country, sector, days, asset_class if is_non_stock_class else None)
    cached = _cache.get(cache_key)
    if cached and cached["date"] == today:
        return cached["data"]

    if is_non_stock_class:
        stocks = _fetch_asset_class_ranked(asset_class, days=days) or []
        result = {
            "country": None, "source": "asset_class_volume" if stocks else "unavailable",
            "asset_class": asset_class, "sector": None, "days": days, "stocks": stocks[:20],
        }
        _cache[cache_key] = {"date": today, "data": result}
        return result

    stocks = None
    source = "basket_volume"
    country_used = country

    if country == "TW" and not sector:
        stocks = _fetch_taiwan_official()
        if stocks:
            source = "official_twse"

    if not stocks:
        stocks = _fetch_basket_ranked(country, sector=sector, days=days)

    if not stocks:
        stocks = _fetch_basket_ranked(DEFAULT_COUNTRY, sector=sector, days=days) or []
        source = "default_fallback"
        country_used = DEFAULT_COUNTRY

    result = {
        "country": country_used, "source": source, "asset_class": "Stocks",
        "sector": sector, "days": days, "stocks": stocks[:20],
    }
    _cache[cache_key] = {"date": today, "data": result}
    return result
