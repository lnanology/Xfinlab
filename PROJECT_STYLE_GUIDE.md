# XFINLAB Project Style Guide

## Overview
本專案採用單頁 HTML 的內嵌 CSS 方式設計，沒有獨立 CSS 檔案。所有頁面主要使用 `Inter` 作為介面字體，`DM Serif Display` 作為標題與品牌字體；配色以深色科技風為主，搭配品牌藍與金色強調色。

---

## Color Palette

- `--navy` #0D1B2A — 主背景深色
- `--navy2` #111F30 — 次背景 / 卡片底色
- `--navy3` #162438 — 深背景區塊
- `--navy4` #1A2B3C — 表單、側欄背景
- `--blue` #58A6FF — 主要品牌色 / 文字連結 / 強調色
- `--blue2` #1F6FEB — 按鈕背景 / 穩定重點色
- `--blue-dim` rgba(56,139,253,0.12) — 輔助背景、 hover、分隔效果
- `--gold` #C9A84C — 次要強調色
- `--gold2` #E8CC7A — 金色變化色
- `--green` #2ECC71 — 成功 / 上漲色
- `--red` #E74C3C — 錯誤 / 下降色
- `--text` #E6EDF3 — 主要文字
- `--text2` #8B949E — 次要文字
- `--text3` #4A5568 — 輸注文字
- `--border` rgba(56,139,253,0.12) — 弱邊框/分隔線
- `--border2` rgba(56,139,253,0.25) — 强邊框/ hover 邊框

---

## Typography

- 基礎字體：`'Inter', sans-serif`
- 標題 / 品牌字體：`'DM Serif Display', serif`
- 文字風格
  - 主要文字：`font-weight: 300` 或 `400`
  - 強調文字：`font-weight: 500` / `600`
  - 段落與次要文字：`font-size` 0.75rem–1rem
- 標題樣式
  - `h1` 常使用 `font-size: clamp(2.8rem, 7vw, 5.5rem)` 或固定 2rem
  - Section 標題為 `font-family: 'DM Serif Display'`，搭配簡潔 line-height
- 常見文字色彩
  - 正文：`var(--text)`
  - 次要說明：`var(--text2)`
  - 低階文字 / 附註：`var(--text3)`

---

## Buttons

### 主要按鈕
- `.btn-primary`, `.screen-btn`, `.analyze-btn`, `.ai-btn`, `.send-btn`
- 共同特徵
  - 背景：`var(--blue2)`
  - 文字：`#fff`
  - 邊框：`none` 或 `1px solid var(--blue2)`
  - 邊角：`border-radius: 4px` 或 `6px`
  - Hover：變色為 `var(--blue)` / `background: var(--blue)`

### 次要按鈕
- `.btn-secondary`, `.tool-btn`, `.qc-btn`, `.preset-btn`, `.cat-btn`, `.tf-btn`
- 共同特徵
  - 背景透明或 `var(--navy4)`
  - 邊框：`1px solid var(--border)` / `var(--border2)`
  - 文字色：`var(--text2)`
  - hover：`color: var(--blue)` / `border-color: var(--blue)` / `background: var(--blue-dim)`

### 導航按鈕
- `.nav-cta`
  - 背景：`var(--blue2)`
  - 文字：白色
  - border-radius: 4px
  - hover：`background: var(--blue)`

---

## Cards

### Card 樣式規則
- 背景：`var(--navy2)` 或 `var(--navy3)`
- 邊框：`1px solid var(--border)` 或 `var(--border2)`
- 圓角：`border-radius: 6px` / `4px`
- 內距：1rem 至 2.2rem
- hover 效果：淡色背景（`var(--blue-dim)` / `var(--gold-dim)`）或邊框色加深

### 具體元件
- `.feature`, `.price-card`, `.result-card`, `.news-card`, `.wcard`, `.msg-bubble`, `.ai-summary`
- `.feature-icon`、`.msg-avatar`、`.news-cat` 等為卡片內子元件
- 卡片標題使用深色或品牌藍色字體，如 `color: var(--blue)`
- 卡片內次要說明使用 `color: var(--text2)`

### 專案內例子
- 功能卡 `.feature`：欄位式卡片，`border-right` / `border-bottom` 用於分格
- 結果卡 `.result-card`：用於 AI 結果、比較與篩選內容
- 文章卡 `.news-card`：新聞內容卡片搭配 `.news-meta`, `.news-title`, `.news-desc`
- 聊天卡 `.msg-bubble`：機器人與使用者訊息泡泡區分左 / 右

---

## Navbar

### 通用結構
- `nav` 包含品牌 `.logo`、主要連結 `.nav-links` / `.nav-right`，以及 CTA `.nav-cta`
- 一般固定或 sticky
  - 首頁：`position: fixed; top: 0; left: 0; right: 0`
  - 其他頁面：`position: sticky; top: 0`
- 背景：`var(--navy2)`
- 底部邊框：`border-bottom: 1px solid var(--border)`
- Logo：`font-family: 'DM Serif Display'`, `color: var(--blue)`，`em` 使用 `color: var(--gold)`

### 連結樣式
- `.nav-link`：次要連結，色彩為 `var(--text2)`，hover 後變 `var(--blue)`
- `.nav-cta`：主 CTA，`background: var(--blue2)`、白字、圓角

### 變體
- `chart.html` 使用 `.nav-right` 組合
- `chat.html` 使用 `.nav-center` + `.mode-btn` 作頁內導航

---

## Footer

### 主要 Footer
- 僅在 `index.html` 首頁出現完整版 footer
- 結構
  - `.footer-logo`：品牌與金色強調
  - `.footer-links`：橫向連結清單
  - `.footer-note`：小字說明
- 設計元素
  - 背景：`var(--navy2)`
  - 分隔線：`border-top: 1px solid var(--border)`
  - 連結文字：`var(--text3)` / hover 變 `var(--blue)`

### 輔助 Footer / 底欄
- `chart.html` 使用 `.bottom-bar`：功能鏈接與風險提示
- 用法：隱喻資訊結尾、提供回首頁或 AI 分析連結

---

## Layout

### 容器與寬度
- `.container` 常見最大寬度
  - 1100px (首頁)
  - 1000px / 900px / 720px 依頁面內容而定
- 水平置中：`margin: 0 auto`
- 內邊距：`padding: 2rem` 或 `padding: 1.5rem`

### 網格與彈性
- 主內容區多使用 `display: grid; grid-template-columns: repeat(auto-fit, minmax(...))`
- 多數卡片區域採用 `display: flex; gap: ...` 或 `grid` 以實現響應式排版
- 側欄頁面（`chart.html`, `chat.html`）使用 `.main { display:flex; }`
- 頁面區塊通常分為 `.hero`, `.features-section`, `.sidebar`, `.chat-area` 等

### 卡片 / 區塊
- 卡片元素常搭配 `padding`, `border-radius`, `background: var(--navy2)`
- 分隔線多採 `border-top: 1px solid var(--border)` / `border: 1px solid var(--border)`
- 常見區塊高度設定為 `min-height: 100vh` 或 `height: 100%`

---

## Responsive Rules

- `@media(max-width: 768px)`
  - 首頁 `.nav-links` 隱藏
  - `.feature` 取消右側邊框
  - `.cookie-bar` 改成直列布局
  - `chat.html` 隱藏 `.sidebar`
  - `chat.html` `.welcome-grid` 變成一欄顯示

- `@media(max-width: 600px)`
  - `chart.html` 隱藏 `.sidebar`
  - `.tv-wrap` 高度限定為 `60vh`

- 自適應技術
  - `grid-template-columns: repeat(auto-fit, minmax(...))` 用於卡片、自適應欄位
  - `flex-wrap: wrap` 用於按鈕列、快速選項、badge、底部連結
  - `clamp()` 用於首頁 hero 標題字體大小

---

## Reusable Components

### Brand / badges
- `.logo` / `.footer-logo`：品牌文字 + 金色 `em`
- `.page-tag`, `.section-tag`, `.badge`, `.feature-badge`：小字標籤
- `.mkt-tag`, `.news-cat`, `.impact-pos/neg/neu`：狀態標籤

### Form controls
- `.input-field`, `.search-input`, `.search-field`, `.filter-select`, `textarea.input-box`
  - 深色背景、透明邊框、圓角
  - focus 時 `border-color: var(--blue)`
- `.cat-btn`, `.qc-btn`, `.preset-btn`, `.mkt-btn`, `.tf-btn`
  - 圓角藍色 hover / active 樣式

### Buttons / Callouts
- `.btn-primary` / `.nav-cta` / `.screen-btn` / `.analyze-btn` / `.ai-btn`
  - 主要 CTA 樣式
- `.btn-secondary` / `.tool-btn` / `.mode-btn`
  - 次要互動元件

### Cards & result panels
- `.result-card`, `.news-card`, `.price-card`, `.feature`, `.step`, `.wcard`
  - 標準深色卡片，常用 `padding`, `border-radius`, `border: 1px solid`，hover 亮度或邊框加強
- `.msg-bubble` / `.msg` / `.messages`
  - 聊天視圖特有訊息泡泡樣式

### Feedback / loading
- `.loading`, `.loading-text`, `.dot-ani` / `@keyframes blink`
  - 通用載入指示器
- `.disclaimer`、`.input-hint`、`.footer-note`
  - 低階提示與風險說明

---

## Notes

- 專案樣式以深色金融數據平台為主，並以藍色、金色與綠/紅色作為資訊分類與互動提示
- 所有頁面 CSS 都直接寫入各自 HTML 檔案，應用變數式風格一致性高
- 元件化風格並未抽離成全域樣式檔，但可依照上述變體整理為共同 UI library
