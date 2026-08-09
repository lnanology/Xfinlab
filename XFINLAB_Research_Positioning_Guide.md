# XFINLAB 定位重整指引 — Institutional Investment Research Platform

## 0. 先驗證：你貼嘅思路方向啱唔啱

搜尋咗美國SEC對「investment adviser」嘅定義（Investment Advisers Act §202(a)(11)），確認咗一個關鍵法律概念，同你貼嘅內容吻合，但仲要加多一層：

**"Publisher Exclusion"（刊物豁免）**：一個資訊/研究平台如果符合以下條件，法律上唔算「投資顧問」：
- 提供**非個人化**（impersonal）嘅評論同分析
- **唔係為個別訂閱者度身訂造**（not tailored to any specific subscriber's needs）
- 純粹「一般定期發行」（general and regular circulation），唔係為咗規避監管而設嘅推銷工具

即係話：**唔止改字**，仲要改「輸出結構」——如果Portfolio Allocation功能係攞緊某個特定用戶嘅持倉、風險承受度，然後度身出一份「你應該點配置」，就算個掣寫住"Research Allocation"，法律實質上仍然接近個人化投資建議。要做到「Research」而唔係「Advice」，個輸出必須係任何人查詢同一隻股都會見到嘅同一份分析，唔係為呢個特定用戶調校。

呢個補充咗你貼嗰份文件冇講到嘅一層——你嗰份主要係「改名」，但法規上「改結構（impersonal + non-tailored）」同「改名」同樣重要，甚至更重要。

---

## 1. 定位聲明

**由：** AI Investment Advisor / Signal Provider
**改做：** Institutional Investment Research Platform

首頁/meta/品牌描述統一用呢句（英文版本已經幾接近，中文版都要對齊）：
> XFINLAB is an institutional-grade AI research platform providing market data, scenario analysis and decision-support tools. All output is for informational and educational purposes only and does not constitute personalized investment advice.

---

## 2. 全站詞彙對照表（整合你貼嘅版本 + XFINLAB實際用緊嘅字眼）

| 現有字眼（XFINLAB實際用緊） | 改做 |
|---|---|
| AI Investment Advisor / AI投資顧問 | AI Research Copilot / Research Assistant |
| Signal / 訊號 | Research / Intelligence / Brief |
| Free Signals（已改market-brief.html） | Daily Market Intelligence / Daily Research Brief |
| BUY / SELL（已軟化） | Bullish / Bearish / Neutral（維持，方向正確） |
| Decision Score | Research Score（"Decision"隱含「幫你決定」，"Research"中性啲） |
| AI Watchlist | Research Watchlist / Tracked Assets |
| 異常偵測雷達 Anomaly Detection Radar | Anomaly Research Alert / Unusual Activity Monitor |
| Top Opportunity / 今日重點機會 | Today's Research Highlights / Top Ranked Research |
| 最活躍股票 | High Attention Assets（呢個字眼已經安全，Yahoo/Bloomberg都用） |
| Entry/Stop/TP/RR（已改支撐/阻力） | 維持現狀，已經係Reference Level/Scenario Range呢個方向 |
| VIP Picks / Premium Signals（如有） | Research Pro / Institutional Research |
| Ask AI / AI對話 | Research Copilot / Market Copilot |
| Recommended Allocation | Research Allocation / Simulation Allocation |
| Investment Advice（AI Report） | Research Report / Market Intelligence |
| TG Signals（Telegram widget） | XFINLAB Research / Daily Market Intelligence |
| 訂閱每日提醒 | 訂閱每日市場情報 (Subscribe to Daily Market Intelligence) |

---

## 3. 逐頁具體改法（對應你個repo實際檔案）

### market-brief.html（前free-signals.html）
- 頁面title/H1：「免費每日市場快訊」可保留（本身已經冇"信號"字眼），但內部：
  - `.signal-item` /「訊號」字眼可以淡化做「今日研究關注清單」
  - 榜單邏輯由「邊隻升邊隻跌排名」改做「多因子研究評分」展示（唔淨係方向，仲有Trend/Risk/Volatility等多點資訊——呼應SEC "general commentary"原則）
  - 教育元素（強烈建議）：每個項目底下加一句"Why"，例如："AI偵測到期權成交量異常上升，歷史上類似情況會帶嚟較高波動。僅供研究參考，不構成投資建議。"

### Telegram Channel（services/telegram_push_service.py + growth/anomaly_alerts.py）
- **修正返上一輪我嘅建議**：唔一定要完全改做「用戶主動查」先安全。Bloomberg「Five Things You Need to Know」、Morningstar每日筆記都係主動推送，行業常態。真正分界線係**內容格式**：
  - ❌ 危險格式：「🚀 BUY NVDA」（單一標的、直接方向指令）
  - ✅ 安全格式：多點聚合簡報（Macro Summary + Top Movers + Risk Events + Market Structure + Research Score + Disclaimer），呢個係「晨報」唔係「訊號」
- Channel名稱：「XFINLAB Signals」→「XFINLAB Daily Research」/「XFINLAB Market Intelligence」
- 每日內容範本見第4節

### Web Push（push_service.py + push-prompt.js）
- 掣文案：「訂閱每日提醒」→「訂閱每日市場情報」
- 內容同Telegram一致，改做聚合簡報格式，唔好淨係send單一方向

### AI Chat（chat.html）
- 輸入框placeholder：「Ask AI」→「Research Copilot」/「問AI市場分析」（保留現有中文語感，淡化"advisor"感）
- **輸出結構模板**（最高風險項目，務必跟）：
  ```
  Market Structure Analysis: [TICKER]
  ✔ Trend: [客觀描述]
  ✔ Valuation: [客觀數據]
  ✔ Risk: [客觀評分]
  ✔ Probability: [歷史統計，非保證]
  ✔ News: [事實摘要]
  ✔ Volatility: [數據]

  Research Conclusion: Bullish Bias / Neutral / Bearish Bias
  [免責聲明：僅供研究參考，最終決定權在於投資者本人]
  ```
  避免AI輸出入面出現「你應該買」「而家係入場時機」呢類第二人稱指令句式。

### Portfolio Allocation（portfolio.html）
- 「你應該投資」→「Suggested Research Allocation」/ 「Institutional Simulation」
- **結構上**：確保輸出係基於用戶自己輸入嘅假設參數（例如風險等級、時間長度）嘅**情境模擬結果**，而唔係「we recommend you personally do X」嘅口吻——用「模擬結果顯示於[假設]下嘅配置」框架，而非「你應該點做」

### Probability Scan（probability-scan.html）
- 「95%會升」→「Historical Pattern Similarity: 82%」+ 一句解釋呢個%係「過去類似形態嘅統計結果，唔係對未來嘅保證」

### Pricing（pricing.html）
- 已經冇"Signal"字眼（之前check過），tier名可以再對齊：Free/Basic/Pro/Pro+/Professional/Enterprise 已經幾中性，維持

---

## 4. Telegram每日簡報格式範本（取代而家嘅「派Signal」格式）

```
📊 XFINLAB Daily Market Intelligence — [日期]

Global Market Summary
[大市概覽，1-2句]

Today's Research Watchlist
[3-5隻，每隻: Ticker + Research Score + Bullish/Neutral/Bearish Bias]

Risk Radar
[異常/風險事件，客觀描述]

Institutional Insight
[1段教育性解釋，例如："AI偵測到XX成交量異常，歷史上類似情況..."]

⚠️ Research information only. Not investment advice. Final decisions remain with the investor.
```

---

## 5. 免責聲明 + Audit Log（監管機構越來越重視嘅部分）

- 每個AI輸出（Chat/Report/Portfolio）底部強制加返一句disclaimer（唔係淨係頁腳一次過寫，而係每次AI回覆都帶住）
- 保留AI分析紀錄（audit log）——你哋已經有Decision Journal（#221），呢個本身就係「可解釋性+紀錄保存」嘅正面示範，值得喺對外文案（例如Paddle申請/appeal時）明確提出嚟做賣點，唔好收埋

---

## 6. 實施優先順序

1. **首頁 + market-brief.html + Telegram/Push文案**（曝光最高，改動集中）
2. **AI Chat輸出模板**（風險最高，但只係prompt/模板層面改動，唔使動大結構）
3. **Portfolio Allocation輸出結構**（要確保「非個人化」原則，可能要調整少少邏輯，唔止文案）
4. **Decision Score→Research Score 等detail字眼**（全站掃描替換，低風險但工作量較大，可以之後慢慢做）

---

*本文件為策略建議整理，非法律意見。跨司法管轄區（美國/歐盟/香港/新加坡/日本）嘅具體要求有差異，建議正式申請/appeal前搵相關地區嘅金融合規律師核實。*
