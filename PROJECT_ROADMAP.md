# XFINLAB 開發路線圖

> 對照完整架構見 [XFINLAB_ARCHITECTURE.md](./XFINLAB_ARCHITECTURE.md)

## 架構層級對應

| 層級 | 名稱 | 狀態 |
|------|------|------|
| L0 | Core Mission | ✅ 首頁定位已更新 |
| L1 | Core Data Engines™ | 📋 文件化，待後端 |
| L2 | AI Router™ | 📋 規劃中（Dify 整合） |
| L3 | 數據層 | 📋 Mock API 已有 |
| L4 | Analysis Engines™ | 🔶 部分頁面已有 |
| L5 | Security Center™ | ⬜ 未開始 |
| L6 | Compliance Center™ | 🔶 privacy.html 雛形 |
| L7 | My Research Center™ | ⬜ 未開始 |
| L8 | 產品模組 | 🔶 8 大模組已映射 |
| L9 | 首頁結構 | ✅ 已重構 |
| L10 | 全球語言 | 🔶 UI 已列出 16 語言 |
| L11 | 商業模式 | ✅ Pricing 已更新 |
| L12 | 估值核心 | 📋 文件化 |

## 已完成功能（頁面）

| 模組 | 檔案 |
|------|------|
| AI Market Research™ | `ai-analysis.html` |
| Company Compare™ | `company-compare.html` |
| Event Intelligence™ / News Intelligence™ | `news-denoise.html`, `news.html` |
| Risk Radar™ | `stress-lab.html` |
| Chart Research™ | `chart-analysis.html`, `chart.html` |
| 首頁 Layer 9 | `index.html` |

## 缺少功能

- Strategy Lab™（獨立策略引擎 UI）
- Decision Lab™ / Decision Journal™
- Market Research Center™ 即時數據
- Global Market Discovery™ 真實 API
- Top 10 Most Researched™ 後端
- My Research Center™ 會員系統
- AI Router™ 多模型路由
- TradingView 整合
- Enterprise API™

## 開發優先順序

### Phase 1（MVP）— 進行中
- ✅ 首頁 Layer 9 結構
- ✅ 八大核心模組映射
- ✅ Pricing（Free / Pro / Research Pro+）
- 統一 Navbar / Footer
- K 線分析完整流程
- Mock → 真實 API 過渡

### Phase 2（Beta）
- Strategy Lab™ + AJ Strategy™ 框架
- AI Router™（DeepSeek / Claude / GPT）
- Decision Lab™ · Decision Journal™
- My Research Center™ 登入雛形
- Market Research Center™ 即時數據

### Phase 3（Professional）
- Research Pro+ 付費功能
- Strategy Performance Dataset™
- Enterprise API™
- Alpha Engine™
- 完整 Compliance Center™

## 建議資料夾結構

```
css/
js/
assets/
components/
api/
docs/          ← XFINLAB_ARCHITECTURE.md
```
