# XFINLAB「全球市場模擬層」開源專案地圖(已驗證版)

> 呢份文件同 `XFINLAB_Global_Simulation_Roadmap.md`(Phase 0/1/2規劃)配套使用。淨係列已經直接查證license文字嘅項目,唔包含未驗證嘅猜測。

---

## 一、可直接用嘅code base(3個)

| 項目 | 實際係咩 | License(直接查證) | 點用 |
|---|---|---|---|
| **agency-swarm**(VRSEN,即"agency-agents") | 多agent orchestration framework,可以起「AI辯論/多角色分析」呢類功能 | MIT | 可直接攞code落嚟,改到適合XFINLAB嘅agent debate/研究流程 |
| **GeoPulseWebApp** | 地緣政治監察dashboard,Python/Streamlit | MIT | 目前配對最好嘅一個——UI佈局同數據呈現方式可以直接參考甚至攞部分code |
| **Microsoft MarS** | 金融市場模擬引擎(Large Market Model),Microsoft Research出品 | MIT(直接fetch LICENSE file確認) | 如果將來要做「訂單流/市場微觀結構模擬」,呢個係目前查到最正規、最可信嘅選擇 |

MIT license嘅共同意思:可以商業用、可以改、可以閉源,淨係要保留原作者copyright聲明。冇AGPL嗰種「要公開晒你自己改過嘅code」嘅包袱。

---

## 二、只可以參考、唔可以攞code嘅項目(2個)

| 項目 | 問題 |
|---|---|
| **koala73/worldmonitor**(同 lenage/worldmonitor,其實係同一個project嘅fork) | AGPL-3.0 + 明文要求商業/SaaS用途要另購商業license。淨係可以睇UI/功能設計做靈感,自己重新寫code,唔可以直接攞佢哋嘅code。 |
| **Equibles** | 純AGPL-3.0(冇額外商業限制,但AGPL本身嘅網絡copyleft條款——你部署做SaaS就要公開你改過嘅全部code——對proprietary平台嚟講都係要避開嘅包袱) | 同上,參考優先 |

---

## 三、查完發現唔存在/唔啱用嘅項目(7個)

呢批全部係嗰個AI提出但未經驗證嘅名,已經逐個去搵返實際repo/license確認:

| 名 | 查證結果 |
|---|---|
| Fincept Terminal | 有,但雙授權條款極端苛刻(六位數美金違約金、連帶責任、刑事條款),企硬唔好碰 |
| "AI market terminal" / "geopolitics aesthetic" | 查唔到對應嘅具體單一repo,似係泛稱/風格描述,唔係實際project |
| IntelDesk | 對唔上——真實命中係商業OSINT產品(冇公開source)+一個MATLAB畢業生project(冇license) |
| EchoPolis | 唔存在——查唔到任何相關software,只有一個2018年城市規劃研討會同名 |
| resilience.io | 有呢個NGO項目,但2016年後冇更新,搵唔到公開repo或license |
| Invest Sim | 太泛,一堆唔同作者嘅hobby project撞名,冇one canonical project |
| QUSHi | 有,但係商業proprietary交易教育app,唔係open source |

---

## 四、同 Roadmap 現有Phase點對應

| Roadmap階段 | 用邊個開源項目 |
|---|---|
| Phase 0(重新包裝現有數據) | 唔需要外部code,用返GDELT+FRED/ECB+FinBERT+shipping proxy(全部已有) |
| Phase 1(產業資金流向、社交擴展) | UI/佈局參考GeoPulseWebApp;如果要加「AI辯論式」分析角度,用agency-swarm起 |
| Phase 2(進階/長遠) | 如果將來真係要做訂單流/市場微觀結構模擬,Microsoft MarS係最穩陣嘅底層選擇;世界地圖UI靈感可以參考koala73/worldmonitor(但唔攞佢code) |

---

## 五、總結

6個新提出嘅名,得1個(Microsoft MarS)係真實、有清晰MIT license、可以商業用。連同之前輪驗證嘅agency-swarm、GeoPulseWebApp,總共3個project可以放心攞code落嚟起野。AGPL嗰兩個(worldmonitor、Equibles)淨係做UI/架構參考。其餘7個要就係查唔到,要就係唔開源,唔好再當佢哋係可用選項。
