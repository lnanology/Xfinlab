# XFINLAB 策略整合:B2B API優先 + World Engine開源地圖

> 呢份文件整合兩個決定:(1)主力賣API畀開發者/B端,唔再死磕C端訂閱payment審批;(2)「全球市場模擬層」點用開源code起。

---

## 一、點解揀B2B API做主線

| 對比項 | C端訂閱(而家死路) | B端API(建議主線) |
|---|---|---|
| 收費對象 | 散戶個人 | 開發者/其他fintech公司 |
| Paddle/Stripe分類 | 「投資訊號/財務建議」——Paddle明文禁,Stripe要人手審 | Data/API licensing——一般唔屬呢個restricted類別 |
| 已有基礎 | pricing.html 6-tier訂閱結構 | **Intelligence API v1已經起好**(task #508-517,有key+billing) |
| 冇BR/地址嘅影響 | 完全卡死,冇BR過唔到KYC | 一樣要BR先可以收錢,但B2B客戶審批門檻通常鬆過C端restricted business |
| 現金流特性 | 好多細額訂閱(高風控) | 少數大額合約(低風控,審批員睇落更似正常SaaS) |

**結論**:B2B API唔會令你唔使搞BR,但會令你Stripe申請嗰份文件睇落完全唔似「投資訊號平台」,審批機會大好多。

---

## 二、Intelligence API而家已經有咩(唔使重新起)

根據task #508-517:
- API v1基礎架構(key+billing)已建好
- reasoning_effort控制 + Claude escalation fallback已駁好
- early-access + plan-visibility endpoints已有
- intelligence-api.html landing page已起
- admin.html已有early-access request list管理面板

**即係話呢條線唔使由零開始,缺嗰樣係:真正嘅客戶(開發者/fintech團隊)嚟申請試用,同一份啱佢哋嘅sales/onboarding材料。**

---

## 三、World Engine(全球市場模擬層)點同B2B API連埋一齊

呢個唔係兩件獨立嘅嘢——World Engine起出嚟嘅數據(全球事件、產業資金流向、政策日曆),本身就係好啱賣畀B端嘅API產品:

| World Engine層 | 對應Intelligence API可以賣嘅data product |
|---|---|
| 政策/地理層(FRED/ECB) | Macro calendar API |
| 新聞/事件層(GDELT已駁好) | Structured global events API |
| 社交/情緒層(FinBERT) | Sentiment scoring API |
| 產業層(要新起) | Sector flow API(標明係proxy,唔係真order flow) |

即係話Phase 0(重新包裝現有數據,1-2星期,成本低)唔淨係做一個新UI頁面,可以同時包裝成一個新嘅API product tier,一魚兩食。

---

## 四、開源component地圖(已驗證)

### 可直接攞code(3個,全部MIT)

| 項目 | 用途 | 對應邊層 |
|---|---|---|
| agency-swarm(VRSEN) | 多agent orchestration,起AI辯論/多角度分析 | 可以做API嘅「多角度research」功能 |
| GeoPulseWebApp | 地緣政治dashboard,Python/Streamlit | UI/佈局參考,新聞/事件層 |
| Microsoft MarS | 金融市場模擬引擎(LMM) | 長遠訂單流/市場微觀結構模擬,Phase 2先諗 |

### 只可參考,唔可以攞code(2個,AGPL)

| 項目 | 問題 |
|---|---|
| koala73/worldmonitor(同lenage fork) | AGPL-3.0+商業用途要另購license,淨係睇UI/架構靈感 |
| Equibles | 純AGPL,網絡copyleft包袱,參考優先 |

### 查完唔存在/唔啱用(7個)

Fincept Terminal(避開,條款苛刻)、"AI market terminal"/"geopolitics aesthetic"(冇對應具體repo)、IntelDesk(對唔上)、EchoPolis(唔存在)、resilience.io(冇公開license)、Invest Sim(太泛)、QUSHi(proprietary app)。

---

## 五、同Global Simulation Roadmap嘅Phase對應

| Roadmap階段 | 內容 | 開源用邊個 | B2B API賣點 |
|---|---|---|---|
| Phase 0(1-2星期) | 重新包裝GDELT+FRED/ECB+FinBERT+shipping proxy做「全球市場地圖」頁面 | 唔需要外部code | 同步包裝做Macro/Events API tier |
| Phase 1(1-2個月) | 產業分類taxonomy、資金流向引擎、社交擴展 | UI參考GeoPulseWebApp;AI辯論用agency-swarm起 | Sector flow API(標明proxy) |
| Phase 2(長遠) | Whale tracking、跨資產contagion偵測、3D視覺化 | 訂單流模擬可參考Microsoft MarS;世界地圖UI靈感參考koala73/worldmonitor(唔攞code) | 進階data product,視乎B端客戶需求 |

---

## 六、建議執行順序

1. **即刻**:整理Intelligence API嘅sales/onboarding材料,對象係開發者/fintech團隊,唔係散戶——呢份先申請Stripe self-serve
2. **平行**:Phase 0重新包裝現有數據做「全球市場地圖」頁面+對應API tier(成本最低,用返晒已有真實數據)
3. **有咗第一筆B2B收入/儲夠BR費用後**:正式搞BR+虛擬地址,回頭補C端payment
4. **Phase 1/2**:視乎B2B客戶實際需求先決定投入產業分類、agency-swarm多角度分析呢類新開發,唔好未有客戶先假設要做
