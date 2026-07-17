// XFINLAB Global Asset Search -- 媲美Interactive Brokers/Bloomberg/
// TradingView嘅全球資產搜尋框：股票/ETF/指數/外匯/商品/期貨/債券/加密
// 貨幣全部一齊搜，AI式辨識（symbol/公司全名/別名/模糊拼寫都搵到），
// 一個engine掛晒落主頁+8個功能頁+dashboard.html嘅所有輸入格，唔使
// 改動後端（純前端JS，唔靠新API）。
//
// 資料模型（Asset）刻意keep呢個形狀，方便日後如果要搬去後端一個共用
// 嘅Asset主資料表，前端呢層轉接layer(searchAssets/getAssetMeta)可以
// 原封不動繼續用，換嘅淨係下面呢個ASSETS array嘅來源（變成fetch API）：
//   symbol / name / aliases[] / type / api / country / exchange /
//   popularity / logo

const ASSETS = [
  // ===== 股票 Stocks (US) =====
  {symbol: 'AAPL', name: 'Apple Inc.', type: 'stock', aliases: ['apple', 'apple inc'], popularity: 100, logo: '🍎'},
  {symbol: 'NVDA', name: 'NVIDIA Corporation', type: 'stock', aliases: ['nvidia'], popularity: 99},
  {symbol: 'TSLA', name: 'Tesla Inc.', type: 'stock', aliases: ['tesla', 'tesla inc', 'tesla motors'], popularity: 98},
  {symbol: 'MSFT', name: 'Microsoft Corporation', type: 'stock', aliases: ['microsoft'], popularity: 98},
  {symbol: 'META', name: 'Meta Platforms Inc.', type: 'stock', aliases: ['meta', 'facebook', 'meta platforms'], popularity: 95},
  {symbol: 'AMZN', name: 'Amazon.com Inc.', type: 'stock', aliases: ['amazon'], popularity: 96},
  {symbol: 'GOOGL', name: 'Alphabet Inc.', type: 'stock', aliases: ['google', 'alphabet'], popularity: 96},
  {symbol: 'GOOG', name: 'Alphabet Inc. Class C', type: 'stock', aliases: ['google class c'], popularity: 80},
  {symbol: 'BRK', name: 'Berkshire Hathaway', type: 'stock', aliases: ['berkshire', 'berkshire hathaway', 'brk.b'], popularity: 85},
  {symbol: 'JPM', name: 'JPMorgan Chase', type: 'stock', aliases: ['jpmorgan', 'jp morgan'], popularity: 82},
  {symbol: 'V', name: 'Visa Inc.', type: 'stock', aliases: ['visa'], popularity: 84},
  {symbol: 'UNH', name: 'UnitedHealth Group', type: 'stock', aliases: ['unitedhealth'], popularity: 70},
  {symbol: 'XOM', name: 'Exxon Mobil', type: 'stock', aliases: ['exxon', 'exxonmobil'], popularity: 72},
  {symbol: 'JNJ', name: 'Johnson & Johnson', type: 'stock', aliases: ['johnson & johnson', 'johnson and johnson'], popularity: 70},
  {symbol: 'WMT', name: 'Walmart Inc.', type: 'stock', aliases: ['walmart'], popularity: 75},
  {symbol: 'MA', name: 'Mastercard Inc.', type: 'stock', aliases: ['mastercard'], popularity: 80},
  {symbol: 'PG', name: 'Procter & Gamble', type: 'stock', aliases: ['procter & gamble', 'procter and gamble'], popularity: 65},
  {symbol: 'ORCL', name: 'Oracle Corporation', type: 'stock', aliases: ['oracle'], popularity: 75},
  {symbol: 'HD', name: 'Home Depot', type: 'stock', aliases: ['home depot'], popularity: 68},
  {symbol: 'CVX', name: 'Chevron Corporation', type: 'stock', aliases: ['chevron'], popularity: 65},
  {symbol: 'MRK', name: 'Merck & Co.', type: 'stock', aliases: ['merck'], popularity: 62},
  {symbol: 'ABBV', name: 'AbbVie Inc.', type: 'stock', aliases: ['abbvie'], popularity: 60},
  {symbol: 'KO', name: 'Coca-Cola Company', type: 'stock', aliases: ['coca-cola', 'coca cola', 'coke'], popularity: 72},
  {symbol: 'PEP', name: 'PepsiCo Inc.', type: 'stock', aliases: ['pepsico', 'pepsi'], popularity: 65},
  {symbol: 'LLY', name: 'Eli Lilly', type: 'stock', aliases: ['eli lilly', 'lilly'], popularity: 68},
  {symbol: 'BAC', name: 'Bank of America', type: 'stock', aliases: ['bank of america', 'bofa'], popularity: 70},
  {symbol: 'AMD', name: 'Advanced Micro Devices', type: 'stock', aliases: ['amd'], popularity: 90},
  {symbol: 'COST', name: 'Costco Wholesale', type: 'stock', aliases: ['costco'], popularity: 72},
  {symbol: 'AVGO', name: 'Broadcom Inc.', type: 'stock', aliases: ['broadcom'], popularity: 82},
  {symbol: 'NFLX', name: 'Netflix Inc.', type: 'stock', aliases: ['netflix'], popularity: 85},
  {symbol: 'INTC', name: 'Intel Corporation', type: 'stock', aliases: ['intel'], popularity: 78},
  {symbol: 'CRM', name: 'Salesforce Inc.', type: 'stock', aliases: ['salesforce'], popularity: 68},
  {symbol: 'ADBE', name: 'Adobe Inc.', type: 'stock', aliases: ['adobe'], popularity: 78},
  {symbol: 'PYPL', name: 'PayPal Holdings', type: 'stock', aliases: ['paypal'], popularity: 68},
  {symbol: 'PLTR', name: 'Palantir Technologies', type: 'stock', aliases: ['palantir'], popularity: 80},
  {symbol: 'COIN', name: 'Coinbase Global', type: 'stock', aliases: ['coinbase'], popularity: 78},
  {symbol: 'MSTR', name: 'MicroStrategy', type: 'stock', aliases: ['microstrategy'], popularity: 70},
  {symbol: 'SOFI', name: 'SoFi Technologies', type: 'stock', aliases: ['sofi'], popularity: 55},
  {symbol: 'RIVN', name: 'Rivian Automotive', type: 'stock', aliases: ['rivian'], popularity: 55},
  {symbol: 'NIO', name: 'NIO Inc.', type: 'stock', aliases: ['nio'], popularity: 60},
  {symbol: 'BABA', name: 'Alibaba Group', type: 'stock', aliases: ['alibaba'], popularity: 78},
  {symbol: 'TSM', name: 'Taiwan Semiconductor (ADR)', type: 'stock', aliases: ['tsmc adr', 'taiwan semiconductor adr'], popularity: 82},
  {symbol: 'SHOP', name: 'Shopify Inc.', type: 'stock', aliases: ['shopify'], popularity: 65},
  {symbol: 'SQ', name: 'Block Inc.', type: 'stock', aliases: ['block', 'square'], popularity: 58},
  {symbol: 'HOOD', name: 'Robinhood Markets', type: 'stock', aliases: ['robinhood'], popularity: 62},
  {symbol: 'UBER', name: 'Uber Technologies', type: 'stock', aliases: ['uber'], popularity: 75},
  {symbol: 'LYFT', name: 'Lyft Inc.', type: 'stock', aliases: ['lyft'], popularity: 48},
  {symbol: 'SNAP', name: 'Snap Inc.', type: 'stock', aliases: ['snapchat', 'snap'], popularity: 45},
  {symbol: 'DIS', name: 'Walt Disney Company', type: 'stock', aliases: ['disney'], popularity: 72},
  {symbol: 'BA', name: 'Boeing Company', type: 'stock', aliases: ['boeing'], popularity: 65},
  {symbol: 'GE', name: 'General Electric', type: 'stock', aliases: ['general electric'], popularity: 55},
  {symbol: 'F', name: 'Ford Motor Company', type: 'stock', aliases: ['ford'], popularity: 55},
  {symbol: 'GM', name: 'General Motors', type: 'stock', aliases: ['general motors'], popularity: 55},
  {symbol: 'AAL', name: 'American Airlines', type: 'stock', aliases: ['american airlines'], popularity: 40},
  {symbol: 'DAL', name: 'Delta Air Lines', type: 'stock', aliases: ['delta airlines', 'delta'], popularity: 42},
  {symbol: 'UAL', name: 'United Airlines', type: 'stock', aliases: ['united airlines'], popularity: 40},
  {symbol: 'GS', name: 'Goldman Sachs', type: 'stock', aliases: ['goldman sachs', 'goldman'], popularity: 68},
  {symbol: 'MS', name: 'Morgan Stanley', type: 'stock', aliases: ['morgan stanley'], popularity: 62},
  {symbol: 'C', name: 'Citigroup Inc.', type: 'stock', aliases: ['citigroup', 'citi'], popularity: 58},
  {symbol: 'WFC', name: 'Wells Fargo', type: 'stock', aliases: ['wells fargo'], popularity: 58},
  {symbol: 'BLK', name: 'BlackRock Inc.', type: 'stock', aliases: ['blackrock'], popularity: 60},

  // ===== 期貨 Futures =====
  {symbol: 'ES', name: 'E-mini S&P 500 Futures', type: 'futures', api: 'ES=F', popularity: 70},
  {symbol: 'YM', name: 'E-mini Dow Futures', type: 'futures', api: 'YM=F', popularity: 55},
  {symbol: 'NQ', name: 'E-mini Nasdaq 100 Futures', type: 'futures', api: 'NQ=F', popularity: 65},
  {symbol: 'RTY', name: 'E-mini Russell 2000 Futures', type: 'futures', api: 'RTY=F', popularity: 45},
  {symbol: 'VX', name: 'VIX Futures', type: 'futures', api: '^VIX', popularity: 50},
  {symbol: 'CL', name: 'Crude Oil Futures (WTI)', type: 'futures', api: 'CL=F', aliases: ['wti', 'crude oil'], popularity: 68},
  {symbol: 'BZ', name: 'Brent Crude Futures', type: 'futures', api: 'BZ=F', aliases: ['brent', 'brent crude'], popularity: 60},
  {symbol: 'NG', name: 'Natural Gas Futures', type: 'futures', api: 'NG=F', aliases: ['natural gas'], popularity: 55},
  {symbol: 'GC', name: 'Gold Futures', type: 'futures', api: 'GC=F', aliases: ['gold futures'], popularity: 65},
  {symbol: 'SI', name: 'Silver Futures', type: 'futures', api: 'SI=F', aliases: ['silver futures'], popularity: 50},
  {symbol: 'HG', name: 'Copper Futures', type: 'futures', api: 'HG=F', aliases: ['copper'], popularity: 48},
  {symbol: 'PL', name: 'Platinum Futures', type: 'futures', api: 'PL=F', aliases: ['platinum'], popularity: 35},
  {symbol: 'ZC', name: 'Corn Futures', type: 'futures', api: 'ZC=F', popularity: 30},
  {symbol: 'ZS', name: 'Soybean Futures', type: 'futures', api: 'ZS=F', popularity: 30},
  {symbol: 'ZW', name: 'Wheat Futures', type: 'futures', api: 'ZW=F', popularity: 30},
  {symbol: 'HSIF', name: 'Hang Seng Index Futures', type: 'futures', api: '^HSI', aliases: ['hsi futures', 'hang seng futures'], country: 'Hong Kong', popularity: 40},
  {symbol: 'NKD', name: 'Nikkei 225 Futures', type: 'futures', api: '^N225', aliases: ['nikkei futures'], country: 'Japan', popularity: 35},

  // ===== 指數 Indices =====
  {symbol: 'SPX', name: 'S&P 500 Index', type: 'index', api: '^GSPC', aliases: ['s&p500', 's&p 500', 'sp500'], country: 'USA', popularity: 95},
  {symbol: 'DJI', name: 'Dow Jones Industrial Average', type: 'index', api: '^DJI', aliases: ['dow jones', 'dow'], country: 'USA', popularity: 85},
  {symbol: 'IXIC', name: 'Nasdaq Composite', type: 'index', api: '^IXIC', aliases: ['nasdaq'], country: 'USA', popularity: 85},
  {symbol: 'RUT', name: 'Russell 2000 Index', type: 'index', api: '^RUT', country: 'USA', popularity: 55},
  {symbol: 'VIX', name: 'CBOE Volatility Index', type: 'index', api: '^VIX', aliases: ['vix'], country: 'USA', popularity: 70},
  {symbol: 'FTSE', name: 'FTSE 100 Index', type: 'index', api: '^FTSE', country: 'UK', popularity: 55},
  {symbol: 'N225', name: 'Nikkei 225 Index', type: 'index', api: '^N225', aliases: ['nikkei'], country: 'Japan', popularity: 60},
  {symbol: 'HSI', name: 'Hang Seng Index', type: 'index', api: '^HSI', aliases: ['hang seng'], country: 'Hong Kong', popularity: 62},
  {symbol: 'GDAXI', name: 'DAX Index', type: 'index', api: '^GDAXI', aliases: ['dax'], country: 'Germany', popularity: 55},
  {symbol: 'TWII', name: 'Taiwan Weighted Index', type: 'index', api: '^TWII', aliases: ['taiwan index', 'taiwan etf'], country: 'Taiwan', popularity: 45},
  {symbol: 'AXJO', name: 'ASX 200 Index', type: 'index', api: '^AXJO', country: 'Australia', popularity: 40},
  {symbol: 'KS11', name: 'KOSPI Index', type: 'index', api: '^KS11', aliases: ['kospi'], country: 'South Korea', popularity: 42},
  {symbol: 'FCHI', name: 'CAC 40 Index', type: 'index', api: '^FCHI', aliases: ['cac40', 'cac 40'], country: 'France', popularity: 42},
  {symbol: 'STOXX50E', name: 'Euro Stoxx 50 Index', type: 'index', api: '^STOXX50E', country: 'Europe', popularity: 40},
  {symbol: 'BSESN', name: 'BSE Sensex Index', type: 'index', api: '^BSESN', aliases: ['sensex'], country: 'India', popularity: 45},
  {symbol: 'STI', name: 'Straits Times Index', type: 'index', api: '^STI', country: 'Singapore', popularity: 35},
  {symbol: 'KLSE', name: 'FTSE Bursa Malaysia KLCI', type: 'index', api: '^KLSE', country: 'Malaysia', popularity: 30},
  {symbol: 'JKSE', name: 'Jakarta Composite Index', type: 'index', api: '^JKSE', country: 'Indonesia', popularity: 30},
  {symbol: 'BVSP', name: 'Bovespa Index', type: 'index', api: '^BVSP', aliases: ['bovespa'], country: 'Brazil', popularity: 40},

  // ===== 外匯 Forex =====
  {symbol: 'EURUSD', name: 'Euro / US Dollar', type: 'forex', api: 'EURUSD=X', popularity: 75},
  {symbol: 'USDJPY', name: 'US Dollar / Japanese Yen', type: 'forex', api: 'USDJPY=X', popularity: 70},
  {symbol: 'GBPUSD', name: 'British Pound / US Dollar', type: 'forex', api: 'GBPUSD=X', popularity: 62},
  {symbol: 'AUDUSD', name: 'Australian Dollar / US Dollar', type: 'forex', api: 'AUDUSD=X', popularity: 50},
  {symbol: 'USDCNH', name: 'US Dollar / Chinese Yuan (Offshore)', type: 'forex', api: 'USDCNH=X', popularity: 55},
  {symbol: 'USDHKD', name: 'US Dollar / Hong Kong Dollar', type: 'forex', api: 'USDHKD=X', popularity: 40},

  // ===== 商品 Commodities =====
  {symbol: 'XAUUSD', name: 'Gold Spot', type: 'commodity', api: 'GC=F', aliases: ['gold'], popularity: 80},
  {symbol: 'XAGUSD', name: 'Silver Spot', type: 'commodity', api: 'SI=F', aliases: ['silver'], popularity: 45},

  // ===== ETF =====
  {symbol: 'QQQ', name: 'Invesco QQQ Trust (Nasdaq 100)', type: 'etf', popularity: 88},
  {symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', type: 'etf', popularity: 90},
  {symbol: 'VOO', name: 'Vanguard S&P 500 ETF', type: 'etf', aliases: ['vanguard'], popularity: 82},
  {symbol: 'ARKK', name: 'ARK Innovation ETF', type: 'etf', popularity: 55},
  {symbol: 'SOXX', name: 'iShares Semiconductor ETF', type: 'etf', popularity: 58},
  {symbol: 'EWT', name: 'iShares MSCI Taiwan ETF', type: 'etf', aliases: ['taiwan etf'], country: 'Taiwan', popularity: 40},
  {symbol: 'FBTC', name: 'Fidelity Wise Origin Bitcoin Fund', type: 'etf', aliases: ['fidelity'], popularity: 45},

  // ===== 債券 Bonds =====
  {symbol: 'TNX', name: 'US 10-Year Treasury Yield', type: 'bond', api: '^TNX', aliases: ['us10y'], country: 'USA', popularity: 65},
  {symbol: 'TYX', name: 'US 30-Year Treasury Yield', type: 'bond', api: '^TYX', aliases: ['us30y'], country: 'USA', popularity: 45},
  {symbol: 'FVX', name: 'US 5-Year Treasury Yield', type: 'bond', api: '^FVX', country: 'USA', popularity: 35},
  {symbol: 'TLT', name: 'iShares 20+ Year Treasury Bond ETF', type: 'bond', popularity: 55},
  {symbol: 'IEF', name: 'iShares 7-10 Year Treasury Bond ETF', type: 'bond', popularity: 40},
  {symbol: 'SHY', name: 'iShares 1-3 Year Treasury Bond ETF', type: 'bond', aliases: ['us02y'], popularity: 38},
  {symbol: 'AGG', name: 'iShares Core US Aggregate Bond ETF', type: 'bond', popularity: 42},
  {symbol: 'BND', name: 'Vanguard Total Bond Market ETF', type: 'bond', popularity: 40},
  {symbol: 'HYG', name: 'iShares High Yield Corporate Bond ETF', type: 'bond', popularity: 35},
  {symbol: 'LQD', name: 'iShares Investment Grade Corporate Bond ETF', type: 'bond', popularity: 32},
  {symbol: 'VCIT', name: 'Vanguard Intermediate-Term Corporate Bond ETF', type: 'bond', popularity: 30},
  {symbol: 'VGIT', name: 'Vanguard Intermediate-Term Treasury ETF', type: 'bond', popularity: 28},
  {symbol: 'VGLT', name: 'Vanguard Long-Term Treasury ETF', type: 'bond', popularity: 28},
  {symbol: 'VGSH', name: 'Vanguard Short-Term Treasury ETF', type: 'bond', popularity: 28},
  {symbol: 'TIP', name: 'iShares TIPS Bond ETF', type: 'bond', popularity: 30},

  // ===== 港股 Hong Kong (symbol打法同normalizeGlobalTicker()一致，
  // 唔使打".HK"，揀咗之後系統自己識轉；api先至係真正查價用嘅完整代號) =====
  {symbol: '0700', name: 'Tencent Holdings 騰訊控股', type: 'stock', api: '0700.HK', aliases: ['tencent'], popularity: 78},
  {symbol: '9988', name: 'Alibaba Group HK 阿里巴巴', type: 'stock', api: '9988.HK', aliases: ['alibaba hk'], popularity: 55},
  {symbol: '0005', name: 'HSBC Holdings 匯豐控股', type: 'stock', api: '0005.HK', aliases: ['hsbc'], popularity: 55},
  {symbol: '0941', name: 'China Mobile 中國移動', type: 'stock', api: '0941.HK', aliases: ['china mobile'], popularity: 40},
  {symbol: '3690', name: 'Meituan 美團', type: 'stock', api: '3690.HK', aliases: ['meituan'], popularity: 48},
  {symbol: '1299', name: 'AIA Group 友邦保險', type: 'stock', api: '1299.HK', aliases: ['aia'], popularity: 42},
  {symbol: '0388', name: 'HKEX 香港交易所', type: 'stock', api: '0388.HK', aliases: ['hkex'], popularity: 38},
  {symbol: '2318', name: 'Ping An Insurance 中國平安', type: 'stock', api: '2318.HK', aliases: ['ping an'], popularity: 40},
  {symbol: '0016', name: 'Sun Hung Kai Properties 新鴻基地產', type: 'stock', api: '0016.HK', popularity: 28},
  {symbol: '1398', name: 'ICBC 工商銀行', type: 'stock', api: '1398.HK', aliases: ['icbc'], popularity: 32},
  {symbol: '0027', name: 'Galaxy Entertainment 銀河娛樂', type: 'stock', api: '0027.HK', popularity: 30},
  {symbol: '2020', name: 'ANTA Sports 安踏體育', type: 'stock', api: '2020.HK', popularity: 28},

  // ===== 台股 Taiwan =====
  {symbol: '2330', name: 'TSMC 台積電', type: 'stock', api: '2330.TW', aliases: ['tsmc', 'taiwan semiconductor', 'taiwan'], popularity: 75},
  {symbol: '2317', name: 'Hon Hai (Foxconn) 鴻海', type: 'stock', api: '2317.TW', aliases: ['foxconn', 'hon hai'], popularity: 42},
  {symbol: '2454', name: 'MediaTek 聯發科', type: 'stock', api: '2454.TW', aliases: ['mediatek', 'taiwan'], popularity: 45},
  {symbol: '2412', name: 'Chunghwa Telecom 中華電信', type: 'stock', api: '2412.TW', popularity: 25},
  {symbol: '1301', name: 'Formosa Plastics 台塑', type: 'stock', api: '1301.TW', popularity: 22},
  {symbol: '2308', name: 'Delta Electronics 台達電', type: 'stock', api: '2308.TW', popularity: 30},
  {symbol: '2882', name: 'Cathay Financial 國泰金', type: 'stock', api: '2882.TW', popularity: 22},
  {symbol: '3008', name: 'LargAn Precision 大立光', type: 'stock', api: '3008.TW', popularity: 25},
  // 注意：3707係上櫃(TPEx)股票，唔係上市(TWSE)，Yahoo/yfinance代號要用
  // ".TWO"（唔係".TW"），呢個suffix分別成日搞錯，識落嚟落個comment提提。
  {symbol: '3707', name: 'Episil Technologies 漢磊', type: 'stock', api: '3707.TWO', country: 'Taiwan', exchange: 'TPEx', aliases: ['episil', 'hanlei'], popularity: 20},

  // ===== 中國A股 China A-shares =====
  {symbol: '600519', name: 'Kweichow Moutai 貴州茅台', type: 'stock', api: '600519.SS', aliases: ['moutai'], popularity: 42},
  {symbol: '601318', name: 'Ping An Insurance (A股) 中國平安', type: 'stock', api: '601318.SS', popularity: 32},
  {symbol: '000858', name: 'Wuliangye 五糧液', type: 'stock', api: '000858.SZ', popularity: 25},
  {symbol: '300750', name: 'CATL 寧德時代', type: 'stock', api: '300750.SZ', aliases: ['catl'], popularity: 35},

  // ===== 日本 Japan =====
  {symbol: '7203', name: 'Toyota Motor トヨタ自動車', type: 'stock', api: '7203.T', aliases: ['toyota'], popularity: 55},
  {symbol: '6758', name: 'Sony Group ソニーグループ', type: 'stock', api: '6758.T', aliases: ['sony'], popularity: 55},
  {symbol: '9984', name: 'SoftBank Group ソフトバンクグループ', type: 'stock', api: '9984.T', aliases: ['softbank'], popularity: 45},
  {symbol: '9432', name: 'NTT 日本電信電話', type: 'stock', api: '9432.T', popularity: 25},

  // ===== 南韓 South Korea =====
  {symbol: '005930', name: 'Samsung Electronics 삼성전자', type: 'stock', api: '005930.KS', aliases: ['samsung'], popularity: 60},
  {symbol: '000660', name: 'SK Hynix SK하이닉스', type: 'stock', api: '000660.KS', aliases: ['sk hynix'], popularity: 42},

  // ===== 澳洲 Australia =====
  {symbol: 'BHP', name: 'BHP Group', type: 'stock', api: 'BHP.AX', popularity: 35},
  {symbol: 'CBA', name: 'Commonwealth Bank of Australia', type: 'stock', api: 'CBA.AX', popularity: 28},
  {symbol: 'CSL', name: 'CSL Limited', type: 'stock', api: 'CSL.AX', popularity: 25},

  // ===== 印度 India =====
  {symbol: 'RELIANCE', name: 'Reliance Industries', type: 'stock', api: 'RELIANCE.NS', popularity: 40},
  {symbol: 'TCS', name: 'Tata Consultancy Services', type: 'stock', api: 'TCS.NS', popularity: 32},
  {symbol: 'INFY', name: 'Infosys', type: 'stock', api: 'INFY.NS', popularity: 30},

  // ===== 泰國 Thailand =====
  {symbol: 'PTT', name: 'PTT Public Company', type: 'stock', api: 'PTT.BK', popularity: 22},
  {symbol: 'CPALL', name: 'CP All', type: 'stock', api: 'CPALL.BK', popularity: 18},
  {symbol: 'AOT', name: 'Airports of Thailand', type: 'stock', api: 'AOT.BK', popularity: 18},

  // ===== 越南 Vietnam =====
  {symbol: 'VNM', name: 'Vinamilk 越南乳業', type: 'stock', api: 'VNM.VN', aliases: ['vinamilk'], popularity: 18},
  {symbol: 'VIC', name: 'Vingroup', type: 'stock', api: 'VIC.VN', aliases: ['vingroup'], popularity: 18},

  // ===== 印尼 Indonesia =====
  {symbol: 'BBCA', name: 'Bank Central Asia', type: 'stock', api: 'BBCA.JK', popularity: 18},
  {symbol: 'TLKM', name: 'Telkom Indonesia', type: 'stock', api: 'TLKM.JK', popularity: 18},

  // ===== 馬來西亞 Malaysia =====
  {symbol: 'MAYBANK', name: 'Malayan Banking (Maybank)', type: 'stock', api: '1155.KL', aliases: ['maybank'], popularity: 18},
  {symbol: 'PBBANK', name: 'Public Bank Berhad', type: 'stock', api: '1295.KL', popularity: 16},

  // ===== 新加坡 Singapore =====
  {symbol: 'DBS', name: 'DBS Group Holdings', type: 'stock', api: 'D05.SI', popularity: 25},
  {symbol: 'OCBC', name: 'OCBC Bank', type: 'stock', api: 'O39.SI', popularity: 20},
  {symbol: 'SINGTEL', name: 'Singtel', type: 'stock', api: 'Z74.SI', popularity: 18},

  // ===== 澳門 Macau（澳門博彩股主要喺港交所上市） =====
  {symbol: '1928', name: 'Sands China 金沙中國', type: 'stock', api: '1928.HK', aliases: ['sands china', 'macau'], popularity: 25},
  {symbol: '2282', name: 'MGM China 美高梅中國', type: 'stock', api: '2282.HK', aliases: ['mgm china', 'macau'], popularity: 20},

  // ===== 英國 UK =====
  {symbol: 'HSBA', name: 'HSBC Holdings (LSE)', type: 'stock', api: 'HSBA.L', popularity: 30},
  {symbol: 'BP', name: 'BP p.l.c.', type: 'stock', api: 'BP.L', popularity: 32},
  {symbol: 'AZN', name: 'AstraZeneca', type: 'stock', api: 'AZN.L', popularity: 35},
  {symbol: 'ULVR', name: 'Unilever plc', type: 'stock', api: 'ULVR.L', popularity: 25},

  // ===== 法國 France =====
  {symbol: 'MC', name: 'LVMH', type: 'stock', api: 'MC.PA', aliases: ['lvmh'], popularity: 35},
  {symbol: 'OR', name: "L'Oréal", type: 'stock', api: 'OR.PA', aliases: ["l'oreal", 'loreal'], popularity: 28},
  {symbol: 'TTE', name: 'TotalEnergies', type: 'stock', api: 'TTE.PA', popularity: 28},

  // ===== 德國 Germany =====
  {symbol: 'SAP', name: 'SAP SE', type: 'stock', api: 'SAP.DE', popularity: 35},
  {symbol: 'SIE', name: 'Siemens AG', type: 'stock', api: 'SIE.DE', aliases: ['siemens'], popularity: 30},
  {symbol: 'VOW3', name: 'Volkswagen AG', type: 'stock', api: 'VOW3.DE', aliases: ['volkswagen'], popularity: 30},
  {symbol: 'BMW', name: 'Bayerische Motoren Werke AG', type: 'stock', api: 'BMW.DE', aliases: ['bmw'], popularity: 32},

  // ===== 意大利 Italy =====
  {symbol: 'ENI', name: 'Eni S.p.A.', type: 'stock', api: 'ENI.MI', popularity: 20},
  {symbol: 'ISP', name: 'Intesa Sanpaolo', type: 'stock', api: 'ISP.MI', popularity: 18},
  {symbol: 'STLAM', name: 'Stellantis (Milan)', type: 'stock', api: 'STLAM.MI', aliases: ['stellantis'], popularity: 22},

  // ===== 西班牙 Spain =====
  {symbol: 'SAN', name: 'Banco Santander', type: 'stock', api: 'SAN.MC', aliases: ['santander'], popularity: 25},
  {symbol: 'ITX', name: 'Inditex (Zara)', type: 'stock', api: 'ITX.MC', aliases: ['zara', 'inditex'], popularity: 22},
  {symbol: 'IBE', name: 'Iberdrola', type: 'stock', api: 'IBE.MC', popularity: 18},

  // ===== 葡萄牙 Portugal =====
  {symbol: 'EDP', name: 'EDP - Energias de Portugal', type: 'stock', api: 'EDP.LS', popularity: 12},
  {symbol: 'GALP', name: 'Galp Energia', type: 'stock', api: 'GALP.LS', popularity: 12},

  // ===== 奧地利 Austria =====
  {symbol: 'OMV', name: 'OMV AG', type: 'stock', api: 'OMV.VI', popularity: 12},
  {symbol: 'EBS', name: 'Erste Group Bank', type: 'stock', api: 'EBS.VI', popularity: 12},

  // ===== 匈牙利 Hungary =====
  {symbol: 'OTP', name: 'OTP Bank', type: 'stock', api: 'OTP.BD', popularity: 12},
  {symbol: 'MOL', name: 'MOL Group', type: 'stock', api: 'MOL.BD', popularity: 12},

  // ===== 俄羅斯 Russia（受制裁影響，即市數據可能唔齊全） =====
  {symbol: 'GAZP', name: 'Gazprom（數據可能受制裁影響）', type: 'stock', api: 'GAZP.ME', popularity: 15},
  {symbol: 'SBER', name: 'Sberbank（數據可能受制裁影響）', type: 'stock', api: 'SBER.ME', popularity: 15},

  // ===== 中東 Middle East =====
  {symbol: '2222', name: 'Saudi Aramco', type: 'stock', api: '2222.SR', aliases: ['aramco', 'saudi aramco'], popularity: 30},
  {symbol: 'FAB', name: 'First Abu Dhabi Bank', type: 'stock', api: 'FAB.AD', popularity: 15},
  {symbol: 'EMAAR', name: 'Emaar Properties (Dubai)', type: 'stock', api: 'EMAAR.DU', popularity: 15},

  // ===== 巴西 Brazil =====
  {symbol: 'VALE3', name: 'Vale S.A.', type: 'stock', api: 'VALE3.SA', aliases: ['vale'], popularity: 25},
  {symbol: 'PETR4', name: 'Petrobras', type: 'stock', api: 'PETR4.SA', aliases: ['petrobras'], popularity: 25},
  {symbol: 'ITUB4', name: 'Itaú Unibanco', type: 'stock', api: 'ITUB4.SA', aliases: ['itau'], popularity: 18},

  // ===== 加拿大 Canada =====
  {symbol: 'RY', name: 'Royal Bank of Canada', type: 'stock', api: 'RY.TO', popularity: 25},
  {symbol: 'SHOPTO', name: 'Shopify (Toronto)', type: 'stock', api: 'SHOP.TO', aliases: ['shopify canada'], popularity: 20},
  {symbol: 'ENB', name: 'Enbridge Inc.', type: 'stock', api: 'ENB.TO', popularity: 20},

  // ===== 加密貨幣 Crypto =====
  {symbol: 'BTC', name: 'Bitcoin', type: 'crypto', aliases: ['bitcoin'], popularity: 100},
  {symbol: 'ETH', name: 'Ethereum', type: 'crypto', aliases: ['ethereum'], popularity: 90},
  {symbol: 'SOL', name: 'Solana', type: 'crypto', aliases: ['solana'], popularity: 75},
  {symbol: 'BNB', name: 'Binance Coin', type: 'crypto', aliases: ['binance coin', 'binance'], popularity: 65},
  {symbol: 'XRP', name: 'Ripple', type: 'crypto', aliases: ['ripple'], popularity: 70},
  {symbol: 'DOGE', name: 'Dogecoin', type: 'crypto', aliases: ['dogecoin', 'doge'], popularity: 68},
  {symbol: 'ADA', name: 'Cardano', type: 'crypto', aliases: ['cardano'], popularity: 55},
  {symbol: 'DOT', name: 'Polkadot', type: 'crypto', aliases: ['polkadot'], popularity: 45},
  {symbol: 'AVAX', name: 'Avalanche', type: 'crypto', aliases: ['avalanche'], popularity: 48},
  {symbol: 'LTC', name: 'Litecoin', type: 'crypto', aliases: ['litecoin'], popularity: 50},
  {symbol: 'LINK', name: 'Chainlink', type: 'crypto', aliases: ['chainlink'], popularity: 48},
  {symbol: 'MATIC', name: 'Polygon', type: 'crypto', aliases: ['polygon'], popularity: 45},
  {symbol: 'SHIB', name: 'Shiba Inu', type: 'crypto', aliases: ['shiba inu', 'shiba'], popularity: 42},
  {symbol: 'TRX', name: 'TRON', type: 'crypto', aliases: ['tron'], popularity: 38},
  {symbol: 'ATOM', name: 'Cosmos', type: 'crypto', aliases: ['cosmos'], popularity: 30},
  {symbol: 'VET', name: 'VeChain', type: 'crypto', aliases: ['vechain'], popularity: 25},
];

// 向後兼容：舊code可能仍然引用ALL_TICKERS/STOCKS呢兩個名。
const ALL_TICKERS = ASSETS;
const STOCKS = ASSETS;

const TICKER_TYPE_LABEL = {
  stock: '股票', etf: 'ETF', futures: '期貨', crypto: '加密貨幣',
  index: '指數', bond: '債券', forex: '外匯', commodity: '商品'
};

const TICKER_TYPE_LOGO = {
  stock: '🏢', etf: '📦', futures: '📑', crypto: '₿',
  index: '📈', bond: '🏦', forex: '💱', commodity: '🪙'
};

// 每個資產類別自己嘅代表emoji（部份headline資產有專屬icon，冇嘅話就
// fallback用返TICKER_TYPE_LOGO嗰個大類icon）。
const SYMBOL_LOGO_OVERRIDE = {
  AAPL: '🍎', TSLA: '🚗', GOOGL: '🔍', GOOG: '🔍', AMZN: '📦',
  MSFT: '🪟', META: '📘', NVDA: '🎮', BTC: '₿', ETH: 'Ξ',
  XAUUSD: '🥇', XAGUSD: '🥈', GC: '🥇', SI: '🥈', CL: '🛢️', BZ: '🛢️'
};

// suffix -> {exchange, country}，用嚟自動推斷股票嘅交易所/國家，唔使
// 逐隻手打（202個資產入面九成都可以靠呢個表自動配到）。
const EXCHANGE_SUFFIX_MAP = {
  '.HK': {exchange: 'HKEX', country: 'Hong Kong'},
  '.TW': {exchange: 'TWSE', country: 'Taiwan'},
  '.SS': {exchange: 'SSE', country: 'China'},
  '.SZ': {exchange: 'SZSE', country: 'China'},
  '.T': {exchange: 'TSE', country: 'Japan'},
  '.KS': {exchange: 'KRX', country: 'South Korea'},
  '.AX': {exchange: 'ASX', country: 'Australia'},
  '.NS': {exchange: 'NSE', country: 'India'},
  '.BK': {exchange: 'SET', country: 'Thailand'},
  '.VN': {exchange: 'HOSE', country: 'Vietnam'},
  '.JK': {exchange: 'IDX', country: 'Indonesia'},
  '.KL': {exchange: 'Bursa Malaysia', country: 'Malaysia'},
  '.SI': {exchange: 'SGX', country: 'Singapore'},
  '.L': {exchange: 'LSE', country: 'UK'},
  '.PA': {exchange: 'Euronext Paris', country: 'France'},
  '.DE': {exchange: 'XETRA', country: 'Germany'},
  '.MI': {exchange: 'Borsa Italiana', country: 'Italy'},
  '.MC': {exchange: 'BME', country: 'Spain'},
  '.LS': {exchange: 'Euronext Lisbon', country: 'Portugal'},
  '.VI': {exchange: 'Wiener Börse', country: 'Austria'},
  '.BD': {exchange: 'Budapest SE', country: 'Hungary'},
  '.ME': {exchange: 'MOEX', country: 'Russia'},
  '.SR': {exchange: 'Tadawul', country: 'Saudi Arabia'},
  '.AD': {exchange: 'ADX', country: 'UAE'},
  '.DU': {exchange: 'DFM', country: 'UAE'},
  '.SA': {exchange: 'B3', country: 'Brazil'},
  '.TO': {exchange: 'TSX', country: 'Canada'},
};

function getAssetMeta(a) {
  if (a.country && a.exchange) return {country: a.country, exchange: a.exchange};
  if (a.type === 'crypto') return {exchange: 'Crypto', country: a.country || 'Global'};
  if (a.type === 'forex') return {exchange: 'Forex', country: a.country || 'Global'};
  if (a.type === 'commodity') return {exchange: 'Commodity', country: a.country || 'Global'};
  if (a.type === 'futures') return {exchange: 'Futures', country: a.country || 'Global'};
  if (a.type === 'bond') return {exchange: 'Bond', country: a.country || 'USA'};
  if (a.type === 'index') return {exchange: 'Index', country: a.country || 'Global'};
  const api = a.api || a.symbol;
  for (const suf in EXCHANGE_SUFFIX_MAP) {
    if (api.endsWith(suf)) {
      const m = EXCHANGE_SUFFIX_MAP[suf];
      return {exchange: a.exchange || m.exchange, country: a.country || m.country};
    }
  }
  return {exchange: a.exchange || 'NASDAQ/NYSE', country: a.country || 'USA'};
}

function getAssetLogo(a) {
  return SYMBOL_LOGO_OVERRIDE[a.symbol] || TICKER_TYPE_LOGO[a.type] || '💹';
}

// ---- Levenshtein edit distance，用嚟做「Did you mean」拼寫修正 ----
function _levenshtein(a, b) {
  a = (a || '').toLowerCase();
  b = (b || '').toLowerCase();
  const dp = [];
  for (let i = 0; i <= a.length; i++) dp.push([i].concat(new Array(b.length).fill(0)));
  for (let j = 0; j <= b.length; j++) dp[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      dp[i][j] = a[i - 1] === b[j - 1]
        ? dp[i - 1][j - 1]
        : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
    }
  }
  return dp[a.length][b.length];
}

// ---- AI式排序搜尋：完全符合 > Ticker前綴 > 名稱/別名前綴 >
// 名稱/別名包含 > 熱門程度 > 拼寫修正(fuzzy) ----
function searchAssets(query, limit) {
  limit = limit || 8;
  const raw = (query || '').trim();
  if (!raw) return {results: [], suggestion: null};
  const q = raw.toLowerCase();
  const qUpper = raw.toUpperCase();

  const scored = [];
  ASSETS.forEach(a => {
    const symbolUpper = a.symbol.toUpperCase();
    const nameLower = a.name.toLowerCase();
    const aliases = a.aliases || [];
    let score = 0;
    let matched = false;

    if (symbolUpper === qUpper) { score = 1000; matched = true; }
    else if (symbolUpper.startsWith(qUpper)) { score = 800 - (symbolUpper.length - qUpper.length); matched = true; }
    else if (aliases.some(al => al === q)) { score = 760; matched = true; }
    else if (nameLower === q) { score = 750; matched = true; }
    else if (aliases.some(al => al.startsWith(q))) { score = 700; matched = true; }
    else if (nameLower.startsWith(q)) { score = 690; matched = true; }
    else if (aliases.some(al => al.includes(q))) { score = 520; matched = true; }
    else if (nameLower.includes(q)) { score = 500; matched = true; }

    if (matched) {
      score += (a.popularity || 30) * 0.4;
      scored.push({asset: a, score});
    }
  });

  scored.sort((x, y) => y.score - x.score);
  const results = scored.slice(0, limit).map(s => s.asset);

  // 冇搵到任何match，先至試下拼寫修正 (例如 "Bitcion" -> Bitcoin)
  let suggestion = null;
  if (results.length === 0 && q.length >= 3) {
    let best = null;
    let bestDist = Infinity;
    ASSETS.forEach(a => {
      const candidates = [a.symbol, a.name].concat(a.aliases || []);
      candidates.forEach(c => {
        const cl = c.toLowerCase();
        const dist = _levenshtein(q, cl.slice(0, q.length + 4));
        if (dist < bestDist) { bestDist = dist; best = a; }
      });
    });
    const threshold = Math.max(2, Math.floor(q.length * 0.4));
    if (best && bestDist <= threshold) suggestion = best;
  }

  return {results, suggestion};
}

// ---- 熱門搜尋 (未輸入任何嘢、focus緊個input時顯示) ----
// 國際/預設清單 -- 冇偵測到地區、或者本地熱門股未攞到之前，用呢個頂住。
const TRENDING_SYMBOLS = ['AAPL', 'TSLA', 'NVDA', 'BTC', 'SPX', 'XAUUSD'];
function getInternationalTrending() {
  return TRENDING_SYMBOLS.map(sym => ASSETS.find(a => a.symbol === sym)).filter(Boolean);
}

// 本地優先熱門股 -- 根據js/i18n.js偵測、cache落嚟嘅IP地區
// (localStorage 'xfinlab_country')，問後端 /api/trending-stocks 攞返
// 「呢個地區而家最多人交投嘅股票」，排先於國際清單。全session淨係
// fetch一次；未攞到之前getTrendingAssets()淨係會返返國際清單，
// 唔會block住個dropdown。攞到之後，如果個dropdown仲喺度顯示緊
// trending狀態，就會即時reflow顯示返本地清單上去。
let _localTrendingAssets = null;
let _localTrendingFetchPromise = null;
const _trendingRefreshCallbacks = [];

function _getCachedCountry() {
  try { return localStorage.getItem('xfinlab_country') || null; } catch (e) { return null; }
}

function _fetchLocalTrending() {
  if (_localTrendingFetchPromise) return _localTrendingFetchPromise;
  const country = _getCachedCountry();
  if (!country) { _localTrendingFetchPromise = Promise.resolve(null); return _localTrendingFetchPromise; }

  _localTrendingFetchPromise = fetch(`https://api.xfinlab.com/api/trending-stocks?country=${encodeURIComponent(country)}`)
    .then(res => res.json())
    .then(data => {
      const stocks = (data && data.stocks) || [];
      _localTrendingAssets = stocks.map(s => ({
        symbol: s.symbol,
        name: s.name,
        type: 'stock',
        popularity: 90
      }));
      _trendingRefreshCallbacks.forEach(cb => { try { cb(); } catch (e) {} });
      return _localTrendingAssets;
    })
    .catch(() => null);
  return _localTrendingFetchPromise;
}

function getTrendingAssets() {
  if (_localTrendingAssets === null) _fetchLocalTrending(); // fire-and-forget，唔阻住即時顯示
  const intl = getInternationalTrending();
  if (_localTrendingAssets && _localTrendingAssets.length) {
    return _localTrendingAssets.concat(intl);
  }
  return intl;
}

// ---- 最近搜尋 (localStorage，全站共用一個key，所有頁面睇到同一份) ----
const RECENT_KEY = 'xfl_recent_search_assets';
function getRecentAssets() {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    const list = raw ? JSON.parse(raw) : [];
    return list.map(sym => ASSETS.find(a => a.symbol === sym)).filter(Boolean);
  } catch (e) { return []; }
}
function recordRecentAsset(asset) {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    let list = raw ? JSON.parse(raw) : [];
    list = list.filter(s => s !== asset.symbol);
    list.unshift(asset.symbol);
    list = list.slice(0, 6);
    localStorage.setItem(RECENT_KEY, JSON.stringify(list));
  } catch (e) {}
}

// ---- 打字時輪流轉嘅placeholder範例 ----
const PLACEHOLDER_ROTATION = [
  'Search Stocks, ETFs, Crypto...', 'Try AAPL', 'Try BTC', 'Try EURUSD',
  'Try Gold', 'Try S&P 500', 'Search any global asset...'
];

function _renderAssetRow(a, extraAttrs) {
  const meta = getAssetMeta(a);
  const logo = getAssetLogo(a);
  // Note: this row intentionally does NOT show a "Stock/ETF/Crypto"
  // type badge anymore -- removed per feedback that the type label
  // (TICKER_TYPE_LABEL) was noisy/unnecessary in the dropdown. The
  // exchange + country columns already carry enough context.
  return `<div class="xfl-asset-row" ${extraAttrs || ''} style="padding:9px 14px;cursor:pointer;display:flex;align-items:center;gap:10px;border-bottom:1px solid #1e2d45;">
    <span style="font-size:1.05rem;width:22px;text-align:center;flex-shrink:0">${logo}</span>
    <span style="font-weight:600;color:#e2e8f0;font-family:monospace;min-width:64px;flex-shrink:0">${a.symbol}</span>
    <span style="font-size:0.78rem;color:#94a3b8;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${a.name}</span>
    <span style="font-size:0.68rem;color:#64748b;white-space:nowrap;flex-shrink:0">${meta.exchange}</span>
    <span style="font-size:0.68rem;color:#64748b;white-space:nowrap;flex-shrink:0;min-width:44px;text-align:right">${meta.country}</span>
  </div>`;
}

function initAutocomplete(inputId, dropdownId) {
  const input = document.getElementById(inputId);
  const dropdown = document.getElementById(dropdownId);
  if (!input || !dropdown) return;
  attachTickerAutocomplete(input, {existingDropdown: dropdown});
}

// 通用版本，唔使成頁提前起返個dropdown元素同id -- 掛落任何ticker/資產
// input就得，dropdown自己隨input動態生成/定位。全球資產搜尋引擎，
// 涵蓋股票/ETF/指數/外匯/商品/期貨/債券/加密貨幣，AI式辨識公司全名/
// 別名，容錯模糊搜尋+拼寫修正(Did you mean)，熱門/最近搜尋，鍵盤
// 上下/Enter/ESC/Tab全支援。
//
// options.multi=true：用於逗號分隔嘅多代號輸入格（例如ai-analysis.html
// 嘅symbolInput："NVDA,AAPL,B" -> 淨係對最後一截"B"做比對，揀咗之後淨係
// 替換返最後一截，前面已經打嘅代號維持原狀）。
function attachTickerAutocomplete(input, options) {
  options = options || {};
  const multi = !!options.multi;
  if (!input || input.dataset.xflAcAttached) return;
  input.dataset.xflAcAttached = '1';

  let dropdown = options.existingDropdown;
  if (!dropdown) {
    const parent = input.parentElement;
    if (parent && getComputedStyle(parent).position === 'static') {
      parent.style.position = 'relative';
    }
    dropdown = document.createElement('div');
    if (parent) parent.appendChild(dropdown);
  }
  dropdown.style.display = 'none';

  let currentResults = [];
  let currentSuggestion = null;
  let activeIndex = -1;

  function activeSegment() {
    if (!multi) return input.value.trim();
    const parts = input.value.split(',');
    return (parts[parts.length - 1] || '').trim();
  }

  function applySelection(symbol) {
    if (!multi) { input.value = symbol; return; }
    const parts = input.value.split(',').map(p => p.trim()).filter(Boolean);
    parts.pop(); // 移除仲未打完嘅最後一截
    parts.push(symbol);
    input.value = parts.join(',');
  }

  function closeDropdown() {
    dropdown.style.display = 'none';
    activeIndex = -1;
  }

  function highlight() {
    const rows = dropdown.querySelectorAll('.xfl-asset-row');
    rows.forEach((r, i) => {
      r.style.background = i === activeIndex ? '#131c2e' : 'transparent';
    });
  }

  function selectAsset(asset) {
    applySelection(asset.api || asset.symbol);
    recordRecentAsset(asset);
    closeDropdown();
    input.dispatchEvent(new Event('change'));
  }

  function renderSection(title, assets) {
    if (!assets.length) return '';
    const header = `<div style="padding:8px 14px 4px;font-size:0.68rem;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#64748b">${title}</div>`;
    return header + assets.map(a => _renderAssetRow(a)).join('');
  }

  function renderEmptyState() {
    const trending = getTrendingAssets();
    let html;
    if (_localTrendingAssets && _localTrendingAssets.length) {
      const localPart = trending.slice(0, _localTrendingAssets.length);
      const intlPart = trending.slice(_localTrendingAssets.length);
      html = renderSection('🔥 本地熱門', localPart) + renderSection('🌍 國際市場', intlPart) + renderSection('🕓 Recent', getRecentAssets());
    } else {
      html = renderSection('🔥 Trending', trending) + renderSection('🕓 Recent', getRecentAssets());
    }
    dropdown.innerHTML = html;
    currentResults = trending.concat(getRecentAssets());
    currentSuggestion = null;
    wireRowClicks();
    dropdown.style.display = currentResults.length ? 'block' : 'none';
  }

  // 本地熱門股攞到之後 (async)，如果呢個dropdown仲focus緊、仲顯示緊
  // trending狀態(未打字)，即時reflow一次，讓本地清單補上去。
  _trendingRefreshCallbacks.push(function () {
    if (document.activeElement === input && !activeSegment()) renderEmptyState();
  });

  function renderResults(val) {
    const {results, suggestion} = searchAssets(val, 8);
    currentResults = results;
    currentSuggestion = suggestion;
    activeIndex = -1;

    if (results.length === 0 && !suggestion) { closeDropdown(); return; }

    let html = '';
    if (results.length) {
      html += results.map(a => _renderAssetRow(a)).join('');
    } else if (suggestion) {
      html += `<div class="xfl-suggestion-row" style="padding:12px 14px;cursor:pointer;color:#94a3b8;font-size:0.82rem;border-bottom:1px solid #1e2d45">
        Did you mean <strong style="color:#00d4ff">${suggestion.name} (${suggestion.symbol})</strong>?
      </div>`;
    }
    dropdown.innerHTML = html;
    wireRowClicks(suggestion);
    dropdown.style.display = 'block';
  }

  function wireRowClicks(suggestionForEmptyMatch) {
    const rows = dropdown.querySelectorAll('.xfl-asset-row');
    rows.forEach((row, i) => {
      row.addEventListener('mouseenter', () => { activeIndex = i; highlight(); });
      row.addEventListener('click', () => selectAsset(currentResults[i]));
    });
    const sugRow = dropdown.querySelector('.xfl-suggestion-row');
    if (sugRow && suggestionForEmptyMatch) {
      sugRow.addEventListener('click', () => selectAsset(suggestionForEmptyMatch));
    }
  }

  input.addEventListener('input', function() {
    const val = activeSegment();
    if (!val) { renderEmptyState(); return; }
    renderResults(val);
  });

  input.addEventListener('focus', function() {
    if (!activeSegment()) renderEmptyState();
  });

  document.addEventListener('click', e => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      closeDropdown();
    }
  });

  // 用capture phase掛喺document層面（唔係掛落input本身），保證一定
  // 喺page自己嗰個keydown監聽（例如probability-scan.html嘅
  // "Enter -> runScan()"）之前執行 -- 咁樣揀咗個建議之後，input.value
  // 已經更新好，page自己個Enter handler先至跟住讀到啱嘅代號繼續行落
  // 去，唔會出現「揀低咗個建議但page用緊舊值」嘅次序問題。
  document.addEventListener('keydown', function(e) {
    if (e.target !== input) return;
    if (dropdown.style.display === 'none' || !currentResults.length) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = (activeIndex + 1) % currentResults.length;
      highlight();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = (activeIndex - 1 + currentResults.length) % currentResults.length;
      highlight();
    } else if (e.key === 'Enter') {
      if (activeIndex >= 0 && currentResults[activeIndex]) {
        selectAsset(currentResults[activeIndex]);
      } else if (currentSuggestion && currentResults.length === 0) {
        selectAsset(currentSuggestion);
      }
      // 冇揀任何item就乜都唔做，保留返page自己原本嘅Enter行為。
    } else if (e.key === 'Escape') {
      closeDropdown();
    } else if (e.key === 'Tab') {
      const pick = activeIndex >= 0 ? currentResults[activeIndex] : currentResults[0];
      if (pick) { applySelection(pick.api || pick.symbol); recordRecentAsset(pick); }
      closeDropdown();
    }
  }, true);

  // 輪流轉嘅placeholder範例，得喺個input冇內容嗰陣先轉，唔會滋擾緊
  // 打緊字嘅用戶。
  if (options.rotatePlaceholder !== false) {
    let phIndex = 0;
    const originalPlaceholder = input.placeholder;
    setInterval(() => {
      if (document.activeElement === input) return; // 用戶專心打緊字就唔轉
      if (activeSegment()) return;
      phIndex = (phIndex + 1) % PLACEHOLDER_ROTATION.length;
      input.placeholder = PLACEHOLDER_ROTATION[phIndex];
    }, 2600);
    // 保留返頁面原本個placeholder做第一個
    if (originalPlaceholder) PLACEHOLDER_ROTATION[0] = originalPlaceholder;
  }
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
