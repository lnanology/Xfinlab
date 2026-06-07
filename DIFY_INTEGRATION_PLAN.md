# Dify Integration Plan

目標：為 `ai-analysis.html`、`company-compare.html`、`news-denoise.html`、`stress-lab.html` 提供統一且安全的 Dify（或類似 LLM 服務）整合規格，包含前端需送出的資料、預期回傳格式、API endpoint 預留位置、前端接收方式，以及從 Mock 切換到正式 API 的步驟。

---

## 共通建議（所有頁面）
- 絕對不要在前端直接使用 Dify API Key。所有呼叫建議經由後端代理（proxy）或 serverless function，例如：`POST /api/dify/{page}`，由後端負責帶入 `Authorization: Bearer <API_KEY>` 並處理流量控制、快取與錯誤封裝。
- 回傳格式應為 JSON，含 `status`, `data`, `meta`。建議 schema 版本控制，例如 `schema_version: 1`。
- 前端實作：在各頁面的「執行分析」函式內呼叫代理 endpoint；UI 顯示 loading、錯誤及結果；失敗時回退到 Mock（若 feature flag 開啟）。

---

## 1) ai-analysis.html
- 檔案： [ai-analysis.html](ai-analysis.html)

1) 每個頁面需要傳送什麼資料
- `symbol`（字串）：使用者輸入的第一個代號（例如 `AAPL`）。
- `symbols`（字串陣列，可選）：若支援批量分析。
- `assetType`（字串）：`stock`/`etf`/`crypto`/`auto`。
- `context`（物件，可選）：前端已計算的 mock scores 或近期價格摘要，例如 `mock_scores:{fund:78,tech:65,news:82,risk:28}`，便於 LLM 進行比對與補述。
- `uiFlags`（可選）：如 `explain_level: 'short'|'detailed'`。
- `request_id`（可選）：用於追蹤與除錯。

2) Dify 回傳什麼資料（建議 schema）
- `status`: `ok` / `error`
- `schema_version`: 1
- `data`:
  - `scores`: { `fund`: int, `tech`: int, `news`: int, `risk`: int, `overall`: int }
  - `probabilities`: { `bull`: int, `flat`: int, `bear`: int }
  - `narrative`: string （簡短+可選的詳細段落）
  - `risks`: [ { `title`, `desc`, `confidence` } ]
  - `indicators`: [ { `name`, `value`, `note` } ]
  - `sources`: [ { `source`, `url` } ]
- `meta`: { `request_id`, `processing_time_ms` }

3) API Endpoint 預留位置（後端代理）
- Proxy path: `POST /api/dify/ai-analysis`
- External Dify (if calling from server): `https://api.dify.ai/v1/chat-messages`
- 前端呼叫位置（建議）：`runAnalysis()`（目前在 [ai-analysis.html](ai-analysis.html) 中）在產生 mock 後或開始 mock 前替換成真實呼叫。

4) 前端如何接收結果
- UI 流程：點擊「執行分析」→ 切換 loading → `fetch('/api/dify/ai-analysis', {method:'POST', body:JSON.stringify(payload)})` → 解析回傳 JSON → 更新 `fundScore`, `techScore`, `newsScore`, `riskScore` DOM；更新機率進度條 `bullFill/flatFill/bearFill`；更新 `aiConclusion` 與可選的 `reusable-score-card`（動態填 data-* 並重新渲染）。
- 錯誤處理：若 response.status !== 200 或 `status==='error'`，顯示錯誤訊息並保留 mock 資料。
- 範例片段（前端）:

```js
const payload = { symbol: primary, assetType, context: { mock_scores: {...} } };
const res = await fetch('/api/dify/ai-analysis', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
const json = await res.json();
if(json.status==='ok'){
  const d = json.data;
  document.getElementById('fundScore').textContent = d.scores.fund + '/100';
  // ... 更新其他 DOM
  // 若使用 reusable-score-card:
  const el = document.querySelector('.reusable-score-card');
  if(el){ el.dataset.fund = d.scores.fund; el.dataset.tech = d.scores.tech; el.dataset.news = d.scores.news; el.dataset.risk = d.scores.risk; el.dataset.overall = d.scores.overall; /* 重新初始化或觸發 render */ }
}
```

5) 未來如何切換正式 API
- 使用後端 proxy；在前端使用 feature flag 例如 `window.DIFY_USE_MOCK = false`。
- 後端環境變數 `DIFY_API_KEY` 並限制 IP、加上 rate-limiter、快取（短期 30s）及監控。前端只切換 proxy URL 或關閉 mock branch。

---

## 2) company-compare.html
- 檔案： [company-compare.html](company-compare.html)

1) 傳送資料
- `symbols`: 字串陣列（2~5 個公司代號）。
- `metrics`: 可選陣列，像 `['market_cap','revenue_growth','gross_margin','roe','fcf','debt_ratio']`。
- `request_id`, `user`（可選）

2) Dify 回傳
- `status`, `schema_version`
- `data`:
  - `table`: { `headers`: ["指標", ...], `rows`: [ [metric, value1, value2, ...], ... ] }
  - `scores`: [ { `symbol`, `scores`: {fund, growth, health, overall} } ]
  - `highlights`: [ {`title`,`desc`} ]
  - `recommendation`: { `top_pick`, `rationale` }
  - `explainable`: optional structured rationales per company
- `meta`。

3) Endpoint 預留
- Proxy path: `POST /api/dify/company-compare`
- 前端呼叫位置（建議）：`doCompare()`（目前在 [company-compare.html](company-compare.html)）在生成 mock table 與分析時改為呼叫真實 API。

4) 前端接收
- 收到 `table` 後：用它替換 `#tableBody` 與表頭；收到 `scores` 陣列則用可重用元件或頁內的 score-grid 顯示（動態產生 `.reusable-score-card` 或填入現有格子）。
- 若回傳含 raw markdown 或長文本（`narrative`），使用 `formatAnalysis()` 或 markdown-to-html 處理後插入 `analysisContent`。

5) 上線切換
- Proxy + 增量 rollout：先在內部測試環境開啟真實 API，觀察回傳穩定度與成本，再在前端放開 feature flag 給使用者。

---

## 3) news-denoise.html
- 檔案： [news-denoise.html](news-denoise.html)

> 此頁已有 `simulateDifyApi()` 暫存，為整合提供天然切入點。

1) 傳送資料
- `symbol`（字串）
- `timeRange`（選填）：如 `last_7d`,`last_30d`。
- `sources`（選填）：新聞來源白名單或黑名單。
- `max_items`（int）
- `context`：前端已經擷取的新聞片段（若在前端抓取）或僅提供 fetch key 由後端拉取原始新聞。

2) Dify 回傳
- `status`, `schema_version`
- `data`:
  - `sentiment_summary`: { `overall_score`, `bull_pct`, `neutral_pct`, `bear_pct` }
  - `highlights`: top facts / denoised statements
  - `denoised_news`: [ { `headline`, `snippet`, `sentiment`, `source`, `url` } ]
  - `blindspots`: [ { `title`, `desc` } ]
  - `explanations`: optional textual reasoning

3) Endpoint 預留
- Proxy path: `POST /api/dify/news-denoise`
- 前端現有函式 `simulateDifyApi()` 可直接替換為 fetch 呼叫至代理，或在該函式加條件判斷（mock vs real）。

4) 前端如何接收
- 收到 `sentiment_summary` → 更新 `#totalSentiment`, `#bullishGauge`, `#neutralGauge`, `#bearishGauge` 的 width 與分數 DOM；
- `denoised_news` → 轉為 `.news-item` 清單插入 `#newsList`；
- `highlights` / `blindspots` → 填入對應區塊 `#denoisedContent`、`#blindspotContent`。
- 若有 `reusable-score-card`，可把 `news` 分數塞入該元件的 `data-news` 屬性。

5) 上線切換
- 在 `simulateDifyApi()` 中判斷 `window.DIFY_USE_MOCK` 或檢查 `process.env`（若使用 bundler）來決定是否呼叫 proxy。

---

## 4) stress-lab.html
- 檔案： [stress-lab.html](stress-lab.html)

1) 傳送資料
- `strategyKey`（字串）
- `amount`（數字）
- `scenarios`（可選）：要套用的情境清單
- `request_id`

2) Dify 回傳
- `status`, `schema_version`
- `data`:
  - `scenario_results`: [ { `scenario`, `max_drawdown_pct`, `remaining_value`, `recovery_years`, `notes` } ]
  - `risk_profile`: { `score`: int, `description` }
  - `advice`: [ { `action`, `rationale` } ]
  - `explainability`: optional step-by-step reasoning

3) Endpoint 預留
- Proxy path: `POST /api/dify/stress-lab`
- 前端呼叫位置（建議）：`runStressTest()`（目前在 [stress-lab.html](stress-lab.html)）。在目前用 mock profile 計算之後可替換或補上 LLM 輔助解釋與建議結果。

4) 前端接收
- 收到 `scenario_results` → 直接填入 `dd2008/sub2008/rec2008` 等 DOM（或透過一個資料驅動函式批量更新）。
- 顯示 `advice` 至 AI 教育區或另增彈窗以說明對策略的建議。

5) 上線切換
- 建議先以 read-only 模式（僅回傳解釋文字，不立即替換量化數字），由 QA 與量化團隊核對結果正確性，再逐步開啟實際替換數值。

---

## API 版本化、錯誤與安全性建議
- 使用 `schema_version` 與 `timestamp` 在 response meta 中標示回傳版本。
- 常見錯誤碼：
  - `429`（rate limit）→ 前端提示稍後重試與 exponential backoff。
  - `502/504` → 顯示暫時性服務錯誤。
  - `400` → 請求參數錯誤，顯示開發者可見日誌。
- 後端代理應實作：API Key 保護、速率限制、短期快取（30s - 2min）、日誌與監控、輸入長度限制（避免過長 prompt）。

---

## 範例：後端 proxy 路由清單（建議）
- `POST /api/dify/ai-analysis`
- `POST /api/dify/company-compare`
- `POST /api/dify/news-denoise`
- `POST /api/dify/stress-lab`

每個 endpoint 回傳統一包裝 `{ status: 'ok'|'error', schema_version:1, data: {...}, meta:{request_id, time_ms}}`。

---

## 小結 / 建議實作步驟
1. 建立後端 proxy endpoints 並測試能夠呼叫 Dify（在後端帶入 API Key）。
2. 在前端將現有 `simulateDifyApi()` 與 `runAnalysis()`、`doCompare()`、`runStressTest()` 加上呼叫 proxy 的分支（由 feature flag 控制）。
3. 定義並鎖定回傳 schema（`schema_version`），前端依 schema 做解析，並在 schema 變更時顯示兼容層。
4. 小範圍上線（Internal）→ 收集回傳品質與成本 → 再做 Public rollout。

如需，我可以：
- 幫你產生可直接部署的後端 proxy 範例（Node.js + Express / serverless handler），或
- 在前端現有的函式中加入非破壞性的 fetch 範例（僅示範，不會修改原始檔案）。

---

文件建立於：2026-06-06

