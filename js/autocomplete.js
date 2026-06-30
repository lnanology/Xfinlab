// XFINLAB Stock Autocomplete
const STOCKS = [
  {symbol: 'AAPL', name: 'Apple Inc.'},
  {symbol: 'NVDA', name: 'NVIDIA Corporation'},
  {symbol: 'TSLA', name: 'Tesla Inc.'},
  {symbol: 'MSFT', name: 'Microsoft Corporation'},
  {symbol: 'META', name: 'Meta Platforms Inc.'},
  {symbol: 'AMZN', name: 'Amazon.com Inc.'},
  {symbol: 'GOOGL', name: 'Alphabet Inc.'},
  {symbol: 'GOOG', name: 'Alphabet Inc. Class C'},
  {symbol: 'BRK', name: 'Berkshire Hathaway'},
  {symbol: 'JPM', name: 'JPMorgan Chase'},
  {symbol: 'V', name: 'Visa Inc.'},
  {symbol: 'UNH', name: 'UnitedHealth Group'},
  {symbol: 'XOM', name: 'Exxon Mobil'},
  {symbol: 'JNJ', name: 'Johnson & Johnson'},
  {symbol: 'WMT', name: 'Walmart Inc.'},
  {symbol: 'MA', name: 'Mastercard Inc.'},
  {symbol: 'PG', name: 'Procter & Gamble'},
  {symbol: 'ORCL', name: 'Oracle Corporation'},
  {symbol: 'HD', name: 'Home Depot'},
  {symbol: 'CVX', name: 'Chevron Corporation'},
  {symbol: 'MRK', name: 'Merck & Co.'},
  {symbol: 'ABBV', name: 'AbbVie Inc.'},
  {symbol: 'KO', name: 'Coca-Cola Company'},
  {symbol: 'PEP', name: 'PepsiCo Inc.'},
  {symbol: 'LLY', name: 'Eli Lilly'},
  {symbol: 'BAC', name: 'Bank of America'},
  {symbol: 'AMD', name: 'Advanced Micro Devices'},
  {symbol: 'COST', name: 'Costco Wholesale'},
  {symbol: 'AVGO', name: 'Broadcom Inc.'},
  {symbol: 'NFLX', name: 'Netflix Inc.'},
  {symbol: 'INTC', name: 'Intel Corporation'},
  {symbol: 'CRM', name: 'Salesforce Inc.'},
  {symbol: 'ADBE', name: 'Adobe Inc.'},
  {symbol: 'PYPL', name: 'PayPal Holdings'},
  {symbol: 'PLTR', name: 'Palantir Technologies'},
  {symbol: 'COIN', name: 'Coinbase Global'},
  {symbol: 'MSTR', name: 'MicroStrategy'},
  {symbol: 'SOFI', name: 'SoFi Technologies'},
  {symbol: 'RIVN', name: 'Rivian Automotive'},
  {symbol: 'NIO', name: 'NIO Inc.'},
  {symbol: 'BABA', name: 'Alibaba Group'},
  {symbol: 'TSM', name: 'Taiwan Semiconductor'},
  {symbol: 'SHOP', name: 'Shopify Inc.'},
  {symbol: 'SQ', name: 'Block Inc.'},
  {symbol: 'HOOD', name: 'Robinhood Markets'},
  {symbol: 'UBER', name: 'Uber Technologies'},
  {symbol: 'LYFT', name: 'Lyft Inc.'},
  {symbol: 'SNAP', name: 'Snap Inc.'},
  {symbol: 'TWTR', name: 'Twitter/X'},
  {symbol: 'DIS', name: 'Walt Disney Company'},
  {symbol: 'BA', name: 'Boeing Company'},
  {symbol: 'GE', name: 'General Electric'},
  {symbol: 'F', name: 'Ford Motor Company'},
  {symbol: 'GM', name: 'General Motors'},
  {symbol: 'AAL', name: 'American Airlines'},
  {symbol: 'DAL', name: 'Delta Air Lines'},
  {symbol: 'UAL', name: 'United Airlines'},
  {symbol: 'GS', name: 'Goldman Sachs'},
  {symbol: 'MS', name: 'Morgan Stanley'},
  {symbol: 'C', name: 'Citigroup Inc.'},
  {symbol: 'WFC', name: 'Wells Fargo'},
  {symbol: 'BTC', name: 'Bitcoin'},
  {symbol: 'ETH', name: 'Ethereum'},
  {symbol: 'SOL', name: 'Solana'},
  {symbol: 'BNB', name: 'Binance Coin'},
  {symbol: 'XRP', name: 'Ripple'},
  {symbol: 'DOGE', name: 'Dogecoin'},
];

function initAutocomplete(inputId, dropdownId) {
  const input = document.getElementById(inputId);
  const dropdown = document.getElementById(dropdownId);
  if (!input || !dropdown) return;

  input.addEventListener('input', function() {
    const val = this.value.toUpperCase().trim();
    dropdown.innerHTML = '';
    if (!val) { dropdown.style.display = 'none'; return; }

    const matches = STOCKS.filter(s =>
      s.symbol.startsWith(val) || s.name.toUpperCase().includes(val)
    ).slice(0, 8);

    if (matches.length === 0) { dropdown.style.display = 'none'; return; }

    matches.forEach(s => {
      const item = document.createElement('div');
      item.style.cssText = 'padding:10px 14px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1e2d45;';
      item.innerHTML = `<span style="font-weight:600;color:#e2e8f0;font-family:monospace">${s.symbol}</span><span style="font-size:0.78rem;color:#64748b">${s.name}</span>`;
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
