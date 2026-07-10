# XFINLAB Commercial Production Architecture
### 目標架構整理 + 現狀對照 + 分階段結合路線圖

> 對照現有文件：[XFINLAB_ARCHITECTURE.md](./XFINLAB_ARCHITECTURE.md)（12層產品願景）、[PROJECT_ROADMAP.md](./PROJECT_ROADMAP.md)（Phase 1-3規劃）
> 本文件角色：將兩份文件之間嘅缺口，用一套**可落地嘅工程架構**填埋，並且訂出「加邊樣、幾時加、點加先唔會拖跨現有production」嘅具體步驟。

---

## 目錄

1. [Part A：架構整理（目標藍圖）](#part-a)
2. [Part B：現狀對照表（邊層已有／部分／缺）](#part-b)
3. [Part C：分階段結合路線圖（安全、不中斷）](#part-c)
4. [Part D：Chart Analysis／Yahoo Finance 具體落地位置](#part-d)
5. [Part E：明確唔做嘅嘢](#part-e)
6. [下一步（唯一即刻要做嘅task）](#next)

---

<a name="part-a"></a>
## Part A：架構整理（目標藍圖）

### A.1 九層主結構（由上至下）

```
1. Executive Layer          — 方向，不參與運算
2. Platform Layer           — 產品（前端/會員/訂閱/支付）
3. Data Intelligence Layer  — 數據蒐集、清洗、知識化
4. AI Intelligence Layer    — Memory / Reasoning / Verification / Learning / Evolution / Research
5. Simulation Layer         — 情境推演、預測、數位分身
6. Investment Layer         — 金融本業運算（市場/技術/基本面/風險/因子/型態）
7. Decision Layer           — 真正商業價值（決策、組合、事件情報、決策日誌）
8. Platform Intelligence    — 推薦/用戶洞察/告警/搜尋/報表/API/SDK
9. Infrastructure Layer     — FastAPI/PostgreSQL/Redis/pgvector/MinIO/Docker/Nginx/監控/備份

   ── Security & Operations Layer（獨立一層，架喺Infrastructure之上，貫穿全部）──
```

| Layer | 內容 |
|---|---|
| 1. Executive | Strategy · Roadmap · Product · Business · AI方向 |
| 2. Platform | Frontend · Dashboard · User · Subscription · Payment · API · Plugin · Search · Notification |
| 3. Data Intelligence | **蒐集**：API/RSS/Scrapy/BeautifulSoup/Playwright/aiohttp/PDF/CSV/XML/OCR → Queue → Normalize → Clean → Dedup → Store。**Engine**：Collection／Data／Semantic／Knowledge／Relation／Provenance |
| 4. AI Intelligence | Memory（Working/Long/Semantic/Episode合一）／Reasoning（Recursive/Tree/Planning/Reflection合一）／Verification（Self-Critic/Debate/Fact-Check/Confidence/Uncertainty/Consensus合一）／Learning／Evolution／Research |
| 5. Simulation | Simulation／Scenario／Forecast／Digital Twin／Counterfactual（全部併入Simulation Engine） |
| 6. Investment | Market／Technical／Fundamental／Risk／Factor／Pattern（全部金融運算） |
| 7. Decision | Decision Engine／Portfolio Engine／Event Intelligence™／Decision Database™／Decision Journal™ |
| 8. Platform Intelligence | Recommendation／User Intelligence／Alert／Search／Report／API／SDK |
| 9. Infrastructure | FastAPI／PostgreSQL／Redis／pgvector／MinIO／Docker／Nginx／Monitoring／Backup（**唔使一開始上Kubernetes**，等用戶量到百萬先） |

### A.2 十八個Core Engine（封頂數字，唔再增加）

```
Collection Engine   Data Engine        Semantic Engine    Knowledge Engine
Relation Engine     Provenance Engine  Memory Engine      Reasoning Engine
Verification Engine Learning Engine    Evolution Engine   Research Engine
Simulation Engine   Forecast Engine    Market Engine      Risk Engine
Decision Engine     Portfolio Engine
```
新需求一律用 **Registry** 掛載，唔准再開新Engine。

### A.3 六個Registry（防止Engine無限增生嘅關鍵）

| Registry | 解決咩問題 |
|---|---|
| Source Registry | 新增數據源（例如換走Yahoo Finance）唔使改code，註冊就得 |
| License Registry | 每個數據源嘅授權條款、商業/非商業用途集中管理 |
| Model Registry | 新增/替換AI模型（Groq/Gemini/Claude…）唔使改業務code |
| Prompt Registry | 集中管理同版本化所有prompt（而家散落喺每個api檔案入面） |
| Feature Registry | 已算好嘅特徵（RSI/MACD/Embedding…）集中註冊、可重用 |
| Plugin Registry | 新增功能模組（例如ESG Engine）用plugin形式掛載 |

（建議額外加：**Schema Registry**〔管理JSON/Table/API版本〕、**Policy Registry**〔唔同地區/法規/模型規則〕、**Service Registry**〔每個Engine/Agent/API嘅位置、版本、健康狀態〕）

### A.4 五個Manager（控制成本）

```
Workflow Orchestrator   Queue Manager   Cost Optimizer   Cache Manager   Resource Scheduler
```

### A.5 十個Agent（封頂數字）

```
Research Agent   News Agent      Macro Agent     Risk Agent      Portfolio Agent
Technical Agent  Report Agent    Translation Agent  Discovery Agent  Monitoring Agent
```

### A.6 AI Pipeline（數據 → 決策嘅完整流向）

```
Global Data → Collection → Cleaning → Dedup → NER → Knowledge Graph
→ Embedding → Memory → Reasoning → Verification → Research → Decision → Dashboard
```

### A.7 AI Cost Strategy（重點：80%唔使GPT）

```
Python → Rule Engine → Regex → Dictionary → Feature Store → Embedding
→ Small Model → DeepSeek → GPT → Claude
```
Feature Store全部Cache（Embedding/Summary/Risk/Pattern/Sentiment/NER/Ticker/Language），唔重複計算。

### A.8 商業版Database取態

```
PostgreSQL → Knowledge Graph → pgvector → MinIO
```
**第一版唔使Neo4j、唔使Elastic。**

### A.9 Security & Operations Layer（獨立一層，唔分散去每個Engine）

```
Identity & Access · Authentication · Authorization · API Security
Secret Management · Encryption · Audit Logging · Monitoring
Incident Response · Backup & Recovery · Rate Limiting · WAF · Compliance
```
八個必備能力：API Gateway（唔畀用戶直接掂到Backend）／JWT驗證＋Role＋Permission／RBAC（Guest→User→Pro→Enterprise→Admin→Super Admin）／Secret Manager（唔寫死API KEY）／Rate Limit／Audit Log（登入/付款/管理員操作/AI分析/API呼叫全記錄）／Monitoring（CPU/Memory/Token/API/Error/AI Cost/Crawler/Database）／每日Backup（Database→Object Storage）。

### A.10 擴充機制

- Event Bus：Engine之間唔直接互call，經Event Bus，新增Engine唔使改舊code
- Workflow Engine：負責Engine編排、Agent Flow、Queue、Retry、Timeout、Parallel Execution
- Cache Engine：Redis/Feature Cache/AI Response Cache/Query Cache/Embedding Cache，大幅降低Token成本

---

<a name="part-b"></a>
## Part B：現狀對照表

> 依據：實際盤點`backend/main.py`嘅import chain（真正跑緊production嘅係repo root嘅`api/`、`services/`、`ai/`、`auth/`、`engines/`，`backend/`入面嘅巨大目錄結構〔quant/alpha/trading/evolution/agents/agi/brain/stream/infrastructure〕大部分未接駁真實數據）。

| Layer | 對應現狀 | 狀態 |
|---|---|---|
| 1. Executive | `XFINLAB_ARCHITECTURE.md` + `PROJECT_ROADMAP.md`（12層願景+Phase規劃） | ✅ 已有，屬文件層面 |
| 2. Platform | 29個HTML頁面 + Vercel前端 + `api/quota.py`/`referral.py`/`onboarding.py` | ✅ 已有，Payment(Paddle)待審批 |
| 3. Data Intelligence | `services/market_data_service.py`(yfinance)、`services/news_service.py`、`growth/`爬蟲(reddit_bot/telegram_bot) | 🔶 有Collection，冇Semantic/Knowledge/Relation/Provenance Engine，冇統一Queue/Dedup pipeline |
| 4. AI Intelligence | `ai/ai_router.py`(模型路由)、`ai/report_generator.py`、`ai/research_agent.py` | 🔶 得返Reasoning嘅雛形，冇獨立Memory/Verification/Learning/Evolution Engine（`backend/agi/`有scaffold但用mock data） |
| 5. Simulation | `stress-lab.html` + `api/stress_lab.py` | 🔶 得返一個頁面級模擬，冇Scenario/Forecast/Digital Twin Engine |
| 6. Investment | `engines/`（risk_engine/scoring_engine/screener_engine）+ 新增嘅`services/technical_analysis_service.py`（RSI/MACD/支撐阻力/Fibonacci） | ✅ **今次Chart Analysis MVP已經係Investment Layer嘅Technical/Pattern Engine雛形** |
| 7. Decision | `database/schema.sql`有`decision_journal`表，但冇對應嘅Decision Engine業務邏輯接駁 | ⬜ Schema已定義，邏輯未實裝 |
| 8. Platform Intelligence | `api/watchlist.py`、`api/report.py`、`api/analytics.py` | 🔶 有雛形，冇統一Recommendation/Alert Engine |
| 9. Infrastructure | FastAPI + SQLite（+Litestream備份去R2）+ Railway + Vercel | 🔶 冇Postgres/Redis/pgvector/MinIO（暫時輕量化係合理，唔使而家上） |
| Security & Ops | JWT(`auth/`) + Upload Security(`security/upload_security.py`) | 🔶 有Auth/Upload驗證，**冇**Rate Limit、Audit Log、Secret Manager、統一Monitoring |
| Registry × 6 | 冇任何一個Registry存在 | ⬜ 完全未開始（呢個係最快、最平、風險最低嘅第一步） |
| Manager × 5 | 冇Workflow Orchestrator/Queue/Cost Optimizer/Cache Manager/Resource Scheduler | ⬜ 未開始 |
| Event Bus | `backend/infrastructure/event_bus.py` **已經寫咗但完全冇被引用** | ⬜ 現成嘅scaffold，得閒隨時可以接駁 |

**孤兒/未接駁模塊**（有code但未連接真實數據，`/api/pipeline/{ticker}`入面`MasterPipeline`用嘅係硬編碼mock數據）：
`backend/quant/`、`backend/alpha/`、`backend/trading/`、`backend/evolution/`、`backend/agents/`、`backend/agi/`、`backend/ai/agents/`、`backend/stream/`、`backend/infrastructure/event_bus.py`、`engines/risk_engine_v2.py`、`engines/chart_vision_engine.py`。

---

<a name="part-c"></a>
## Part C：分階段結合路線圖（安全、不中斷）

原則：**每一階段都唔郁現有production endpoint嘅行為，淨係喺旁邊加嘢，加完先慢慢切流量過去。**

### Phase 0（現狀，已完成）
Chart Analysis MVP：`services/technical_analysis_service.py` 已經係Investment Layer嘅Technical/Pattern Engine雛形，同AI Vision分工清楚。✅

### Phase 1 — 加Registry（唔改任何現有Engine，純新增）
1. `registry/source_registry.py`：登記現有Yahoo Finance數據源 + 未來替代數據源，欄位包括授權類型（commercial/non-commercial）
2. `registry/license_registry.py`：**直接對應你提出嘅Yahoo Finance法律風險** — 記錄每個數據源嘅授權條款，方便隨時審查/替換
3. `registry/model_registry.py`：將而家`ai_router.py`嘅`AI_PROVIDER`/`VISION_PROVIDER`環境變數邏輯升級做正式registry（現有邏輯已經有雛形，只係缺一個中央清單）
4. `registry/prompt_registry.py`：將散落喺`chart_analysis.py`、`ai_analysis.py`等檔案入面嘅prompt文字抽出嚟做版本化管理

風險：**零**（純新增檔案，冇改動任何現有router嘅行為）

### Phase 2 — Security & Operations 補強
1. Rate Limiting（FastAPI middleware，例如`slowapi`）
2. Audit Log（新table，記錄登入/付款/AI分析/管理員操作）
3. Secret Manager正式化（Railway已有環境變數機制，呢步係規範化管理，唔使新infra）
4. 統一Monitoring（Railway自帶部分metrics，可加健康檢查endpoint）

風險：**低**（Rate Limit/Audit Log係中間件疊加，唔改業務邏輯；上線前用staging環境confirm唔會誤傷正常流量）

### Phase 3 — Event Bus 啟用（現成code，零成本）
`backend/infrastructure/event_bus.py`已經寫咗，只係未被引用。可以由**低風險嘅非核心流程**開始試（例如：Chart Analysis分析完成後發一個event，畀`growth/anomaly_alerts.py`訂閱嚟做告警，而唔係而家咁靠cron硬call）。

風險：**低**（先喺一條非關鍵路徑試用，唔動主要API response流程）

### Phase 4 — Cache Engine（Redis）
現時`backend/core/cache.py`都已經有一個Cache雛形（但backend/未接駁）。加Redis嘅第一個用途應該係**AI Response Cache**（Chart Analysis同一張圖/同一個symbol短時間內重複請求，唔使再call Gemini/Groq），直接慳AI成本，同時降低cost overrun風險。

風險：**低**（cache miss時fallback番做直接call，唔影響正確性）

### Phase 5 — 孤兒模塊處理（`backend/quant/alpha/trading/evolution/agents/agi`）
呢批code寫得幾完整，但用緊hardcoded mock data，兩條路揀一：
- **(a) 接駁真實數據**：將`MasterPipeline.run()`嘅mock market_data/news_data，改用真正`market_data_service`/`news_service`，先至慢慢升級做Investment/Simulation Layer嘅正式一部分
- **(b) 封存**：如果短期用唔上，就喺呢份文件記錄低（唔刪code），等真係需要Portfolio/Alpha/Evolution呢類進階功能先再拎出嚟做

**建議：而家揀(b)**，因為your priority係Chart Analysis + 數據源合規，冇必要而家分散資源去救一個未連real data嘅demo pipeline。

### Phase 6 — Investment/Decision Layer深化（對應你之前份「AI Chart Intelligence Core」文件）
喺Phase 0基礎上逐步加：
- Swing Detection／Fibonacci Engine → 已經係`technical_analysis_service.py`嘅一部分 ✅
- Confluence Engine（將支撐/阻力/Fibonacci/型態訊號交叉驗證評分）→ 下一個合理嘅小步
- Scenario Engine → 併入Simulation Layer，長遠先做
- Chart DNA Engine／Explainable AI → 最後階段，屬於Verification Engine嘅延伸

---

<a name="part-d"></a>
## Part D：Chart Analysis／Yahoo Finance 具體落地位置

| 議題 | 架構位置 | 具體行動 |
|---|---|---|
| Yahoo Finance非commercial license風險 | Source Registry + License Registry | Phase 1建立Registry後，將yfinance標記為「短期使用/非commercial」，同時登記候選替代（下面Part 之外另開research task比較Polygon.io／Alpaca／Twelve Data／Finnhub／EOD Historical Data等commercial-friendly方案，我可以另開一個task幫你逐間比較價錢/授權） |
| Chart Analysis真實數據 | Investment Layer → Technical Engine / Pattern Engine | 已完成（`technical_analysis_service.py`） |
| AI視覺型態辨識 | AI Intelligence Layer → Reasoning Engine（narrow用途） | 已完成（`chart_analysis.py`嘅prompt已收窄做純視覺辨識） |
| 支撐/阻力/型態交叉驗證 | Investment Layer → 未來嘅Confluence邏輯 | 未開始，屬於Phase 6 |

---

<a name="part-e"></a>
## Part E：明確唔做嘅嘢（避免過度工程）

- ❌ 而家唔上Kubernetes（等用戶到百萬先）
- ❌ 而家唔加Neo4j／Elasticsearch（PostgreSQL+pgvector夠用）
- ❌ 唔再開新Engine（18個封頂，新需求一律用Registry/Plugin掛載）
- ❌ 唔即刻救backend/嘅mock pipeline（quant/alpha/trading/evolution/agents/agi 先封存）
- ❌ 唔一次過將9層晒做齊 —— 一次只做一個Phase，做完先驗證穩定先出下一個

---

<a name="next"></a>
## 下一步（唯一即刻要做嘅task）

Phase 1嘅四個Registry入面，**建議由`license_registry.py`＋`source_registry.py`開始**，因為佢直接解決你提出嘅Yahoo Finance法律風險，而且零風險（純新增檔案，唔動任何production行為）。

要唔要我而家就開始起呢兩個Registry？
