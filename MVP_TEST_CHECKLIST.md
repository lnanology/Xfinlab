# MVP Test Checklist

## 1. 頁面測試
- [ ] `index.html` 可以打開並顯示核心功能區。
- [ ] `ai-analysis.html` 可以打開並顯示輸入框、評分卡與結果區。
- [ ] `company-compare.html` 可以打開並顯示公司輸入區、比較表與分析區。
- [ ] `news-denoise.html` 可以打開並顯示股票代號輸入區、情緒/新聞/盲點結果區。
- [ ] `stress-lab.html` 可以打開並顯示策略選擇、測試結果區與心理測驗區。

## 2. API 測試
- [ ] 啟動 `mock-server.py` 並確認 `http://localhost:8080` 可正常訪問網站。
- [ ] `POST /api/ai-analysis` 回傳格式為 JSON，包含 `status`, `schema_version`, `data.scores`。
- [ ] `POST /api/company-compare` 回傳格式為 JSON，包含 `status`, `data.companies` 與各項指標欄位。
- [ ] `POST /api/news-denoise` 回傳格式為 JSON，包含 `status`, `data.sentimentIndex`, `data.facts` 與 `data.blindspots`。
- [ ] `POST /api/stress-lab` 回傳格式為 JSON，包含 `status`, `data.scenarios` 與 `data.psych`。

## 3. 手機測試
- [ ] 於手機尺寸下，頁面元素沒有溢出螢幕。
- [ ] Navbar 收合功能可正常切換。
- [ ] 主要輸入欄位、按鈕與結果區可正常閱讀與操作。

## 4. 平板測試
- [ ] 於平板尺寸下，頁面佈局保持清晰、欄位與按鈕間距正常。
- [ ] 核心功能區、分析內容與表格不會過度擠壓。

## 5. 桌機測試
- [ ] 於桌機尺寸下，頁面呈現完整資訊，不會因為寬度不足而出現錯誤排列。
- [ ] 分析結果區、表格與圖表區能正常展開。

## 6. 錯誤處理測試
- [ ] 若輸入為空，系統會提示使用者填寫必要欄位。
- [ ] 若 API 呼叫失敗（例如關閉 `mock-server.py`），系統會顯示錯誤或提示。
- [ ] 模擬回傳異常時，UI 不會崩潰，並保留先前可用資料或提示用戶重試。

---

## 測試目標
完成整個網站的:
- 前端 →
- `/api/*` 模擬 endpoint →
- Mock Data →
- 畫面顯示

確保整個流程可端到端跑通。
