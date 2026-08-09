# XFINLAB「全球市場模擬層」產品功能規劃

> 定位：唔係做一個「預測地球未來」嘅黑箱,而係將現有分散嘅data source整理成一個「地球視角」嘅UI/後端層——用真實數據做地圖,唔係用AI幻想出嚟嘅劇本。呢點同呢個project一路以嚟嘅原則一致(之前拆咗MasterPipeline嗰堆假輸出模組、Stress Lab假數字,依家唔應該喺呢度重蹈覆轍)。

---

## 一、你提出嘅維度 + 我補充嘅維度,整理成7層

| 層 | 你提出嘅概念 | 我補充 |
|---|---|---|
| **地理層** | 唔同國家 | 唔同時區交易時段重疊(HK/EU/US session overlap) |
| **政策層** | 唔同政策 | 央行議息日曆、財政政策、選舉日曆、關稅/貿易政策 |
| **文化/觀點層** | 唔同文化、唔同觀點、唔同取向 | 唔同地區散戶 vs 機構嘅倉位分歧、恐懼貪婪指數按地區拆分 |
| **產業層** | 唔同行業分類、每個行業流動資訊 | 產業資金流向(sector rotation)、供應鏈上下游關聯、行業龍頭 vs 尾部分化 |
| **市場活動層** | 成交量分、大手異動動作 | 機構持倉變化(13F-style,美股先有)、期權未平倉量異動、跨資產相關性斷裂(contagion) |
| **新聞/媒體層** | 即時世界事件、不同新聞頻道、不同自媒體、不同討論區 | 央行官員發言基調追蹤(hawkish/dovish)、供應鏈/航運指標(呢個你哋已經有雛形) |
| **公司層** | 公司生意成長 | 財報季曆、盈利修正趨勢(analyst estimate revision) |

---

## 二、每層現況對照(XFINLAB已有 vs 要新起)

| 層 | 現有基礎 | 缺口 | 工作量估算 |
|---|---|---|---|
| 地理/政策 | FRED(美)、ECB(歐)宏觀數據已駁好 | 冇統一「政策日曆」UI、冇亞洲(HK/CN/TW/JP)央行數據源 | M |
| 新聞/事件 | GDELT全球事件庫已駁好(services/gdelt_news_service.py)、news_impact_engine.py已做量化enrichment | 冇按國家/行業做結構化分類顯示 | S(主要係前端呈現,後端數據已在) |
| 社交/自媒體 | Reddit + FinBERT情緒分析已有 | 冇Twitter/X、冇Threads/IG財經KOL、冇討論區(除Reddit外) | L(要逐個平台接,好多都要API費用或者ToS限制) |
| 產業分類 | 冇明確sector taxonomy | 完全要新起——sector分類 + 資金流向追蹤 | L |
| 大手異動 | anomaly_history_service.py(單一ticker30日掃描) | 冇跨市場「whale/block trade」追蹤層 | L(需要level 2/機構級數據,好多都要收費) |
| 供應鏈/航運 | 已有shipping/supply-chain proxy indicator | 只係proxy,冇覆蓋主要貿易路線圖 | M(擴展現有嘅) |
| 公司成長 | fundamentals/valuation service已有(revenue/earnings) | 冇「成長軌跡」專屬視圖、冇analyst estimate revision追蹤 | M |
| 市場regime | Bayesian regime detector已有 | 冇按地區/資產類別分拆顯示 | S |

**關鍵洞察**:你哋後端其實已經有唔少「地球模擬」嘅原材料(GDELT全球事件、FRED/ECB宏觀、FinBERT情緒、shipping proxy、regime detector),只係從未整理成一個統一嘅「世界視角」畀用戶睇。即係話,呢個功能一部分係**新開發**,一部分係**重新包裝現有數據**——後者成本低好多,應該優先做。

---

## 三、建議分3期做

### Phase 0(重新包裝,唔使新開發,1-2星期)
將GDELT + FRED/ECB + FinBERT + shipping proxy + regime detector,整合做一個新頁面「全球市場地圖」(working title):
- 世界地圖UI,按國家/地區顯示情緒分數(用現有FinBERT+GDELT算出嚟)
- 政策日曆(先用FRED/ECB已有數據,顯示未來7日重要宏觀事件)
- 供應鏈/航運指標卡片(現有proxy直接搬過嚟)

### Phase 1(新起數據層,1-2個月)
- 建立sector/產業分類taxonomy,將現有股票/ETF資料按行業歸類
- 起「產業資金流向」引擎(用成交量+價格變化按sector加總,近似估算,唔係真實order flow——要老實標明係proxy,唔好包裝成真實機構資金流)
- 擴展社交監察,由Reddit擴到多一兩個平台(建議先揀一個,例如StockTwits或者HK財經Threads/IG帳號,唔好一次過接晒五六個平台)

### Phase 2(進階/長遠,視乎有冇資源)
- 大手異動/whale tracking(呢個通常要付費機構級數據,例如Level 2 order book,成本同工作量都高,建議排到後面)
- 跨資產contagion/相關性斷裂偵測
- 互動式「地球」視覺化(3D地圖/動畫)——呢個純粹係UI糖衣,對分析價值有限,建議排最後,做完晒功能先諗要唔要靚

---

## 四、一個要企硬嘅原則

呢個功能一旦做出嚟,對外嘅包裝文案要非常小心:「模擬市場經濟活動預期動向」呢句嘢,聽落好似AI幫你預測世界經濟——呢個正正係之前Paddle拒收、你哋自己一路都喺度軟化嘅「investment advice/trading signals」嗰條紅線。呢個功能要包裝成「彙整全球公開數據嘅儀表板」(dashboard aggregating public data),而唔係「AI對世界經濟嘅預測」,先至唔會同你哋自己一路建立嘅合規定位打交。

---

## 五、下一步

呢份文件淨係規劃,未動任何code。如果想開始,建議由Phase 0起,因為成本最低、用返晒現有真實數據,唔使等新data source先可以見到成果。
