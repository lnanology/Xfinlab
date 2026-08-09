# XFINLAB 法律頁面缺口分析 + 建議

## 0. 搜尋結果：一個時效性極高嘅發現

**EU AI Act第50條「透明度義務」喺2026年8月2日正式生效**——即係今日（8月6日）計，4日前先啱啱生效。呢個唔止係「best practice」，而係如果XFINLAB有歐盟用戶，現在就有法律約束力嘅要求：
- AI生成內容（你嘅AI Report、Chat回覆、Research Score解讀）需要清晰標示係AI生成
- 例外情況：如果AI生成內容經過**人手審核**、並且有自然人/法人負編輯責任，可以豁免。但XFINLAB嘅Chat/AI Report係即時生成、無人手審核，**唔符合呢個豁免**
- 違規罰則：最高€1500萬或全球年營業額3%（machine-readable標記要求2026年12月2日死線）

呢個令你講嘅「AI Disclaimer」頁面唔止係「建立專業形象」，而係實際合規要求，優先級要提高。

同時確認咗GDPR privacy policy嘅檢查清單（controller身份、DPO聯絡、處理依據、資料類別、retention、國際傳輸、8項用戶權利、投訴權、自動化決策披露）——你已有嘅privacy.html大部分已覆蓋，缺口見下面。

---

## 1. 現狀 vs 建議架構：逐頁缺口分析

### terms.html（現有9章）
現有：Acceptance / Not Financial Advice / Subscription / Limitation of Liability / Contact / Governing Law / Eligibility / Payment Processing / Additional Terms

缺：
- **Service Description**（具體列出AI Analysis/Screener/Portfolio Research/Chart Analysis/Research Reports/News Intelligence呢啲實際功能名單——用嚟同「我哋做咩」對齊，避免同你依家改緊嘅「Research」定位唔一致）
- **AI Limitation**（獨立條款，唔淨係"Not Financial Advice"帶過）
- **Market Data Disclaimer**（資料可能delayed/incomplete/unavailable）
- **Intellectual Property**（AI Report、介面、logo版權聲明）
- **Acceptable Use**（禁止scraping/bot/reverse engineering/API abuse——你哋已經做咗anti-scrape技術措施#294-297，但ToS冇明文寫低，等於做咗嘢冇留底，建議補返條款對齊）

### privacy.html（現有11章，已經幾完整）
現有已覆蓋：資料收集/用途/安全/用戶權利/Contact/第三方處理商/Retention/Cookies/EEA-UK/兒童私隱/HK PDPO

缺：
- **自動化決策披露**（GDPR Article 22相關——你嘅AI Research Score/Probability Score本質上係自動化評分，即使唔係「幫你落單」，都建議明確講清楚"呢啲評分係自動生成，唔涉及對你作出有法律效力嘅自動化決定"，先至企穩喺"research tool"呢個定位，唔跌入Article 22嘅"automated decision with legal/significant effect"範圍）
- 第三方名單建議喺Third-Party Data Processors章節明確列名（Stripe/Paddle、Google Analytics、DeepSeek/OpenAI、Cloudflare、Vercel、News API providers）——如果而家淨係寫類別冇列名，建議補齊，GDPR要求對用戶透明度要具體

### risk-warning.html（現有4章，偏薄）
現有：General Investment Risk / Not Investment Advice / No Guarantee of Returns / Your Responsibility

缺：
- **Historical Performance**獨立條款（"past performance does not guarantee future results"——依家可能merge咗喺其他條款入面，但呢句喺全球金融業係標準必寫獨立句，建議獨立成節）
- **AI Limitation**（風險警告專屬版本，同terms.html嗰個唔一樣——呢度要講嘅係"AI分析可能有誤，唔應該作為唯一依據"呢個風險角度，terms.html嗰個係法律責任角度，兩者角度唔同，都要有）
- **Education Purpose**框架句（"For research, education and decision-support purposes only"）
- **No Fiduciary Relationship**（明確講XFINLAB唔係你嘅財務顧問，冇fiduciary duty）

### 完全缺席嘅獨立頁面

| 頁面 | 現狀 | 建議 |
|---|---|---|
| **AI Disclaimer** | 無獨立頁，內容散落喺terms/risk | **新建，優先級最高**（EU AI Act時效性） |
| **Market Data Disclaimer** | 無獨立頁 | 新建（或至少terms.html補條款） |
| **Affiliate Disclosure** | 無——但你哋已經有broker affiliate CTA（#599 IBKR/Moomoo等） | **新建，優先級高**（已經有affiliate連結但冇披露，呢個係最直接嘅合規缺口） |
| **Cookie Policy** | 已有cookie-consent.js技術實現+privacy.html內有Cookies一節 | 建議獨立成頁（cookie banner通常link去獨立頁，而唔係成份privacy.html） |
| **Methodology** | 無 | 新建（你自己提出，值得做） |
| **Model Limitations** | 無 | 新建（你自己提出，值得做） |
| Refund Policy | 已有refund.html | 已覆蓋 |
| API Terms | 已有api-terms.html | 已覆蓋，可以按上面Acceptable Use清單覆核一次 |

---

## 2. 建議頁面架構（Footer完整版）

```
About | Pricing
Terms of Service | Privacy Policy | Risk Warning | AI Disclaimer
Market Data Disclaimer | Affiliate Disclosure | Cookie Policy
Refund Policy | Methodology | Model Limitations | Contact
```

---

## 3. AI Disclaimer 頁面建議內容（優先新建）

```
AI-Generated Content Notice

XFINLAB uses artificial intelligence to generate research analysis,
scores, reports and chat responses. This content is machine-generated
and has not undergone individual human editorial review prior to
display.

AI-generated content may be inaccurate, incomplete, outdated, or
reflect limitations in the underlying models and data. Always verify
important information independently before making financial decisions.

This notice is provided in accordance with applicable AI transparency
requirements, including the EU AI Act.
```

---

## 4. Methodology + Model Limitations 頁面建議大綱

**Methodology（研究方法論）**
- Research Score點計（用返你已有嘅Confluence Engine多因子邏輯嚟解釋，唔使發明新嘢）
- Probability/Risk/News Score嘅基本原則（一句講清楚：based on historical statistical pattern，唔係保證）
- 強調：模型分析，唔係保證結果

**Model Limitations（模型限制）**
- 資料延遲/缺失可能導致誤差
- 市場環境改變會令歷史形態失效（regime change風險）
- 提醒用戶應結合自身判斷，唔應該淨係靠平台分析

呢兩版內容你哋其實已經有現成素材——技術文件、Decision Journal（#221）、Market Regime Detector（#198）呢啲已建好嘅功能本身就係最好嘅佐證，寫呢兩頁基本上係將現有技術文檔整理成用戶可讀版本，唔使重新諗嘢。

---

## 5. 實施優先順序

1. **AI Disclaimer**（新建）——EU AI Act時效性最強
2. **Affiliate Disclosure**（新建）——已經有affiliate連結但冇披露，屬於現行缺口
3. **risk-warning.html補強**（Historical Performance / AI Limitation / No Fiduciary）
4. **terms.html補強**（Service Description / IP / Acceptable Use）
5. **Methodology + Model Limitations**（新建，你自己提出，優先級可以擺後少少，但值得做）
6. **Market Data Disclaimer + Cookie Policy獨立成頁**（現有內容拆出嚟，工作量細）

---

*本文件為法律頁面架構整理，非正式法律意見。正式落地前建議搵相關司法管轄區（尤其歐盟AI Act、香港PDPO/SFC）嘅執業律師覆核最終文字。*
