---
aliases:
  - 20260901-wind-compliance-memo
tags:
  - plan
  - phase-0
  - wind
  - ifind
  - 10jqka
  - compliance
  - memo
created: 2026-09-01
updated: 2026-09-01
---

# 2026-09-01 · Wind/iFinD/同花顺 合规边界 Memo v0.1

> Phase 0 §5-5 · EconomyAdvisor
> 对应 `项目开发计划.md §5` 第 5 条:`调研 Wind/iFinD/同花顺的 API 接入成本与合规边界`
> 目的:在动手接 Wind 替代源前,先把"我们能不能用、用到哪一层、商用是否要授权"3 个问题说清楚,
> 避免 v0.1 demo 跑通后才发现"个人非商用 + 数据二次分发"踩雷

---

## §0 调研范围

- **目标厂商**:
  - **Wind(万得)** · 金融数据终端老牌,字段最全,但商业授权最严
  - **iFinD(同花顺 iFinD)** · 同花顺旗下机构终端,字段与 Wind 高度重合
  - **10jqka(同花顺 iFinD 互联网版)** · 散户终端,部分数据免费
- **3 档判断口径**:
  - **L1 个人非商用 + 教学 / 学术 / 内部研究**:大多数厂商明示允许,但禁止二次分发与转售
  - **L2 互联网产品(API / Web / 小程序)免费版接入**:有 3 家长都做了严格白名单 / 限流 / 字段阉割
  - **L3 商业化对外服务 / 卖方研报 / 机构订阅**:必须签正式商务合同 + 数据许可证,价格 6 位数 / 年起步

---

## §1 Wind(万得) — 合规边界 L3 起步

| 维度 | 内容 |
|---|---|
| 官网 | https://www.wind.com.cn |
| 终端形态 | PC 端 Windows 客户端 + Web 端(wind.com.cn 需登录) |
| API 形态 | **无公开 REST/WebSocket API**;Python SDK `WindPy` 仅对机构授权账号开放,需本地安装客户端 + USB Key |
| 个人非商用条款 | 万得 EULA 明示"个人非商业用途"可使用 Wind 终端,但**禁止任何形式的二次分发、再许可、SaaS 化转售** |
| 字段粒度 | 宏观 + 行业 + 财务 + 行情 + 衍生品全量,**字段最全** |
| 接入成本 | 个人 ¥ 0(已有终端账号)/ 机构 ¥ 30,000-200,000 / 年,API 接入另议 |
| **EconomyAdvisor 判断** | **不在 v0.1 接入**;Phase 1 MVP 全程用免费源(NBS/PBOC/MOF/GACC + akshare/aktools);Phase 3 商业化阶段再议机构授权 |

**风险点**:
- 即使从公开媒体引用 Wind 二手数据(其他研报转引),也需在引用处注明"数据来源:Wind",且不能用作我们 LLM 的"训练 / 微调"语料
- 万得近年加强了对爬取 / 镜像 / 缓存的监控,**不要尝试任何形式的 Wind 镜像站抓取**

---

## §2 同花顺 iFinD — 合规边界 L2 起步

| 维度 | 内容 |
|---|---|
| 官网 | https://www.10jqka.com.cn / https://www.iFinD.com |
| 终端形态 | iFinD PC 终端(机构版) + 同花顺 App / Web(散户版) |
| API 形态 | iFinD Python SDK 同 Wind,**仅机构授权**;**同花顺开放平台**(`open.10jqka.com.cn`)提供免费版 HTTP API,**字段阉割**(无衍生品 / 无高频 tick / 无逐笔成交) |
| 个人非商用条款 | 散户 App / Web 个人浏览免费,但**开放平台 API 必须注册开发者账号 + AppKey**,且明示"非商用 + 限流 1000 次/日" |
| 接入成本 | 个人 AppKey ¥ 0(实名认证 + 手机号)/ 机构授权 ¥ 20,000-150,000 / 年 |
| 字段粒度 | 宏观 + A 股行情 + 财务三件套(资产负债表 / 利润表 / 现金流量表) + 公告 + 资金流;**L1 字段**够用 |
| **EconomyAdvisor 判断** | **v0.1 阶段不接**;Phase 1 MVP 优先用 akshare + 官方源;Phase 2 专题研报时,若需要"个股 + 财务三件套"高粒度,可申请同花顺开放平台 AppKey,做白名单限流使用 |

**风险点**:
- 同花顺开放平台对**二次分发**有严格限制,生成的图表 / 数据集**不能直接对外公开**,仅供"调用方内部使用"
- 同花顺 iFinD 与 Wind **字段定义不完全一致**,若同时引用两源数据,**必须在引用处注明来源**

---

## §3 10jqka 散户版(同花顺 Web/App) — 合规边界 L1

| 维度 | 内容 |
|---|---|
| 官网 | https://www.10jqka.com.cn |
| API 形态 | **无官方 API**;Web 端数据来自后端 XHR,App 端部分接口可 MITM 抓,但 **Robots.txt 与 ToS 明确禁止** |
| 个人非商用条款 | 个人浏览免费,但**禁止自动化抓取**;**禁止将数据二次分发至 SaaS / 公众号 / 小程序 / 任何第三方产品** |
| 接入成本 | 表面 ¥ 0,实质**法律风险 ¥ ???** |
| 字段粒度 | 行情 + 公告 + 资金流 + 研报;宏观指标覆盖浅 |
| **EconomyAdvisor 判断** | **绝对不接**;即使在 v0.1 demo 阶段,也不爬;若需要散户可看的同源数据,改走 akshare(akshare 已合法镜像同花顺等公开源) |

**风险点**:
- 同花顺对**爬虫 / 自动化抓取**维权案例较多(2023-2024 多起),**直接爬 10jqka.com.cn / 抓 App XHR = 法律红线**
- akshare / baostock / tushare pro / akshare-stock 等开源数据源已**合法镜像**部分公开数据(注明来源),**优先用这些**

---

## §4 综合建议(对 §5-5 落地)

| 优先级 | 厂商 | EconomyAdvisor 接入策略 | 时间窗口 |
|---|---|---|---|
| **P0(本期立即)** | 5 大官方源(NBS/PBOC/MOF/GACC/MOFCOM 跳过) | 已 P0/P1 接入,无需 Wind 替代 | Phase 0(2026-09-06 前) |
| **P0(本期立即)** | akshare / baostock / tushare pro | 已通过 akshare 接入 5 指标,其他按需扩展 | Phase 0(持续) |
| **P1(中期)** | 同花顺开放平台 | 若需要个股财务数据,申请 AppKey 走白名单;**绝不爬 10jqka** | Phase 1-2 |
| **P2(商业化前)** | Wind / iFinD 机构版 | Phase 3 商业化前,签正式商务合同;**绝不在 demo / MVP 阶段硬接** | Phase 3(2027-Q2+) |

**v0.1 结论**:5 大官方源 + akshare 已覆盖 Phase 0 全部 P0 指标(GDP / CPI / PMI / M2 / 社融),**§5-5 调研确认无需接 Wind / iFinD**;Phase 3 商业化时再启动机构授权流程。

---

## §5 关联文档

- `项目开发计划.md §5` 第 5 条:调研 Wind/iFinD/同花顺的 API 接入成本与合规边界
- `docs/phase-0-data-source-catalog-v0.1.md`:5 大官方源接入清单(2026-08-25)
- `docs/phase-0-attribution-schema-v0.1.md`:归因 schema v0.1(2026-08-31)
- `Logs/巡检-经济-20260901.md` P1 独立可做第①项:Wind 合规边界 memo

---

## 变更记录

- **2026-09-01** v0.1 · 初稿 · 张勇 T3 daily 任务 · `docs/phase-0-wind-compliance-memo-v0.1.md`
