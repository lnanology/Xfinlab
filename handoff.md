# XFINLAB 全站46語言i18n翻譯 — 進度交接

## 背景
用戶要求：語言切換功能支援全部45/46種語言，並且整個網站頁面及所有導航功能頁都要一致翻譯，同時保留IP自動偵測語言顯示功能。標準指令：「你測試過無問題就可繼續做落去，不用問，不要停」。用中文回覆。

## 已完成頁面（9頁，全部已push到GitHub main）
1. index.html — commit 435ebb3
2. ai-analysis.html — commit 6eb5ead
3. chart-analysis.html — commit c1b922c（順手修咗呢頁原本冇include js/i18n.js嘅bug）
4. stress-lab.html — commit 4445e99（同樣修咗冇i18n.js嘅bug）
5. news-denoise.html — commit 603b9c7（同樣修咗冇i18n.js嘅bug）
6. company-compare.html — commit bfdeabf（同樣修咗冇i18n.js嘅bug）
7. screener.html — commit ca51a77（同樣修咗冇i18n.js嘅bug）
8. probability-scan.html — commit e0394fb（同樣修咗冇i18n.js嘅bug；新key prefix `ps_*`，24個key，nav重用咗nav_chart/nav_screener/nav_dashboard/nav_privacy，新增page-specific嘅ps_nav_ai畀「AI 分析」cta）
9. chat.html — commit 06918d2（同樣修咗冇i18n.js嘅bug；新key prefix `chat_*`，34個key；順手刪咗呢頁原本嘅假語言切換器——一個得3種語言、onchange="changeLang(...)"淨係set document.documentElement.lang冇做任何實際翻譯嘅殘留`<select>`，已被真正46語言嘅I18N switcher取代；sendQuick(...)入面嘅AI query文字保持中文原文冇翻譯，跟screener.html doScreen()嘅慣例——淨係翻譯visible UI文字，唔翻譯送去backend嘅prompt內容）
10. terms.html — commit 3e254a1（呢頁本身冇任何i18n.js/nav/style同site一致，係純英文authored嘅法律文件stub；新key prefix `terms_*`，11個key。因為原文係英文唔係zh-HK，呢頁嘅fallback/source文字用返英文，其他45種語言含zh-HK都當普通target language黎翻譯）
11. privacy.html — commit 3e254a1（同terms.html一齊做，同樣係英文authored；新key prefix `privacy_*`，11個key；support@xfinlab.com email地址keep原文冇翻譯）
12. login.html — commit 278d545（同樣修咗冇i18n.js嘅bug；新key prefix `login_*`，21個key；英文authored（除咗「忘記密碼？」呢句原本已經係zh-HK）；"you@example.com" placeholder keep唔翻譯，因為淨係format example唔係natural language）
13. pricing.html — commit 7fc0a83（本身已有js/i18n.js同3個nav-level tag（nav_dashboard/nav_pricing/nav_login），呢次補晒hero、billing toggle、4個方案卡（Free/Pro/Professional/Enterprise）連features list、5條FAQ、CTA、footer；新key prefix `pricing_*`，69個key；英文authored；順手修咗個CSS bug——原本`.hero h1 span`會將h1入面所有span都變成accent色，加咗data-i18n span包住標題文字後會連累"AI"個span外嘅文字都變色，所以加咗個`.accent-word` class嚟取代通用`span`selector；貨幣數字（$0/$19/$49，同toggleBilling()嘅$15/$39）同內部plan key（'starter'/'pro'）keep原文冇翻譯；handleUpgrade()嘅alert改用`{plan}`placeholder嘅template）

services/i18n.py 依家每種語言個TRANSLATIONS dict已經有505個key/語言，全部46種語言key數量完全一致（每次merge後都verify過0 missing，同埋每次merge都同backup比對過冇整壞舊翻譯）。

## 中途插入咗嘅工作（導航/首頁改版，已完成並push — commit e3bc418）
用戶問咗成個網站導航結構，之後討論咗一輪UX/心理學設計（Hick's Law、progressive disclosure、Notion/Wealthfront/Robinhood三種模式），最後拍板：首頁工具區加一個「智能導覽」/「跳過睇晒全部」嘅fork，揀「智能導覽」會問一條問題（單一股票分析／幾隻之間揀／風險情境／自由傾偈），根據答案用`data-tool-group`篩選現有9張tool card（Wealthfront式contextual filter，冇duplicate DOM）。
- index.html：加咗`.guide-fork`等CSS、`#guideFork`/`#guideQuestion`/`#guideResult`嘅HTML、`startGuide()/skipGuide()/pickGuideOption()/showAllTools()`嘅JS，同一個`t(key, fallback)` i18n helper（呢頁之前冇）。新key prefix `guide_*`，9個key。
- home.html：確認全repo冇任何地方reference（grep過），已經同index.html內容重複，改成一個redirect去index.html（保留檔案，冇刪除，以防外部連結）。
- 驗證階段見過2個「missing key」false positive：`search`（其實係`trackEvent('search',...)`）同`請輸入股票代號`（其實係`alert('請輸入股票代號')`）——兩個都因為regex `t\('...'\)` 錯誤匹配咗以「t(」結尾嘅函數名（trackEvent(/alert 個"aler**t(**"），唔係真正用`t()` helper，已確認唔使加key。

## 進行緊
（無，導航改版已完成並push）

## 剩餘未做（1頁）
dashboard.html（最大一頁，1226行，暫時得1個data-i18n tag，需要由頭做大部分）。目前進度：`dash_*` key prefix已定義（82個key），outputs資料夾有`dash_translations_1.py`（12/46語言），仲差`dash_translations_2/3/4.py`（餘低34種語言）、`merge_dashboard.py`、merge+verify、編輯dashboard.html本身、驗證、commit+push。

## 標準工作流程（每頁重複）
1. Read全頁，audit可翻譯內容，check有冇缺js/i18n.js include（已發現5/7頁都有呢個bug，好可能剩低嘅頁都有同樣問題）
2. 定義page-specific key prefix（例如ps_*代表probability-scan），為每個key生成46種語言嘅真實翻譯（AI生成，非機器翻譯API，已喺commit message講明呢點）——通常分4個python檔案（12/12/11/11語言）用 T = {...} dict格式寫入 outputs 資料夾
3. 用regex+json merge script將新key merge入 services/i18n.py（保留現有key，用json.loads/dumps更新每個語言dict個line），跑完一定要verify「Missing langs: []」
4. Edit HTML檔案：加data-i18n/data-i18n-placeholder attribute，nav links盡量reuse已有嘅共用key（nav_home, nav_analysis, nav_compare, nav_news_denoise, nav_stress, nav_chart, nav_probability, nav_privacy, nav_screener等），select option嘅data-i18n淨係換textContent唔影響value attribute所以JS邏輯唔會壞。JS動態內容（alert/innerHTML樣板）加一個 `function t(key, fallback){ return (typeof I18N!=='undefined' && I18N.translations && I18N.translations[key]) || fallback; }` helper嚟讀取翻譯，保留繁體中文fallback
5. 驗證：(a) python regex檢查所有HTML tag open/close balance，(b) 檢查HTML入面所有data-i18n key喺全部46種語言嘅TRANSLATIONS dict都存在（0 missing），(c) 抽晒所有inline `<script>` block用 `node --check` 驗證JS語法正確
6. Commit：用heredoc寫commit message到 `/tmp/commit_msg_X.txt`（single-quoted delimiter 'COMMITMSG' 避免shell轉義中文/引號問題），fresh shallow clone去 `/tmp/xfinlab_push_X`，淨係copy修改咗嘅檔案入去，`git diff --stat` sanity check，`git -c user.email="abcoaj888@gmail.com" -c user.name="AJ" commit -F ...`，push到origin main，然後清理temp clone

## 重要技術細節
- `js/i18n.js` 嘅 `I18N.apply()` 只處理 `[data-i18n]`（換textContent）同 `[data-i18n-placeholder]`（換placeholder attribute），冇處理aria-label，所以呢啲位一直冇翻譯（可接受，非核心UI文字）
- data-i18n會清晒個element底下所有child node，所以有nested tag（例如`<strong>`包住部分文字）嘅case要拆成sibling span/strong分別data-i18n
- Bash同Read/Edit tool嘅路徑唔同：workspace folder `/Users/aj/Desktop/Xfinlab-main` ↔ bash路徑 `/sessions/<session-name>/mnt/Xfinlab-main`（session名每次對話都會唔同，用bash `pwd`/`ls`確認）；outputs scratch資料夾 ↔ `/sessions/<session-name>/mnt/outputs`
- 用戶email: abcoaj888@gmail.com（commit author用）

## Sources
Xfinlab repo: https://github.com/lnanology/Xfinlab
