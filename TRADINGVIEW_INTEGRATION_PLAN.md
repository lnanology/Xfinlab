# TradingView Integration Plan

目的：指引如何將 TradingView 圖表嵌入現有站點，並說明如何與 `ai-analysis.html` 與 `chart-analysis.html` 互動，手機顯示考量，及未來 Premium 功能設計。

---

## 1) 如何嵌入 TradingView Widget
建議使用 TradingView 官方的 Embeddable Widgets（輕量、免費）做初期整合；未來若需完整功能可升級為 Charting Library（商業授權）。

基本步驟（範例）：

1. 在頁面 head 或 body 底部引入 TradingView widget 的 script（由 TradingView 提供）：

```html
<!-- 放在 head 或 body 結尾，不要直接把 API Key 放在前端 -->
<script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
```

2. 在 DOM 放置容器並初始化：

```html
<div id="tv_chart_container" style="height:500px; width:100%;"></div>
<script>
new TradingView.widget({
  "container_id": "tv_chart_container",
  "symbol": "NASDAQ:AAPL",
  "interval": "D",
  "timezone": "Asia/Taipei",
  "theme": "dark",
  "style": "1",
  "toolbar_bg": "#f1f3f6",
  "hide_side_toolbar": false,
  "withdateranges": true,
  "allow_symbol_change": true,
  "details": true,
  "studies": ["MACD@tv-basicstudies"]
});
</script>
```

要點：
- `symbol` 可動態帶入（見下一節）。
- 不要在前端儲存任何秘密；已註冊的 widget 無需 API key，但 Charting Library 與 Data Feed 會需要私有金鑰或資料供應。若接第三方 market-data（付費），務必透過後端代理。

---

## 2) 如何取得股票代號
為了讓 UI 與 chart 同步，建議採用以下多元來源，按優先順序採用：

- URL 參數（推薦）：例如 `ai-analysis.html?symbol=AAPL`，前端可用 `new URLSearchParams(location.search).get('symbol')` 取得，並將其傳給 TradingView widget。
- 使用者輸入（頁内輸入框）：現有頁面多已提供搜尋或輸入欄位，當按下分析或送出時，把值同步到 chart 的 `symbol`。
- 頁面上下文（例如 compare/page 選單）：若頁面已選定主標的，可直接從頁面資料層取出。
- 從元件或範例檔案拖放（`chart-analysis.html`）：若使用者上傳圖片並識別出 ticker，提供「以此 ticker 開 chart」的一鍵操作。

範例：從 URL 讀取並初始化 widget

```js
const urlSym = new URLSearchParams(location.search).get('symbol');
const symbol = urlSym || 'AAPL';
// 傳入 TradingView.widget 的 symbol
```

注意：對於多市場代號（如 `700.HK`、`TSE:7203`），請做簡單正規化或提供下拉選擇市場前綴。

---

## 3) 如何與 `ai-analysis.html` 互動
目的：在 `ai-analysis.html` 整合圖表，以便 AI 分析能基於使用者選擇的圖表/代號提供更精準的解釋。

交互模式建議：

- 初始同步：當頁面載入或使用者輸入代號並按執行分析時，同時呼叫 AI 分析（現有 `runAnalysis()`）與更新 TradingView widget 的 `symbol`。使用者看到圖表與 AI 結果一同更新。

- 從圖表導向分析：在 chart 上提供一個按鈕（或右鍵選單）「以此符號執行 AI 分析」，按下後會把目前 chart 的 `symbol` 傳回 `ai-analysis` 的分析函式。

- 快照/範圍同步：若 Chart 支援抓取當前時間區間（或輸出快照），可以把快照或時間範圍發到後端做更深度的 image-to-insight 或時間序列分析（後端 proxy 呼叫 LLM/Dify）。例如：
  - 用戶選取區間 → 前端把 `from`/`to` 與 `symbol` 傳至 `/api/dify/ai-analysis`，讓 AI 針對該區間作解讀。

- UI 線上狀態：在 `ai-analysis.html` 的「執行分析」按鈕旁增加 `以圖表區間分析` 選項，或當 chart 發生 `symbol_changed` 事件時，提示使用者是否以新符號執行分析。

範例程式碼片段：

```js
// 當使用者切換 symbol 時
function onChartSymbolChange(newSymbol){
  document.getElementById('symbolInput').value = newSymbol;
  // optional: 自動或提示執行 runAnalysis()
}

// 在初始化 widget 時，透過 callback 綁定事件（若 widget 支援）
// TradingView embeddable widget 允許 allow_symbol_change:true
```

---

## 4) 如何與 `chart-analysis.html` 互動
`chart-analysis.html` 以圖片上傳為主，整合 TradingView 可提供：「直接在圖上比對」與「從 chart 匯出圖片」的雙向流程。

互動建議：

1. 圖片→chart：若上傳圖片能解析出 `symbol`（例如使用 OCR 或從使用者輸入），提供一鍵「在 TradingView 開啟該 symbol」功能，透過 `window.open('chart-page?symbol=XXX')` 或嵌入同頁 widget 並切換 symbol。

2. Chart→圖片：在 TradingView 圖表上提供「匯出為圖片」或「複製快照」按鈕（Charting Library 提供更多控制，Embeddable widget 受限），使用者可把快照直接拖入 `chart-analysis` 的上傳區以做 AI 圖像分析。

3. 共享時間區間與指標：提供按鈕把 chart 的時間範圍（from/to）與已套用指標（如 MA, MACD）傳給 `chart-analysis` 的分析引擎或後端，以便 AI 同時考量該時間段的量價與型態。

4. UX 建議：在 `chart-analysis.html` 側邊放置一個小型 TradingView widget（或連結至完整圖表），使用者可以比對上傳截圖與即時圖表。

---

## 5) 手機版顯示方式
- 使用響應式容器：TradingView widget 設為 `width:100%` 並設定合適的 `height`（或以 CSS 透過 `aspect-ratio` 控制）。
- 輕量模式：手機版優先載入小尺寸或迷你 widget（顯示價格與迷你圖），並提供「展開至全螢幕」按鈕以載入完整畫面。這可透過條件載入或 lazy-load 實現。
- 互動優化：減少右側工具列與 side panels（hide_side_toolbar），改為簡潔工具列，避免觸控事件與桌面右鍵衝突。
- 手機快捷操作：加入「以此 symbol 執行 AI 分析」的固定底部按鈕，方便單手操作。

範例：條件載入輕量 widget

```js
if(window.innerWidth < 600){
  // 初始化 mini widget 或只載入 lightweight summary
} else {
  // 載入完整 TradingView.widget
}
```

---

## 6) 未來 Premium 功能設計（產品建議）
以下為可作為付費模組或 Premium 使用者的進階功能：

1. 實時自定義指標/策略套用
  - 允許用戶上傳自定義 Pine 腳本或自定義指標套用在圖上（需 Charting Library 與合約）。

2. 進階快照與註記共享
  - 使用者可以在圖表上標註支撐/阻力、型態並儲存分享鏈結；分享時可附帶 AI 生成的解說文字。

3. 回放（replay）與事件重播
  - 允許用戶回放價格走勢（回測式播放），並在播放過程中顯示 AI 解說與重點標記。

4. 即時價格警示與動作自動化
  - 當價格突破阻力或跌破支撐時，發送推播或電子郵件提醒；結合 webhook 或 trade execution（需風控）。

5. 定制化 AI Reports
  - 以 Scheduled Reports 形式（每日/每週）發送基於用戶關注清單與圖表的 AI 分析報告。

6. 團隊/多用戶協作
  - 儲存圖表狀態、註解與觀察清單，並讓團隊成員共同評論與審閱。

7. 高級資料來源（低延遲/專業級）
  - 為 Premium 用戶接入更精準的 market-data feed（需後端合約與授權）。

---

## 建議的實作步驟
1. 先在內部測試環境以 TradingView Embeddable Widget 做 PoC（用 URL 參數與頁面輸入同步 symbol）。
2. 實作 `symbol` 的同步 API（前端事件處理函式），並在 `ai-analysis.html` 加入 chart 互動按鈕（不改頁面原始檔，只做前端 enhancement）。
3. 若需匯出快照或深度整合（如從 chart 匯出圖片、註記），評估採用 Charting Library 與後端 Data Feed，並規劃商業授權與成本。
4. 設計 Premium 功能的計費模型與權限控制（feature flag + server-side gate）。

---

文件建立於：2026-06-06
