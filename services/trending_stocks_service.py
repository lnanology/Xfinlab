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
  2. Everywhere else: no exchange publishes an equivalent free official
     ranking without a paid subscription or account registration (HKEX,
     LSE, Euronext, Deutsche Börse, ASX, B3, KRX, SGX, Bursa, SET, IDX
     all checked). So for all other countries: a small curated basket of
     that country's best-known large-cap tickers, ranked by actual
     trailing-7-day trading volume via yfinance (already a project
     dependency) -- real volume data, just scoped to a known basket
     rather than the whole exchange.

Cached per country per calendar day (module-level dict), same pattern
as api/market_pulse.py's free-signals cache, so this only does real
network work once per country per day rather than on every autocomplete
focus.
"""
import requests
from datetime import date

try:
    import yfinance as yf
except Exception:
    yf = None

# ---- Tier 2 fallback baskets: well-known large caps per country ----
# Deliberately small and curated (not an attempt at full-market coverage)
# -- see module docstring for why a real full-market ranking isn't
# freely available outside Taiwan.
COUNTRY_BASKETS = {
    "HK": [("0700.HK", "Tencent"), ("9988.HK", "Alibaba"), ("0005.HK", "HSBC"),
           ("0941.HK", "China Mobile"), ("3690.HK", "Meituan"), ("1299.HK", "AIA"),
           ("0388.HK", "HKEX"), ("2318.HK", "Ping An"), ("0016.HK", "Sun Hung Kai"),
           ("1398.HK", "ICBC"), ("0027.HK", "Galaxy Entertainment"), ("2020.HK", "ANTA Sports")],
    "TW": [("2330.TW", "TSMC"), ("2317.TW", "Hon Hai"), ("2454.TW", "MediaTek"),
           ("2412.TW", "Chunghwa Telecom"), ("1301.TW", "Formosa Plastics"),
           ("2308.TW", "Delta Electronics"), ("2882.TW", "Cathay Financial"), ("3008.TW", "Largan")],
    "CN": [("600519.SS", "Kweichow Moutai"), ("601318.SS", "Ping An"), ("600036.SS", "China Merchants Bank"),
           ("000858.SZ", "Wuliangye"), ("601857.SS", "PetroChina"), ("600030.SS", "CITIC Securities")],
    "JP": [("7203.T", "Toyota"), ("6758.T", "Sony"), ("9984.T", "SoftBank Group"),
           ("6501.T", "Hitachi"), ("8306.T", "Mitsubishi UFJ"), ("9432.T", "NTT"),
           ("7974.T", "Nintendo"), ("6098.T", "Recruit Holdings")],
    "KR": [("005930.KS", "Samsung Electronics"), ("000660.KS", "SK Hynix"), ("373220.KS", "LG Energy Solution"),
           ("005380.KS", "Hyundai Motor"), ("006400.KS", "Samsung SDI"), ("035420.KS", "Naver"), ("051910.KS", "LG Chem")],
    "SG": [("D05.SI", "DBS Group"), ("O39.SI", "OCBC"), ("U11.SI", "UOB"), ("Z74.SI", "Singtel")],
    "MY": [("1155.KL", "Maybank"), ("1023.KL", "CIMB"), ("5183.KL", "Petronas Chemicals")],
    "TH": [("PTT.BK", "PTT"), ("AOT.BK", "Airports of Thailand"), ("CPALL.BK", "CP All")],
    "ID": [("BBCA.JK", "Bank Central Asia"), ("BBRI.JK", "Bank Rakyat Indonesia"), ("TLKM.JK", "Telkom Indonesia")],
    "VN": [("VNM.VN", "Vinamilk"), ("VIC.VN", "Vingroup")],
    "IN": [("RELIANCE.NS", "Reliance Industries"), ("TCS.NS", "TCS"), ("HDFCBANK.NS", "HDFC Bank"),
           ("INFY.NS", "Infosys"), ("ICICIBANK.NS", "ICICI Bank"), ("BHARTIARTL.NS", "Bharti Airtel")],
    "AU": [("BHP.AX", "BHP Group"), ("CBA.AX", "Commonwealth Bank"), ("CSL.AX", "CSL"),
           ("NAB.AX", "NAB"), ("WBC.AX", "Westpac"), ("WES.AX", "Wesfarmers")],
    "GB": [("SHEL.L", "Shell"), ("AZN.L", "AstraZeneca"), ("HSBA.L", "HSBC"),
           ("ULVR.L", "Unilever"), ("BP.L", "BP"), ("GSK.L", "GSK"), ("RIO.L", "Rio Tinto")],
    "DE": [("SAP.DE", "SAP"), ("SIE.DE", "Siemens"), ("ALV.DE", "Allianz"),
           ("DTE.DE", "Deutsche Telekom"), ("VOW3.DE", "Volkswagen"), ("BAS.DE", "BASF")],
    "FR": [("MC.PA", "LVMH"), ("OR.PA", "L'Oreal"), ("TTE.PA", "TotalEnergies"),
           ("SAN.PA", "Sanofi"), ("AI.PA", "Air Liquide"), ("AIR.PA", "Airbus")],
    "BR": [("PETR4.SA", "Petrobras"), ("VALE3.SA", "Vale"), ("ITUB4.SA", "Itau Unibanco"),
           ("BBDC4.SA", "Bradesco"), ("ABEV3.SA", "Ambev"), ("WEGE3.SA", "WEG")],
    "CA": [("RY.TO", "Royal Bank of Canada"), ("TD.TO", "TD Bank"), ("SHOP.TO", "Shopify"), ("ENB.TO", "Enbridge")],
    "US": [("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "NVIDIA"), ("GOOGL", "Alphabet"),
           ("AMZN", "Amazon"), ("META", "Meta"), ("TSLA", "Tesla"), ("JPM", "JPMorgan Chase")],
}

DEFAULT_COUNTRY = "US"

_cache = {}  # country -> {"date": iso_date_str, "data": {...}}


def _fetch_taiwan_official():
    """TWSE's free, anonymous, official 'today's top 20 by volume/value' feed."""
    today_str = date.today().strftime("%Y%m%d")
    url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX20?response=json&date={today_str}"
    try:
        res = requests.get(url, timeout=6)
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


def _fetch_basket_ranked(country):
    basket = COUNTRY_BASKETS.get(country)
    if not basket or yf is None:
        return None
    ranked = []
    for ticker, name in basket:
        volume = 0
        try:
            hist = yf.Ticker(ticker).history(period="7d")
            if not hist.empty and "Volume" in hist:
                volume = int(hist["Volume"].sum())
        except Exception:
            volume = 0
        ranked.append({"symbol": ticker, "name": name, "volume": volume, "source": "basket_volume"})
    ranked.sort(key=lambda s: s["volume"], reverse=True)
    return ranked


def get_trending_for_country(country):
    """Returns {"country": <resolved code>, "source": "...", "stocks": [...]}.
    Always returns something usable -- falls back to the US basket if the
    requested country has no basket and isn't Taiwan."""
    country = (country or DEFAULT_COUNTRY).upper()
    today = date.today().isoformat()

    cached = _cache.get(country)
    if cached and cached["date"] == today:
        return cached["data"]

    stocks = None
    source = "basket_volume"
    country_used = country

    if country == "TW":
        stocks = _fetch_taiwan_official()
        if stocks:
            source = "official_twse"

    if not stocks:
        stocks = _fetch_basket_ranked(country)

    if not stocks:
        stocks = _fetch_basket_ranked(DEFAULT_COUNTRY) or []
        source = "default_fallback"
        country_used = DEFAULT_COUNTRY

    result = {"country": country_used, "source": source, "stocks": stocks[:20]}
    _cache[country] = {"date": today, "data": result}
    return result
