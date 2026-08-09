# XFINLAB 最終策略結構

> 整合成個對話嘅所有討論:定位、開源組件、收入優次、同要避開嘅風險。

---

## 一、定位

XFINLAB 唔再定位做「AI投資分析平台」,改做:

**Financial Data & Intelligence Infrastructure for developers**——賣加工後嘅真實數據(events/macro/sentiment/fundamentals),唔賣對股票方向嘅預測/機率。

一句核心判斷:同Investing.com/TradingView鬥「資料多」冇意思,應該鬥「資料加工成點樣可以俾第三方直接用」。

---

## 二、已經有嘅基礎(唔使重新起)

| 資產 | 對應task | 用途 |
|---|---|---|
| Intelligence API v1(key+billing) | #508-517 | 主收入線底座 |
| GDELT全球事件、FRED/ECB宏觀、FinBERT情緒 | #557-559, #266-269 | Events/Sentiment/Macro數據源 |
| AI provenance marking utility | #682-686 | 標記AI生成內容,擴展做OBSERVED/DERIVED標籤 |
| Broker affiliate CTA | #599 | 零成本收入線,已built |
| Video Engine(多語言自動生成) | #627-651 | 可以同步上YouTube做廣告分成 |
| SEO ticker/comparison頁(80+頁) | #454-502 | 可掛AdSense |
| 46語言i18n | 全站 | 全球市場覆蓋唔使再做 |

---

## 三、要避開嘅嘢(明確紅線)

**唔好賣「對個別股票/行業嘅方向性機率或預期回報」數據產品**,例如"NVDA 5D UP probability 68%"、"expected_return +4.7%"呢類輸出。改名做「forecast dataset」唔會令風險消失:

- Paddle已經因為呢個category拒收你(AUP第10類明文禁trading signals/investment advice)
- Stripe restricted business review對呢類都要人手審
- 更根本:HK《證券及期貨條例》第4類受規管活動(就證券提供意見)定義好闊,系統性咁產出方向性機率再對外銷售,有機會觸及SFC牌照要求——呢個要真正HK法律意見先可以判斷,唔可以自己諗掂就做

呢條線喺文件入面唔存在,唔屬於P0/P1/P2任何階段。

---

## 四、收入結構(按優次)

| 優次 | 收入線 | 使唔使BR/Stripe | 狀態 |
|---|---|---|---|
| 1 | Google AdSense(SEO頁+free tools) | 唔使 | 即刻可做 |
| 2 | YouTube monetization(Video Engine輸出) | 唔使 | 即刻可做,近零邊際成本 |
| 3 | Broker affiliate | 唔使(券商直接過畀個人) | 已built,查緊轉化 |
| 4 | Ko-fi/Buy Me a Coffee(種子資金) | 唔使 | 即刻可做,金額細 |
| 5 | Intelligence API(Data+Intelligence層,唔含forecast) | 要 | 已有底,等BR |
| 6 | MCP Server(新加) | 要(同API共用) | 見下 |
| 7 | Telegram channel sponsorship | 唔使 | 要夠訂閱數先 |

**先做1-4,唔使等BR。5-7先要正式收款渠道。**

---

## 五、新加:MCP Server

呢兩輪討論入面,唯一值得即刻加嘅新方向:

包一層MCP wrapper喺Intelligence API之上,俾Claude/GPT/Cursor呢類AI agent直接call你哋嘅工具攞真實數據(events/macro/sentiment/fundamentals)。特點:
- 成本低,喺已有API基礎上加一層
- 完全冇「賣訊號」風險,因為輸出係俾AI讀嘅結構化真實數據,唔係方向性判斷
- 踩中而家AI agent生態(MCP)嘅風口,同「B2B API」定位一致

---

## 六、World Engine開源組件(已驗證)

| 項目 | License | 用途 |
|---|---|---|
| agency-swarm(VRSEN) | MIT,可直接攞code | 多agent orchestration,起AI辯論功能 |
| GeoPulseWebApp | MIT,可直接攞code | UI/佈局參考,地緣政治dashboard |
| Microsoft MarS | MIT,可直接攞code | 長遠訂單流模擬(Phase 2先諗) |
| koala73/worldmonitor(同lenage fork) | AGPL-3.0+商業要另購license | 只可參考UI/架構,唔攞code |
| Equibles | AGPL-3.0 | 只可參考,網絡copyleft包袱 |

7個新提出嘅名(Fincept Terminal/IntelDesk/EchoPolis/resilience.io/Invest Sim/QUSHi/"AI market terminal")全部查完唔啱用或唔存在,已排除。

---

## 七、執行階段

**P0(即刻,唔使BR)**
- AdSense掛落SEO頁+free tools
- Video Engine輸出同步上YouTube
- 查broker affiliate實際轉化,修正擺位
- Ko-fi/Buy Me a Coffee開通做種子資金

**P1(BR搞掂之後)**
- 正式接通Stripe/Airwallex(用返虛擬地址,BR大機會可豁免)
- Intelligence API開放Data+Intelligence層(唔含forecast/probability)
- 加MCP Server wrapper

**P2(有第一批B2B客戶之後先諗)**
- World Engine Phase 0:重新包裝GDELT+FRED/ECB+FinBERT做「全球市場地圖」,同步做新API tier
- agency-swarm起多角度research功能

**P3(長遠,視乎實際需求,唔預設一定做)**
- Sector/Company Intelligence擴展
- Enterprise custom feed、white-label(要sales能力,一人團隊暫緩)
- 「賣預期數據」呢條線——只有攞到正式HK法律意見話可以做,先重新評估

---

## 八、一句總結

依家最缺嘅唔係更多Agent或更大架構,係第一筆真金白銀。P0四項全部零成本、零BR依賴,應該即刻做;P1先解決payment;P2/P3等有實際客戶需求先擴展,唔好未有人用先起100個agent。
