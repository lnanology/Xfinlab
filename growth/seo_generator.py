import os
import sys
sys.path.insert(0, "/Users/aj/Desktop/Xfinlab-main")

from datetime import datetime


STOCKS = [
    ("AAPL", "Apple Inc."),
    ("NVDA", "NVIDIA Corporation"),
    ("TSLA", "Tesla Inc."),
    ("MSFT", "Microsoft Corporation"),
    ("META", "Meta Platforms Inc."),
    ("GOOGL", "Alphabet Inc."),
    ("AMZN", "Amazon.com Inc."),
    ("BRK", "Berkshire Hathaway"),
    ("JPM", "JPMorgan Chase"),
    ("V", "Visa Inc."),
]


def generate_stock_page(ticker: str, company: str, analysis: dict = None) -> str:
    price = analysis.get("price", "N/A") if analysis else "N/A"
    score = analysis.get("final_score", "N/A") if analysis else "N/A"
    rating = analysis.get("rating", "N/A") if analysis else "N/A"
    risk = analysis.get("risk", {}).get("risk_level", "N/A") if analysis else "N/A"
    date = datetime.now().strftime("%B %d, %Y")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{ticker} Stock Analysis {datetime.now().year} - XFINLAB AI</title>
<meta name="description" content="AI-powered {ticker} ({company}) stock analysis. Get real-time price, risk assessment, and investment rating powered by XFINLAB Intelligence.">
<meta name="keywords" content="{ticker}, {ticker} stock, {ticker} analysis, {company}, stock analysis, AI investment, XFINLAB">
<meta property="og:title" content="{ticker} Stock Analysis - XFINLAB AI">
<meta property="og:description" content="Get AI-powered {ticker} stock analysis. Price: ${price} | Score: {score}/100 | Rating: {rating}">
<style>
body{{font-family:'Inter',sans-serif;background:#080c14;color:#e2e8f0;margin:0;padding:0}}
nav{{background:#0d1525;padding:16px 32px;border-bottom:1px solid #1e2d45}}
.brand{{color:#00d4ff;font-weight:700;font-size:1.1rem;text-decoration:none}}
main{{max-width:900px;margin:0 auto;padding:40px 24px}}
h1{{font-size:2rem;color:#fff;margin-bottom:8px}}
.subtitle{{color:#64748b;margin-bottom:32px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:32px}}
.card{{background:#0d1525;border:1px solid #1e2d45;border-radius:12px;padding:20px}}
.label{{font-size:0.7rem;text-transform:uppercase;letter-spacing:0.1em;color:#64748b;margin-bottom:8px}}
.value{{font-size:1.8rem;font-weight:700;color:#00d4ff}}
.section{{background:#0d1525;border:1px solid #1e2d45;border-radius:12px;padding:24px;margin-bottom:20px}}
h2{{color:#94a3b8;font-size:0.8rem;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px}}
p{{color:#cbd5e1;line-height:1.8}}
.cta{{background:#00d4ff;color:#000;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;display:inline-block;margin-top:20px}}
footer{{text-align:center;padding:32px;color:#64748b;font-size:0.8rem;border-top:1px solid #1e2d45;margin-top:40px}}
</style>
</head>
<body>
<nav><a href="/" class="brand">XFINLAB</a></nav>
<main>
<h1>{ticker} — {company}</h1>
<p class="subtitle">AI Investment Analysis · Updated {date}</p>

<div class="grid">
  <div class="card"><div class="label">Price</div><div class="value">${price}</div></div>
  <div class="card"><div class="label">AI Score</div><div class="value">{score}</div></div>
  <div class="card"><div class="label">Risk Level</div><div class="value">{risk}</div></div>
  <div class="card"><div class="label">Rating</div><div class="value">{rating}</div></div>
</div>

<div class="section">
<h2>About {company}</h2>
<p>{company} ({ticker}) is a publicly traded company analyzed by XFINLAB's AI Investment Intelligence platform. Our system evaluates market data, news sentiment, technical indicators, and risk factors to generate comprehensive investment insights.</p>
</div>

<div class="section">
<h2>AI Analysis Methodology</h2>
<p>XFINLAB uses a multi-layer analysis pipeline combining market data scoring, news sentiment analysis, strategy evaluation, and risk assessment to generate a final investment score from 0-100.</p>
</div>

<div class="section">
<h2>Risk Disclaimer</h2>
<p>This analysis is for informational purposes only and does not constitute financial advice. Always conduct your own research and consult a qualified financial advisor before making investment decisions.</p>
</div>

<a href="https://xfinlab.com" class="cta">Get Full AI Analysis →</a>
</main>
<footer>© {datetime.now().year} XFINLAB — AI Investment Intelligence Platform</footer>
</body>
</html>"""


def generate_all_pages(output_dir: str = "growth/seo/pages"):
    os.makedirs(output_dir, exist_ok=True)

    # Try to get real data
    try:
        from services.market_data_service import MarketDataService
        market_svc = MarketDataService()
    except Exception:
        market_svc = None

    generated = []
    for ticker, company in STOCKS:
        analysis = None
        if market_svc:
            try:
                data = market_svc.get_stock_data(ticker)
                analysis = data
            except Exception:
                pass

        html = generate_stock_page(ticker, company, analysis)
        filepath = f"{output_dir}/{ticker.lower()}.html"
        with open(filepath, "w") as f:
            f.write(html)
        generated.append(filepath)
        print(f"  Generated: {filepath}")

    # Generate index page
    links = "".join([f'<li><a href="{t.lower()}.html" style="color:#00d4ff">{t} — {c}</a></li>' for t, c in STOCKS])
    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Stock Analysis - XFINLAB AI</title>
<meta name="description" content="AI-powered stock analysis for top stocks. Get real-time investment insights powered by XFINLAB Intelligence.">
<style>
body{{font-family:'Inter',sans-serif;background:#080c14;color:#e2e8f0;margin:0;padding:40px}}
h1{{color:#00d4ff}}ul{{line-height:2.5}}a{{text-decoration:none}}
</style>
</head>
<body>
<h1>XFINLAB Stock Analysis</h1>
<ul>{links}</ul>
</body>
</html>"""

    with open(f"{output_dir}/index.html", "w") as f:
        f.write(index_html)

    print(f"\nGenerated {len(generated)} stock pages + index")
    return generated


if __name__ == "__main__":
    print("XFINLAB SEO Generator")
    print("Generating stock pages...")
    generate_all_pages()
    print("Done!")
