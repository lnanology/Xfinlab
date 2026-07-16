// XFINLAB Ticker Autocomplete -- 涵蓋股票/期貨/加密貨幣/指數/債券5大類，
// 等打任何字頭（例如「V」）都可以睇到跨資產類別嘅相關代號建議，唔止
// 得返股票（之前得STOCKS呢個純股票清單，打"V"淨係見到Visa一隻）。
const ALL_TICKERS = [
  // 股票 Stocks
  {symbol: 'AAPL', name: 'Apple Inc.', type: 'stock'},
  {symbol: 'NVDA', name: 'NVIDIA Corporation', type: 'stock'},
  {symbol: 'TSLA', name: 'Tesla Inc.', type: 'stock'},
  {symbol: 'MSFT', name: 'Microsoft Corporation', type: 'stock'},
  {symbol: 'META', name: 'Meta Platforms Inc.', type: 'stock'},
  {symbol: 'AMZN', name: 'Amazon.com Inc.', type: 'stock'},
  {symbol: 'GOOGL', name: 'Alphabet Inc.', type: 'stock'},
  {symbol: 'GOOG', name: 'Alphabet Inc. Class C', type: 'stock'},
  {symbol: 'BRK', name: 'Berkshire Hathaway', type: 'stock'},
  {symbol: 'JPM', name: 'JPMorgan Chase', type: 'stock'},
  {symbol: 'V', name: 'Visa Inc.', type: 'stock'},
  {symbol: 'UNH', name: 'UnitedHealth Group', type: 'stock'},
  {symbol: 'XOM', name: 'Exxon Mobil', type: 'stock'},
  {symbol: 'JNJ', name: 'Johnson & Johnson', type: 'stock'},
  {symbol: 'WMT', name: 'Walmart Inc.', type: 'stock'},
  {symbol: 'MA', name: 'Mastercard Inc.', type: 'stock'},
  {symbol: 'PG', name: 'Procter & Gamble', type: 'stock'},
  {symbol: 'ORCL', name: 'Oracle Corporation', type: 'stock'},
  {symbol: 'HD', name: 'Home Depot', type: 'stock'},
  {symbol: 'CVX', name: 'Chevron Corporation', type: 'stock'},
  {symbol: 'MRK', name: 'Merck & Co.', type: 'stock'},
  {symbol: 'ABBV', name: 'AbbVie Inc.', type: 'stock'},
  {symbol: 'KO', name: 'Coca-Cola Company', type: 'stock'},
  {symbol: 'PEP', name: 'PepsiCo Inc.', type: 'stock'},
  {symbol: 'LLY', name: 'Eli Lilly', type: 'stock'},
  {symbol: 'BAC', name: 'Bank of America', type: 'stock'},
  {symbol: 'AMD', name: 'Advanced Micro Devices', type: 'stock'},
  {symbol: 'COST', name: 'Costco Wholesale', type: 'stock'},
  {symbol: 'AVGO', name: 'Broadcom Inc.', type: 'stock'},
  {symbol: 'NFLX', name: 'Netflix Inc.', type: 'stock'},
  {symbol: 'INTC', name: 'Intel Corporation', type: 'stock'},
  {symbol: 'CRM', name: 'Salesforce Inc.', type: 'stock'},
  {symbol: 'ADBE', name: 'Adobe Inc.', type: 'stock'},
  {symbol: 'PYPL', name: 'PayPal Holdings', type: 'stock'},
  {symbol: 'PLTR', name: 'Palantir Technologies', type: 'stock'},
  {symbol: 'COIN', name: 'Coinbase Global', type: 'stock'},
  {symbol: 'MSTR', name: 'MicroStrategy', type: 'stock'},
  {symbol: 'SOFI', name: 'SoFi Technologies', type: 'stock'},
  {symbol: 'RIVN', name: 'Rivian Automotive', type: 'stock'},
  {symbol: 'NIO', name: 'NIO Inc.', type: 'stock'},
  {symbol: 'BABA', name: 'Alibaba Group', type: 'stock'},
  {symbol: 'TSM', name: 'Taiwan Semiconductor', type: 'stock'},
  {symbol: 'SHOP', name: 'Shopify Inc.', type: 'stock'},
  {symbol: 'SQ', name: 'Block Inc.', type: 'stock'},
  {symbol: 'HOOD', name: 'Robinhood Markets', type: 'stock'},
  {symbol: 'UBER', name: 'Uber Technologies', type: 'stock'},
  {symbol: 'LYFT', name: 'Lyft Inc.', type: 'stock'},
  {symbol: 'SNAP', name: 'Snap Inc.', type: 'stock'},
  {symbol: 'DIS', name: 'Walt Disney Company', type: 'stock'},
  {symbol: 'BA', name: 'Boeing Company', type: 'stock'},
  {symbol: 'GE', name: 'General Electric', type: 'stock'},
  {symbol: 'F', name: 'Ford Motor Company', type: 'stock'},
  {symbol: 'GM', name: 'General Motors', type: 'stock'},
  {symbol: 'AAL', name: 'American Airlines', type: 'stock'},
  {symbol: 'DAL', name: 'Delta Air Lines', type: 'stock'},
  {symbol: 'UAL', name: 'United Airlines', type: 'stock'},
  {symbol: 'GS', name: 'Goldman Sachs', type: 'stock'},
  {symbol: 'MS', name: 'Morgan Stanley', type: 'stock'},
  {symbol: 'C', name: 'Citigroup Inc.', type: 'stock'},
  {symbol: 'WFC', name: 'Wells Fargo', type: 'stock'},
  // 期貨 Futures
  {symbol: 'ES', name: 'E-mini S&P 500 Futures', type: 'futures', api: 'ES=F'},
  {symbol: 'YM', name: 'E-mini Dow Futures', type: 'futures', api: 'YM=F'},
  {symbol: 'NQ', name: 'E-mini Nasdaq 100 Futures', type: 'futures', api: 'NQ=F'},
  {symbol: 'RTY', name: 'E-mini Russell 2000 Futures', type: 'futures', api: 'RTY=F'},
  {symbol: 'VX', name: 'VIX Futures', type: 'futures', api: '^VIX'},
  {symbol: 'CL', name: 'Crude Oil Futures', type: 'futures', api: 'CL=F'},
  {symbol: 'NG', name: 'Natural Gas Futures', type: 'futures', api: 'NG=F'},
  {symbol: 'GC', name: 'Gold Futures', type: 'futures', api: 'GC=F'},
  {symbol: 'SI', name: 'Silver Futures', type: 'futures', api: 'SI=F'},
  {symbol: 'HG', name: 'Copper Futures', type: 'futures', api: 'HG=F'},
  {symbol: 'PL', name: 'Platinum Futures', type: 'futures', api: 'PL=F'},
  {symbol: 'ZC', name: 'Corn Futures', type: 'futures', api: 'ZC=F'},
  {symbol: 'ZS', name: 'Soybean Futures', type: 'futures', api: 'ZS=F'},
  {symbol: 'ZW', name: 'Wheat Futures', type: 'futures', api: 'ZW=F'},
  // 指數 Indices
  {symbol: 'SPX', name: 'S&P 500 Index', type: 'index', api: '^GSPC'},
  {symbol: 'DJI', name: 'Dow Jones Industrial Average', type: 'index', api: '^DJI'},
  {symbol: 'IXIC', name: 'Nasdaq Composite', type: 'index', api: '^IXIC'},
  {symbol: 'RUT', name: 'Russell 2000 Index', type: 'index', api: '^RUT'},
  {symbol: 'VIX', name: 'CBOE Volatility Index', type: 'index', api: '^VIX'},
  {symbol: 'FTSE', name: 'FTSE 100 Index', type: 'index', api: '^FTSE'},
  {symbol: 'N225', name: 'Nikkei 225 Index', type: 'index', api: '^N225'},
  {symbol: 'HSI', name: 'Hang Seng Index', type: 'index', api: '^HSI'},
  {symbol: 'GDAXI', name: 'DAX Index', type: 'index', api: '^GDAXI'},
  // 債券 Bonds
  {symbol: 'TNX', name: 'US 10-Year Treasury Yield', type: 'bond', api: '^TNX'},
  {symbol: 'TYX', name: 'US 30-Year Treasury Yield', type: 'bond', api: '^TYX'},
  {symbol: 'FVX', name: 'US 5-Year Treasury Yield', type: 'bond', api: '^FVX'},
  {symbol: 'TLT', name: 'iShares 20+ Year Treasury Bond ETF', type: 'bond'},
  {symbol: 'IEF', name: 'iShares 7-10 Year Treasury Bond ETF', type: 'bond'},
  {symbol: 'SHY', name: 'iShares 1-3 Year Treasury Bond ETF', type: 'bond'},
  {symbol: 'AGG', name: 'iShares Core US Aggregate Bond ETF', type: 'bond'},
  {symbol: 'BND', name: 'Vanguard Total Bond Market ETF', type: 'bond'},
  {symbol: 'HYG', name: 'iShares High Yield Corporate Bond ETF', type: 'bond'},
  {symbol: 'LQD', name: 'iShares Investment Grade Corporate Bond ETF', type: 'bond'},
  {symbol: 'VCIT', name: 'Vanguard Intermediate-Term Corporate Bond ETF', type: 'bond'},
  {symbol: 'VGIT', name: 'Vanguard Intermediate-Term Treasury ETF', type: 'bond'},
  {symbol: 'VGLT', name: 'Vanguard Long-Term Treasury ETF', type: 'bond'},
  {symbol: 'VGSH', name: 'Vanguard Short-Term Treasury ETF', type: 'bond'},
  {symbol: 'TIP', name: 'iShares TIPS Bond ETF', type: 'bond'},
  // 加密貨幣 Crypto
  {symbol: 'BTC', name: 'Bitcoin', type: 'crypto'},
  {symbol: 'ETH', name: 'Ethereum', type: 'crypto'},
  {symbol: 'SOL', name: 'Solana', type: 'crypto'},
  {symbol: 'BNB', name: 'Binance Coin', type: 'crypto'},
  {symbol: 'XRP', name: 'Ripple', type: 'crypto'},
  {symbol: 'DOGE', name: 'Dogecoin', type: 'crypto'},
  {symbol: 'ADA', name: 'Cardano', type: 'crypto'},
  {symbol: 'DOT', name: 'Polkadot', type: 'crypto'},
  {symbol: 'AVAX', name: 'Avalanche', type: 'crypto'},
  {symbol: 'LTC', name: 'Litecoin', type: 'crypto'},
  {symbol: 'LINK', name: 'Chainlink', type: 'crypto'},
  {symbol: 'MATIC', name: 'Polygon', type: 'crypto'},
  {symbol: 'SHIB', name: 'Shiba Inu', type: 'crypto'},
  {symbol: 'TRX', name: 'TRON', type: 'crypto'},
  {symbol: 'ATOM', name: 'Cosmos', type: 'crypto'},
  {symbol: 'VET', name: 'VeChain', type: 'crypto'},
];

// 向後兼容：舊code可能仍然引用STOCKS呢個名。
const STOCKS = ALL_TICKERS;

const TICKER_TYPE_LABEL = {
  stock: '股票', futures: '期貨', crypto: '加密貨幣', index: '指數', bond: '債券'
};

function initAutocomplete(inputId, dropdownId) {
  const input = document.getElementById(inputId);
  const dropdown = document.getElementById(dropdownId);
  if (!input || !dropdown) return;

  input.addEventListener('input', function() {
    const val = this.value.toUpperCase().trim();
    dropdown.innerHTML = '';
    if (!val) { dropdown.style.display = 'none'; return; }

    const matches = ALL_TICKERS.filter(s =>
      s.symbol.startsWith(val) || s.name.toUpperCase().includes(val)
    ).slice(0, 8);

    if (matches.length === 0) { dropdown.style.display = 'none'; return; }

    matches.forEach(s => {
      const item = document.createElement('div');
      item.style.cssText = 'padding:10px 14px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:10px;border-bottom:1px solid #1e2d45;';
      const typeLabel = TICKER_TYPE_LABEL[s.type] || '';
      item.innerHTML = `<span style="display:flex;align-items:center;gap:8px;min-width:0"><span style="font-weight:600;color:#e2e8f0;font-family:monospace">${s.symbol}</span><span style="font-size:0.72rem;color:#00d4ff;background:rgba(0,212,255,0.1);padding:1px 6px;border-radius:4px;white-space:nowrap">${typeLabel}</span></span><span style="font-size:0.78rem;color:#64748b;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${s.name}</span>`;
      item.onmouseenter = () => item.style.background = '#111d30';
      item.onmouseleave = () => item.style.background = 'transparent';
      item.onclick = () => {
        input.value = s.symbol;
        dropdown.style.display = 'none';
        input.dispatchEvent(new Event('change'));
      };
      dropdown.appendChild(item);
    });

    dropdown.style.cssText = 'display:block;position:absolute;background:#0d1525;border:1px solid #1e2d45;border-radius:8px;z-index:1000;min-width:280px;max-height:320px;overflow-y:auto;box-shadow:0 8px 24px rgba(0,0,0,0.4);';
  });

  document.addEventListener('click', e => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.style.display = 'none';
    }
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Escape') dropdown.style.display = 'none';
  });
}

// 通用版本，唔使成頁提前起返個dropdown元素同id -- 掛落任何ticker input
// 就得，dropdown自己隨input動態生成/定位。專頁（AI Analysis/Compare/
// News Denoise/Chart Analysis/Probability Scan/Anomaly Detection等）嘅
// 輸入格之前完全冇wire過autocomplete.js，用戶打「V」淨係打字，冇任何
// 建議跳出嚟 -- 而家用呢個helper一次過補晒。
//
// options.multi=true：用於逗號分隔嘅多代號輸入格（例如ai-analysis.html
// 嘅symbolInput："NVDA,AAPL,B" -> 淨係對最後一截"B"做比對，揀咗之後淨係
// 替換返最後一截，前面已經打嘅代號維持原狀）。
function attachTickerAutocomplete(input, options) {
  options = options || {};
  const multi = !!options.multi;
  if (!input || input.dataset.xflAcAttached) return;
  input.dataset.xflAcAttached = '1';

  const parent = input.parentElement;
  if (parent && getComputedStyle(parent).position === 'static') {
    parent.style.position = 'relative';
  }
  const dropdown = document.createElement('div');
  dropdown.style.display = 'none';
  if (parent) parent.appendChild(dropdown);

  function activeSegment() {
    if (!multi) return input.value.toUpperCase().trim();
    const parts = input.value.split(',');
    return (parts[parts.length - 1] || '').toUpperCase().trim();
  }

  function applySelection(symbol) {
    if (!multi) { input.value = symbol; return; }
    const parts = input.value.split(',').map(p => p.trim()).filter(Boolean);
    parts.pop(); // 移除仲未打完嘅最後一截
    parts.push(symbol);
    input.value = parts.join(',');
  }

  input.addEventListener('input', function() {
    const val = activeSegment();
    dropdown.innerHTML = '';
    if (!val) { dropdown.style.display = 'none'; return; }

    const matches = ALL_TICKERS.filter(s =>
      s.symbol.startsWith(val) || s.name.toUpperCase().includes(val)
    ).slice(0, 8);

    if (matches.length === 0) { dropdown.style.display = 'none'; return; }

    matches.forEach(s => {
      const item = document.createElement('div');
      item.style.cssText = 'padding:10px 14px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:10px;border-bottom:1px solid #1e2d45;';
      const typeLabel = TICKER_TYPE_LABEL[s.type] || '';
      item.innerHTML = `<span style="display:flex;align-items:center;gap:8px;min-width:0"><span style="font-weight:600;color:#e2e8f0;font-family:monospace">${s.symbol}</span><span style="font-size:0.72rem;color:#00d4ff;background:rgba(0,212,255,0.1);padding:1px 6px;border-radius:4px;white-space:nowrap">${typeLabel}</span></span><span style="font-size:0.78rem;color:#64748b;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-left:8px">${s.name}</span>`;
      item.onmouseenter = () => item.style.background = '#111d30';
      item.onmouseleave = () => item.style.background = 'transparent';
      item.onclick = () => {
        applySelection(s.symbol);
        dropdown.style.display = 'none';
        input.focus();
        input.dispatchEvent(new Event('change'));
      };
      dropdown.appendChild(item);
    });

    dropdown.style.cssText = 'display:block;position:absolute;top:100%;left:0;right:0;margin-top:4px;background:#0d1525;border:1px solid #1e2d45;border-radius:8px;z-index:1000;max-height:320px;overflow-y:auto;box-shadow:0 8px 24px rgba(0,0,0,0.4);';
  });

  document.addEventListener('click', e => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.style.display = 'none';
    }
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Escape') dropdown.style.display = 'none';
  });
}

// selectorOrElements：CSS selector字串，或者一個element/NodeList/Array。
function autoAttachTickerAutocomplete(selectorOrElements, options) {
  let els;
  if (typeof selectorOrElements === 'string') {
    els = document.querySelectorAll(selectorOrElements);
  } else if (selectorOrElements instanceof Element) {
    els = [selectorOrElements];
  } else {
    els = selectorOrElements || [];
  }
  els.forEach(el => attachTickerAutocomplete(el, options));
}
