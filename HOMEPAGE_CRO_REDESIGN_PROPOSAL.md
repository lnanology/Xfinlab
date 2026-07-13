# XFINLAB 首頁 CRO / Neuro UX 重設計建議 — 記錄 + 評估

> 記錄日期：2026-07-11
> 來源：用戶提出嘅完整心理學/CRO首頁架構建議（原文見下方Part A摘要）
> 現狀：純文件記錄 + 評估，未動任何production code

---

## Part A — 原建議摘要

核心論點：XFINLAB如果目標唔係「資訊網站」，而係「Bloomberg + TradingView + Perplexity + AI Analyst」級別嘅全球投資研究平台，就要用行為心理學（Hick's Law、Authority Bias、數字勝於形容詞）+ CRO + Neuro UX去設計，唔可以用一般SaaS思維。

**11屏架構：**

1. **Hero**（5秒決定留下）— 唔介紹平台，直接答「我得到什麼」。淨2個CTA（免費分析／上傳K線）。右側放**真實AI分析畫面**（唔係mockup），因為「人腦相信睇到嘅，唔係讀到嘅」。
2. **Trust Numbers** — 全部用硬數字取代形容詞（例：8,000+股票、200萬+新聞、18+ AI模型、100+市場）。
3. **Problem → Relief** — 左紅右綠對比（❌每日睇100篇新聞 → ✅AI 30秒完成重點）。
4. **五大功能Card** — 每個功能一張大card：真實畫面＋文字＋CTA，唔用一排小icon。
5. **How it Works** — 只3步：輸入股票→AI分析→得到報告。
6. **AI Demo（免登入）** — 首頁直接可以輸入ticker試用，唔使先註冊。
7. **AI Engines權威感** — 列晒Research/Event/Risk/Decision/Chart/Macro/Sentiment Engine™，唔詳細解釋，靠數量builds Authority Bias。
8. **Pricing** — 擺中間唔擺最後（Free→Pro→Institution）。
9. **Testimonials** — 要具體（「以前分析要兩小時，而家十分鐘」），唔可以寫「好用」呢類空泛字眼。
10. **FAQ** — 解除最後疑慮（市場覆蓋/數據來源/AI可唔可靠/會唔會推薦股票/免費版/免登入試用）。
11. **Final CTA** — 具體行動（「免費分析第一隻股票」）唔係「開始使用」。

**色彩心理學建議：** 60%白＋30%深灰＋10%強調色（藍=信任/主CTA，橙=立即行動，綠=正向，紅=高風險）。

**額外3個模組：**
- **Live Market Pulse** — 首頁即時顯示全球市場情緒/波動率/熱門產業
- **Interactive AI Playground** — 免登入即可輸入ticker攞精簡AI分析
- **Personalized Homepage** — 根據用戶地區（美股/港股/台股/加密）自動調整首頁內容

---

## Part B — 現狀對照（`index.html`實際內容，2026-07-11）

| 建議項目 | 現狀 | Gap |
|---|---|---|
| Hero淨2個CTA | 已經係1個主要search+CTA（「分析→」），符合Hick's Law精神 | 細，唔算gap |
| Hero右側真實分析畫面 | 完全冇 — 現時Hero淨係文字+search bar，冇任何視覺化「產品證據」 | **大** |
| Live ticker bar | ✅已有（AAPL/NVDA/TSLA/MSFT/META/BTC/ETH跑馬燈，接真實`/api/market/{symbol}`） | 冇gap，已做到 |
| Trust Numbers（純數字） | 現時stats係「20+分析指標／即時市場數據／AI智能研究報告／多幣」— 混雜形容詞（「即時」「AI」「多幣」）同軟數字 | **中** — 要換成硬數字，但**數字必須真實** |
| Problem→Relief對比 | 完全冇 | **中**，純copy+layout，工作量細 |
| 大card式功能展示 | 現時係6個細icon card（icon+標題+一句description+link），冇真實screenshot | **中** — 需要每個功能嘅真實截圖 |
| How it Works 3步 | 完全冇 | 細，容易加 |
| 免登入AI Demo | 完全冇（所有分析功能都要login） | **大**，見Part C風險 #1 |
| AI Engines權威展示 | 完全冇呢類品牌化陳列 | **大**，見Part C風險 #2 |
| Pricing擺中間 | 現時Pricing係獨立頁面(`pricing.html`)，首頁完全冇提及價錢 | 中 |
| Testimonials | 完全冇 | **大**，見Part C風險 #3 |
| FAQ | 完全冇（首頁層面） | 細，容易加 |
| Final CTA具體化 | 現時已經係「立即開始免費分析」+「免費註冊」/「立即試用」兩個按鈕，同建議方向接近 | 細 |
| 色彩：60%白底 | 現時全站（包括今日改嘅所有頁面）用緊深藍/navy主題（`#080c14`底、`#00d4ff`強調色），**唔係**白底 | **極大** — 呢個唔係首頁改動，係全站品牌色改動 |
| Live Market Pulse | 完全冇 | 中大，需要新聚合邏輯 |
| Interactive AI Playground | 冇（同免登入Demo係同一件事） | 大，同#1風險一樣 |
| Personalized Homepage | 完全冇 | 大，需要地區偵測+內容切換 |

---

## Part C — 我嘅評估：邊啲值得做、邊啲要小心

### 🟢 低風險、可以直接做（純copy/layout，唔涉及新數據源或新cost）

- Trust Numbers 改用純數字（但數字要係真實可查證，唔可以作大）
- Problem → Relief 對比section
- How it Works 3步
- FAQ section
- Final CTA文案微調
- Pricing摘要搬去首頁中段（連結返`pricing.html`）

### 🟡 中風險，需要額外內容/工作先可以做

- Hero右側「真實AI分析畫面」+ 五大功能大card：需要每個功能嘅真實截圖或者live-render component。呢個我可以做，但要你揀：用靜態screenshot（快，但要定期update先唔會過時），定係用真正live component（例如直接embed一個縮小版嘅`probability-scan.html`結果喺Hero度）——後者好似建議講嘅「唔係mockup」精神，但技術上複雜好多（要即時call API，仲要諗埋rate limit）。
- Live Market Pulse：需要新增一個「全球市場情緒聚合」endpoint（例如攞幾隻指數ticker嘅trend/confluence，算個平均），工作量中等，冇新增cost（用現有Alpaca/yfinance）。

### 🔴 高風險，強烈建議你決定清楚先做

**1. 免登入AI Demo / Interactive AI Playground**
你而家嘅商業模式係「免費帳號每日10次分析」，即係要login先用到AI。免登入Demo即係任何人（包括競爭對手/scraper）都可以無限次consume你嘅AI API cost（Groq/Gemini vision call真係要俾錢），而家淨係得blanket 100/min per IP嘅rate limit，冇同「免登入用戶」專門加更嚴格嘅quota。如果要做，建議：
- 淨畀一個超簡化版分析（例如淨顯示Confluence方向，唔call vision model）
- 加專門嘅per-IP daily cap（例如3次/日），獨立於login用戶嘅quota
- 呢個係產品/成本決策，唔係純技術決定，要你話事點取捨。

**2. 「18+ AI Engines™」權威感展示**
今日我先啱啱做完Phase 5調查：`backend/quant/alpha/trading/evolution/agents/agi`嗰批code入面嘅「Engine」，好多其實係好簡單嘅weighted formula（例如`risk = volatility*0.4 + event_risk*0.3 + (100-news_score)*0.3`），未經回測校準。如果首頁大字標榜「Research Engine™／Risk Engine™／Decision Engine™」咁多個，建立Authority Bias，但用戶/監管機構一拆開個formula就發現冇料到，對金融平台嚟講呢個係**信譽同potentially合規風險**，唔係細事。建議：要不就先投放資源將幾個核心Engine做到真正有實力（回測/校準），要不就低調啲講，唔好用「™」呢類商標感字眼去誇大。

**3. Testimonials**
建議入面嘅例子（「以前分析股票要兩小時，而家十分鐘」）如果唔係真實用戶講過嘅說話，就係捏造testimonial——金融產品做呢樣風險好大（虛假宣傳）。如果XFINLAB而家仲未有真實用戶回饋，呢個section應該**延後**，或者暫時用「產品能力陳述」代替（例如具體講「AI喺30秒內處理XX日新聞」呢類可驗證嘅系統事實，唔係假扮user quote）。

**4. 60%白底色彩系統**
呢個唔係首頁單獨可以改嘅嘢——今日我改過嘅所有頁面（chart-analysis/screener/probability-scan/admin dashboard等）全部用緊深藍navy主題，同「白底70%」係完全相反嘅視覺方向。如果只改首頁做白底，其他頁面維持深藍，用戶由首頁click入去任何功能頁都會有「唔同網站」嘅違和感。呢個要決定係「淨首頁試驗」定係「全站rebrand」，後者係好大工程（起碼十幾個檔案嘅CSS variable要重新設計同測試）。

**5. Personalized Homepage（地區個人化）**
需要新增地區偵測（IP geolocation，可能要new第三方service或者用免費嘅Cloudflare/Vercel headers），加內容切換邏輯。呢個係錦上添花，喺用戶量仲細嘅階段，投資報酬可能唔高，建議排到最後。

---

## Part D — 建議分階段執行（如果你決定要做）

| 階段 | 內容 | 風險 | 前置條件 |
|---|---|---|---|
| Phase A | Trust Numbers（真數字）+ Problem→Relief + How it Works + FAQ + CTA文案 | 低 | 要你提供／確認真實數字（覆蓋幾多股票、幾多新聞來源等） |
| Phase B | Pricing摘要搬上首頁中段 | 低 | 無 |
| Phase C | 五大功能改做大card（先用靜態screenshot） | 中 | 要幫你影／生成每個功能嘅畫面截圖 |
| Phase D | Hero加真實分析畫面（live component） | 中高 | 決定用screenshot定live embed |
| Phase E | Live Market Pulse | 中 | 無新cost，但要設計「全球情緒」點計 |
| Phase F | 免登入AI Demo | 高 | **你要先決定quota策略同接受嘅AI cost上限** |
| Phase G | AI Engines權威展示 | 高（信譽風險） | **你要先決定：投資做實個formula，定係克制啲嘅文案** |
| Phase H | Testimonials | 高（如冇真實用戶） | **要有真實用戶回饋先做，或者暫時skip** |
| Phase I | 全站白底rebrand | 極高（範圍大） | **獨立決定，唔應該同首頁改動一齊做** |
| Phase J | Personalized Homepage | 中 | 排最後 |

---

## 我嘅總結建議

呢份CRO建議嘅心理學原則（Hick's Law、數字勝於形容詞、Problem→Relief、具體CTA）本身係啱嘅，亦都同而家嘅網站方向唔衝突，Phase A/B/C呢啲我建議可以盡快做。但入面有4樣嘢（免登入Demo嘅cost控制、Engine權威感嘅誠信風險、Testimonials嘅真實性、全站換色嘅範圍）唔係我可以自己拍板嘅純技術決定，需要你話事。

---

## Part E — 決策記錄：2026-07-13 首頁重排 + 新增2個Engine + 免費體驗改單次制

**背景：** 用戶要求（1）用心理學研究重新排列首頁區塊；（2）AI Engine由7個加到9個，排3x3；（3）評估免登入「免費體驗」CTA嘅位置是否合適；（4）之後再要求將免費體驗改為每個IP限用1次（唔可以重開網頁重用），用完要登入。

**1. 區塊重排（已執行，commit 9c4b05d）：**
Trust Numbers 同 Problem→Relief 兩個section由原本較後嘅位置搬到Hero之後、Live AI Result之前。理據：Serial Position Effect（首因效應）— 社會認同（Trust Numbers嘅硬數字）應該喺fold之上盡早出現先可以提升轉換；Problem→Relief嘅情感鉤子亦應該喺Hero之後、產品機制細節之前出現。新順序：Hero → Trust Numbers → Problem/Relief → Live AI Result → Today's AI Outlook → Real AI Showcase → Core AI Engines → Decision Intelligence → How it works → 免登入AI Demo → Pricing摘要 → FAQ → Final CTA。

**2. 免登入Demo位置（評估後：維持原位，唔搬）：**
研究顯示「互動demo → 免費試用 → 產品擴展」呢個漏斗，demo section最佳位置係喺pricing附近／之前，而家已經係咁擺（How it works之後、Pricing之前），符合最佳實踐，所以冇搬動。

**3. 新增2個Engine（已執行）：**
新增Anomaly Engine™（`anomaly.html`）同真正嘅Portfolio Engine™（`portfolio.html`），兩個都係包住現有、已經上線嘅後端邏輯（`api/anomaly.py`、`api/portfolio.py`），之前呢兩個功能淨係喺dashboard.html widget入面出現過，首頁冇獨立tile。同時修正咗一個舊有命名錯誤：首頁原本掛「Portfolio Engine™」個tile其實連去`company-compare.html`（同業比較功能，唔係組合配置），而家改名做「Compare Engine™」/"Compare Agent"。Tools grid由4欄改3欄，變成3x3共9個tile；`engines_title`同Trust Numbers嘅stat由「7」改做「9」，46種語言全部更新（4種用native數字字符嘅語言 fa/bn/ne/mr 有特殊處理）。

**4. 免費體驗改單次制（已執行）：**
`api/public_demo.py`由「每IP 30分鐘無限次試用時段＋4小時cooldown先可以開新時段」改為「每IP終身限用1次，冇自動重置」，用完之後一定要登入先可以再用。呢個係因應用戶明確要求（每個IP記錄住，唔可以靠重開網頁繞過），首頁相關文案（試用提示、錯誤訊息、結果CTA、FAQ）同步更新，46種語言全部翻譯。

**驗證：** 所有改動經過tag平衡檢查、`node --check`驗證inline script語法、46種語言key覆蓋率100%檢查（剩餘幾個regex false positive已確認同之前一樣係`alert(`/`trackEvent(`/`split(`呢類函數名尾段啱啱好係"t("造成，唔係真正缺key），先commit+push（commit 9c4b05d）。
