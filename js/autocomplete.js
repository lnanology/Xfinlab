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
  // 港股 Hong Kong (symbol打法同normalizeGlobalTicker()一致，唔使打
  // ".HK"，揀咗之後系統自己識轉；api先至係真正查價用嘅完整代號)
  {symbol: '0700', name: 'Tencent Holdings 騰訊控股', type: 'stock', api: '0700.HK'},
  {symbol: '9988', name: 'Alibaba Group HK 阿里巴巴', type: 'stock', api: '9988.HK'},
  {symbol: '0005', name: 'HSBC Holdings 匯豐控股', type: 'stock', api: '0005.HK'},
  {symbol: '0941', name: 'China Mobile 中國移動', type: 'stock', api: '0941.HK'},
  {symbol: '3690', name: 'Meituan 美團', type: 'stock', api: '3690.HK'},
  {symbol: '1299', name: 'AIA Group 友邦保險', type: 'stock', api: '1299.HK'},
  {symbol: '0388', name: 'HKEX 香港交易所', type: 'stock', api: '0388.HK'},
  {symbol: '2318', name: 'Ping An Insurance 中國平安', type: 'stock', api: '2318.HK'},
  {symbol: '0016', name: 'Sun Hung Kai Properties 新鴻基地產', type: 'stock', api: '0016.HK'},
  {symbol: '1398', name: 'ICBC 工商銀行', type: 'stock', api: '1398.HK'},
  {symbol: '0027', name: 'Galaxy Entertainment 銀河娛樂', type: 'stock', api: '0027.HK'},
  {symbol: '2020', name: 'ANTA Sports 安踏體育', type: 'stock', api: '2020.HK'},
  // 台股 Taiwan
  {symbol: '2330', name: 'TSMC 台積電', type: 'stock', api: '2330.TW'},
  {symbol: '2317', name: 'Hon Hai (Foxconn) 鴻海', type: 'stock', api: '2317.TW'},
  {symbol: '2454', name: 'MediaTek 聯發科', type: 'stock', api: '2454.TW'},
  {symbol: '2412', name: 'Chunghwa Telecom 中華電信', type: 'stock', api: '2412.TW'},
  {symbol: '1301', name: 'Formosa Plastics 台塑', type: 'stock', api: '1301.TW'},
  {symbol: '2308', name: 'Delta Electronics 台達電', type: 'stock', api: '2308.TW'},
  {symbol: '2882', name: 'Cathay Financial 國泰金', type: 'stock', api: '2882.TW'},
  {symbol: '3008', name: 'LargAn Precision 大立光', type: 'stock', api: '3008.TW'},
  // 中國A股 China A-shares
  {symbol: '600519', name: 'Kweichow Moutai 貴州茅台', type: 'stock', api: '600519.SS'},
  {symbol: '601318', name: 'Ping An Insurance (A股) 中國平安', type: 'stock', api: '601318.SS'},
  {symbol: '000858', name: 'Wuliangye 五糧液', type: 'stock', api: '000858.SZ'},
  {symbol: '300750', name: 'CATL 寧德時代', type: 'stock', api: '300750.SZ'},
  // 日本 Japan
  {symbol: '7203', name: 'Toyota Motor トヨタ自動車', type: 'stock', api: '7203.T'},
  {symbol: '6758', name: 'Sony Group ソニーグループ', type: 'stock', api: '6758.T'},
  {symbol: '9984', name: 'SoftBank Group ソフトバンクグループ', type: 'stock', api: '9984.T'},
  {symbol: '9432', name: 'NTT 日本電信電話', type: 'stock', api: '9432.T'},
  // 南韓 South Korea
  {symbol: '005930', name: 'Samsung Electronics 삼성전자', type: 'stock', api: '005930.KS'},
  {symbol: '000660', name: 'SK Hynix SK하이닉스', type: 'stock', api: '000660.KS'},
  // 澳洲 Australia
  {symbol: 'BHP', name: 'BHP Group', type: 'stock', api: 'BHP.AX'},
  {symbol: 'CBA', name: 'Commonwealth Bank of Australia', type: 'stock', api: 'CBA.AX'},
  {symbol: 'CSL', name: 'CSL Limited', type: 'stock', api: 'CSL.AX'},
  // 印度 India
  {symbol: 'RELIANCE', name: 'Reliance Industries', type: 'stock', api: 'RELIANCE.NS'},
  {symbol: 'TCS', name: 'Tata Consultancy Services', type: 'stock', api: 'TCS.NS'},
  {symbol: 'INFY', name: 'Infosys', type: 'stock', api: 'INFY.NS'},
  // 泰國 Thailand
  {symbol: 'PTT', name: 'PTT Public Company', type: 'stock', api: 'PTT.BK'},
  {symbol: 'CPALL', name: 'CP All', type: 'stock', api: 'CPALL.BK'},
  {symbol: 'AOT', name: 'Airports of Thailand', type: 'stock', api: 'AOT.BK'},
  // 越南 Vietnam
  {symbol: 'VNM', name: 'Vinamilk 越南乳業', type: 'stock', api: 'VNM.VN'},
  {symbol: 'VIC', name: 'Vingroup', type: 'stock', api: 'VIC.VN'},
  // 印尼 Indonesia
  {symbol: 'BBCA', name: 'Bank Central Asia', type: 'stock', api: 'BBCA.JK'},
  {symbol: 'TLKM', name: 'Telkom Indonesia', type: 'stock', api: 'TLKM.JK'},
  // 馬來西亞 Malaysia
  {symbol: 'MAYBANK', name: 'Malayan Banking (Maybank)', type: 'stock', api: '1155.KL'},
  {symbol: 'PBBANK', name: 'Public Bank Berhad', type: 'stock', api: '1295.KL'},
  // 新加坡 Singapore
  {symbol: 'DBS', name: 'DBS Group Holdings', type: 'stock', api: 'D05.SI'},
  {symbol: 'OCBC', name: 'OCBC Bank', type: 'stock', api: 'O39.SI'},
  {symbol: 'SINGTEL', name: 'Singtel', type: 'stock', api: 'Z74.SI'},
  // 澳門 Macau（澳門博彩股主要喺港交所上市）
  {symbol: '1928', name: 'Sands China 金沙中國', type: 'stock', api: '1928.HK'},
  {symbol: '2282', name: 'MGM China 美高梅中國', type: 'stock', api: '2282.HK'},
  // 英國 UK
  {symbol: 'HSBA', name: 'HSBC Holdings (LSE)', type: 'stock', api: 'HSBA.L'},
  {symbol: 'BP', name: 'BP p.l.c.', type: 'stock', api: 'BP.L'},
  {symbol: 'AZN', name: 'AstraZeneca', type: 'stock', api: 'AZN.L'},
  {symbol: 'ULVR', name: 'Unilever plc', type: 'stock', api: 'ULVR.L'},
  // 法國 France
  {symbol: 'MC', name: 'LVMH', type: 'stock', api: 'MC.PA'},
  {symbol: 'OR', name: "L'Oréal", type: 'stock', api: 'OR.PA'},
  {symbol: 'TTE', name: 'TotalEnergies', type: 'stock', api: 'TTE.PA'},
  // 德國 Germany
  {symbol: 'SAP', name: 'SAP SE', type: 'stock', api: 'SAP.DE'},
  {symbol: 'SIE', name: 'Siemens AG', type: 'stock', api: 'SIE.DE'},
  {symbol: 'VOW3', name: 'Volkswagen AG', type: 'stock', api: 'VOW3.DE'},
  // 意大利 Italy
  {symbol: 'ENI', name: 'Eni S.p.A.', type: 'stock', api: 'ENI.MI'},
  {symbol: 'ISP', name: 'Intesa Sanpaolo', type: 'stock', api: 'ISP.MI'},
  {symbol: 'STLAM', name: 'Stellantis (Milan)', type: 'stock', api: 'STLAM.MI'},
  // 西班牙 Spain
  {symbol: 'SAN', name: 'Banco Santander', type: 'stock', api: 'SAN.MC'},
  {symbol: 'ITX', name: 'Inditex (Zara)', type: 'stock', api: 'ITX.MC'},
  {symbol: 'IBE', name: 'Iberdrola', type: 'stock', api: 'IBE.MC'},
  // 葡萄牙 Portugal
  {symbol: 'EDP', name: 'EDP - Energias de Portugal', type: 'stock', api: 'EDP.LS'},
  {symbol: 'GALP', name: 'Galp Energia', type: 'stock', api: 'GALP.LS'},
  // 奧地利 Austria
  {symbol: 'OMV', name: 'OMV AG', type: 'stock', api: 'OMV.VI'},
  {symbol: 'EBS', name: 'Erste Group Bank', type: 'stock', api: 'EBS.VI'},
  // 匈牙利 Hungary
  {symbol: 'OTP', name: 'OTP Bank', type: 'stock', api: 'OTP.BD'},
  {symbol: 'MOL', name: 'MOL Group', type: 'stock', api: 'MOL.BD'},
  // 俄羅斯 Russia（受制裁影響，即市數據可能唔齊全）
  {symbol: 'GAZP', name: 'Gazprom（數據可能受制裁影響）', type: 'stock', api: 'GAZP.ME'},
  {symbol: 'SBER', name: 'Sberbank（數據可能受制裁影響）', type: 'stock', api: 'SBER.ME'},
  // 中東 Middle East
  {symbol: '2222', name: 'Saudi Aramco', type: 'stock', api: '2222.SR'},
  {symbol: 'FAB', name: 'First Abu Dhabi Bank', type: 'stock', api: 'FAB.AD'},
  {symbol: 'EMAAR', name: 'Emaar Properties (Dubai)', type: 'stock', api: 'EMAAR.DU'},
  // 巴西 Brazil
  {symbol: 'VALE3', name: 'Vale S.A.', type: 'stock', api: 'VALE3.SA'},
  {symbol: 'PETR4', name: 'Petrobras', type: 'stock', api: 'PETR4.SA'},
  {symbol: 'ITUB4', name: 'Itaú Unibanco', type: 'stock', api: 'ITUB4.SA'},
  // 全球其他指數 More global indices
  {symbol: 'AXJO', name: 'ASX 200 Index (Australia)', type: 'index', api: '^AXJO'},
  {symbol: 'KS11', name: 'KOSPI Index (South Korea)', type: 'index', api: '^KS11'},
  {symbol: 'FCHI', name: 'CAC 40 Index (France)', type: 'index', api: '^FCHI'},
  {symbol: 'STOXX50E', name: 'Euro Stoxx 50 Index', type: 'index', api: '^STOXX50E'},
  {symbol: 'BSESN', name: 'BSE Sensex Index (India)', type: 'index', api: '^BSESN'},
  {symbol: 'STI', name: 'Straits Times Index (Singapore)', type: 'index', api: '^STI'},
  {symbol: 'KLSE', name: 'FTSE Bursa Malaysia KLCI', type: 'index', api: '^KLSE'},
  {symbol: 'JKSE', name: 'Jakarta Composite Index', type: 'index', api: '^JKSE'},
  {symbol: 'BVSP', name: 'Bovespa Index (Brazil)', type: 'index', api: '^BVSP'},
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
        // 有啲代號（港股/台股/期貨/指數/債息）真正查價要用嘅代號同
        // 畫面上顯示嘅唔一樣（例如"0700"顯示，但真正要查"0700.HK"），
        // s.api就係嗰個真正查價用嘅格式，冇嘅話先fallback用返symbol。
        input.value = s.api || s.symbol;
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
        applySelection(s.api || s.symbol);
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
