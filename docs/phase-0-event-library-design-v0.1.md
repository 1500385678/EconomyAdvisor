---
aliases:
  - phase-0-event-library-design-v0.1
tags:
  - phase-0
  - design
  - event-library
  - schema
created: 2026-09-03
updated: 2026-09-03
---

# Phase 0 §5 事件库 v0.1 设计

> EconomyAdvisor · 历史事件库最小版方案
> 对应 `项目开发计划.md §5`:`整理近 10 年 50 个关键政策文件 + 100 个历史宏观事件,建结构化事件库`
> 目的:把"事件库"这个 Phase 0 资产盘点的最后一个未启动子项,从"建表+标签+相似度检索"三件套给出可落地的最小设计

---

## §0 现状

**已落地**

- 归因 schema v0.1(2026-08-31 · `phase-0-attribution-schema-v0.1.md` · 五档:政策/资金/海外/情绪/技术)
- 5 大官方源接入清单 v0.1(2026-08-25)
- akshare 解析层落地,5 指标 schema + probe + parse 收口(2026-08-26~29)
- frontend 最小骨架(2026-08-28 · 1 主页 + 1 API)

**未启动**

- 事件库表结构、标签体系、相似度检索算法
- 50 政策 + 100 事件的来源与采集流程
- 跨事件"剧本模板"抽象(用于 Phase 1 跨周期对比)

---

## §1 设计目标(3 点)

1. **可入库**:单一 SQLite 表 `event` + `event_tag` + `event_relation` 三表,跟现有 `economy_ingest.db` 同库
2. **可检索**:按 `event_date` / `category` / `tag` / `related_indicator_code` 四维度快速过滤
3. **可对比**:每条事件预留 `playbook_id` 字段,Phase 1 用 playbook 做"这次像哪次"的跨周期对比

**Phase 0 只交付** §2 schema + §3 标签体系 + §4 数据契约;§5 相似度算法 v0.1 推迟到 Phase 1 MVP。

---

## §2 表结构 v0.1(SQLite)

> 复用 `data/economy_ingest.db`,新增 3 张表,与 `indicator` / `indicator_value` 同库

### 2.1 `event` 主表

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | 内部 id |
| `event_code` | TEXT UNIQUE NOT NULL | 业务码,形如 `EVT-2015-06-12-001`,同日期可多条 |
| `event_date` | TEXT NOT NULL | YYYY-MM-DD,事件发生日(政策以发文日为准) |
| `category` | TEXT NOT NULL | 见 §3.1 大类枚举 |
| `title_cn` | TEXT NOT NULL | 中文标题(<= 40 字) |
| `title_en` | TEXT | 英文标题(可选) |
| `summary` | TEXT | 1-3 句摘要(200-500 字) |
| `source_url` | TEXT | 官方源 URL |
| `source_org` | TEXT | 来源机构(如"央行"、"国务院"、"证监会") |
| `impact_score` | INTEGER | 1-5 主观影响分,Phase 0 暂不填,Phase 1 写归因时回填 |
| `playbook_id` | TEXT | 剧本模板编码(如 `PB-RATE-CUT-Emergency`),Phase 0 留空 |
| `created_at` | TEXT NOT NULL DEFAULT (datetime('now')) | |
| `updated_at` | TEXT NOT NULL DEFAULT (datetime('now')) | |

**索引**:`event_date`、`category`、`playbook_id` 各一索引。

### 2.2 `event_tag` 多对多标签

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_id` | INTEGER NOT NULL FK→event.id | |
| `tag` | TEXT NOT NULL | 见 §3.2 标签词典 |
| PRIMARY KEY | (event_id, tag) | |

**索引**:`tag` 一索引,用于"找所有带 X 标签的事件"。

### 2.3 `event_relation` 事件↔事件 / 事件↔指标

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | |
| `from_event_id` | INTEGER NOT NULL FK→event.id | |
| `to_event_id` | INTEGER | 事件↔事件关系(留空表示事件↔指标) |
| `to_indicator_code` | TEXT | 指标 code(留空表示事件↔事件) |
| `relation_type` | TEXT NOT NULL | 枚举:cause/followup/similar/related |
| `weight` | REAL DEFAULT 1.0 | 关系强度 0-1,Phase 1 相似度算法用 |

**说明**:事件↔指标用 `to_indicator_code`(关联现有 `indicator.code`);事件↔事件用 `to_event_id`。

---

## §3 标签体系

### 3.1 大类(category) · 8 档

| category | 范围 | Phase 0 目标条数 |
|---|---|---|
| `policy-monetary` | 货币政策(利率/准备金/公开市场操作) | 12 |
| `policy-fiscal` | 财政政策(赤字/专项债/减税) | 8 |
| `policy-regulatory` | 监管政策(资管新规/房地产/平台) | 10 |
| `data-release` | 关键数据公布(GDP/CPI 超预期) | 20 |
| `market-shock` | 市场异动(股灾/汇市闪崩/债灾) | 15 |
| `global-event` | 海外事件(美联储/Fed/欧债/地缘) | 20 |
| `industry-event` | 行业事件(房地产/新能源/半导体周期) | 10 |
| `structural` | 结构性事件(人口拐点/地产周期切换) | 5 |
| 合计 | | **100** |

### 3.2 细标签(tag) · 自由词,受 §3.3 词典约束

例:`降息`、`降准`、`LPR 调降`、`房地产融资三支箭`、`硅谷银行`、`俄乌冲突`、`地方债一揽子化债`、`PMI 重回扩张区间`

**注意**:`tag` 是自由词,但为避免膨胀,新建 tag 时必须从 §3.3 词典选;词典外新词需写一句"为什么不能复用现有 tag"。

### 3.3 起步词典(首批 30 个,Phase 0 期间滚动扩充到 80)

- 货币政策 8:`降息` `降准` `LPR 调降` `MLF 续作` `逆回购` `再贷款` `PSL` `结构性工具`
- 财政政策 4:`专项债` `特别国债` `减税降费` `赤字率`
- 监管政策 6:`资管新规` `房地产三支箭` `平台经济` `注册制` `退市新规` `减持新规`
- 市场异动 6:`股灾` `债灾` `汇市闪崩` `商品暴跌` `流动性危机` `信用违约`
- 海外 4:`美联储加息` `美联储降息` `欧债危机` `中美贸易摩擦`
- 数据 2:`GDP 超预期` `CPI 超预期`

---

## §4 数据契约 v0.1

### 4.1 来源策略

- **政策类**(policy-*)优先一手源:央行/财政部/发改委/国务院 官网原文
- **数据类**(data-release)直接用 §5-2 拉下来的 `indicator_value` 反查(例:CPI 公布日某月值偏离前值 0.5pp 自动入库)
- **市场异动**(market-shock)人工录入,留 3-5 条元数据(标的 / 涨跌幅 / 主因)
- **海外类**(global-event)摘 FOMC 议息会议纪要 + 美财政部公告
- **行业/结构性**:人工录入,Phase 0 不爬虫

### 4.2 录入流程(Phase 0 半自动)

1. 找候选:每周从 `data-release` 自动扫一遍(用现有 `indicator_value` 时序 + 阈值触发)
2. 人工审:每日 1 条候选 → 编辑 `title_cn` / `summary` / `tag` → 入 `event` 表
3. 政策原文:周末 1-2 小时,集中录入本周重要政策(目标 1-2 条/周)
4. 100 事件目标:Phase 0 周期内(到 9-6)先冲到 30,Phase 1 持续到 100

### 4.3 与归因 schema v0.1 的关系

| 归因档位 | 事件库对应字段 |
|---|---|
| 政策 | `event.category in policy-*` |
| 资金 | `event.tag` 含 `流动性` / `MLF` / `降准` / `社融` |
| 海外 | `event.category = global-event` |
| 情绪 | `event.tag` 含 `恐慌` / `VIX` / `北向资金` |
| 技术 | 不在事件库,归因时单独算(动量/突破) |

> 即:归因 schema 是"对当下资产波动的解释",事件库是"对历史上发生过的同类事情的记忆"。两者通过 `playbook_id` 关联,Phase 1 再打通。

---

## §5 相似度算法(推迟到 Phase 1)

Phase 0 不实现,仅占位设计:

- 维度 1:tag Jaccard 相似度(快速过滤)
- 维度 2:事件↔指标关联图嵌入(节点 = event,边 = same playbook)
- 维度 3:category + impact_score 二次过滤

输出:给定 1 个新事件,返回 Top-5 历史相似剧本 + 后续 30/90 天路径。

---

## §6 Phase 0 交付清单

- [x] §2 三表 DDL v0.1
- [x] §3.1 八大类 + 目标条数
- [x] §3.3 30 tag 起步词典
- [x] §4.1-§4.2 来源策略 + 录入流程
- [ ] `backend/event/__init__.py` + `event_schema.py` + 录入 CLI(下一日)
- [ ] `event` 30 条首批录入(2026-09-06 前)
- [ ] frontend `/api/events` 路由(只列 Top-10 最新,Phase 1 再加相似度)

---

## §7 变更记录

- **2026-09-03** v0.1 初稿:三表 schema + 8 大类 + 30 tag 词典 + 录入流程
