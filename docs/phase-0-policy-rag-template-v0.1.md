---
title: 政策 RAG 提取模板 v0.1
type: policy-rag-template
version: 0.1
status: draft
date: 2026-09-19
agent: 20-经济-Economy
project: EconomyAdvisor
phase: 0
related:
  - docs/phase-0-policies-corpus-v0.1.md (工作树已删 · git HEAD cc824a0 历史可查 · 25/50 条政策语料库)
  - 项目开发计划.md §3 政策文件解读 (工作树已删 · git HEAD cc824a0 历史可查)
  - 项目开发计划.md §5 Phase 0 资产盘点 (工作树已删 · git HEAD cc824a0 历史可查)
tags:
  - phase-0
  - policy-rag
  - extract-template
  - 受益板块映射
  - 5字段提取
---

# 政策 RAG 提取模板 v0.1

> Phase 0 沉淀资产 · 为 Phase 1 政策解读 RAG 通道奠基
> **定位**:政策文件入库 LLM 解读前的"提取规范",非最终解读输出,非 RAG 检索 prompt
> **对应**:产品定位第 2 点"政策可行动" + 项目开发计划 §3 第 2 项"政策文件解读"
> **状态**:与现有 25/50 政策语料库(POL-01 ~ POL-32)对接,Phase 1 启动后即可作为"政策入库 → 5 字段抽取 → 受益板块映射 → 飞书 Agent 解读"流水线的第 2 步规范

---

## §0 适用与不适用

**适用**

- 政策文件入库后,LLM 提取前的"字段化预处理"规范
- Phase 1 飞书 Agent 政策解读 prompt 的"输入契约"
- Phase 1 政策 RAG 主题检索的"标准化输出"格式

**不适用**

- 不替代 LLM 的最终解读(LLM 仍负责"含义翻译 + 普通人友好化")
- 不替代 `phase-0-policies-corpus-v0.1.md` 政策库本身(本文件是"提取模板",非"政策库")
- 不替代事件库 ingest 通道(`backend/event/ingest_event.py` 工作树已删,git HEAD cc824a0 历史可查)

---

## §1 5 字段提取规范

每条政策入库 LLM 解读前,先由 extractor(LLM 或规则+LLM 混合)提取以下 5 个字段。字段名固定,值类型固定,缺失值用 `null` 而非空字符串。

### 1.1 政策主体(issuing_body)

- **类型**:string
- **要求**:政策发布机构全称,如"中国人民银行 + 国家金融监督管理总局 + 中国证券监督管理委员会 + 国家外汇管理局"(POL-30 五部门联合)
- **多机构**:用 ` + ` 分隔,按"中央 → 地方 → 行业"层级排序
- **缺失值**:`null`(政策来源不明)

### 1.2 政策层级(policy_level)

- **类型**:enum[string]
- **取值**:
  - `central_top` —— 国家级顶层方略(如 POL-30《金融强国"十五五"规划》)
  - `central_sector` —— 国家级行业部委细则(如 POL-01《保险公司资产负债管理办法》/ POL-15《中小企业"十五五"规划》)
  - `local_top` —— 省市级顶层(如 POL-29 北京数字经济"十五五"规划)
  - `local_sector` —— 省市级行业细则
  - `industry_self` —— 行业自律(如 POL-31 中钢协倡议书 / POL-32 市场监管总局行政指导)
  - `international` —— 国际对照(如 POL-25 日本 / POL-26 香港 / POL-27 美国)
- **缺失值**:`null`

### 1.3 政策类别(policy_category)

- **类型**:enum[string]
- **8 大类**(与 `phase-0-policies-corpus-v0.1.md §4 主题速查矩阵` 对齐):
  - `finance` —— 金融(含银行/保险/证券/治理/科技金融/普惠/养老/数字金融)
  - `real_estate` —— 房地产(新模式/供需/保障房/REITs)
  - `digital_economy` —— 数字经济(算力/算法/数据要素/6G/AI/机器人)
  - `industrial` —— 工业(供给侧/反内卷/钢铁/制造)
  - `platform_regulation` —— 平台监管(反垄断/反不正当竞争/独家合作/全网最低价)
  - `sme` —— 中小企业(融资/回款/商业票据/账款披露)
  - `international` —— 国际对照(地产危机/金融危机/救市)
  - `macro_top` —— 宏观顶层(五年规划/中央金融办/顶层方略)
- **缺失值**:`null`

### 1.4 实施窗口(implementation_window)

- **类型**:object
- **子字段**:
  - `start_date` —— string(YYYY-MM-DD),实施/施行起始日
  - `end_date` —— string(YYYY-MM-DD) 或 `null`(长期/无限期)
  - `transition_period_years` —— number 或 `null`,过渡期年数(如 POL-01 保险公司新规 3 年过渡期)
  - `effective_phases` —— string[] 或 `null`,分阶段实施时间表(如 POL-29 北京数字经济"2026-2030 年均 8%,2030 占 GDP 50%")
- **缺失值**:全部子字段填 `null`

### 1.5 受益/受损板块(beneficiary_sectors)

- **类型**:object
- **子字段**:
  - `beneficiary` —— string[] —— 受益板块大类(从 8 大类受益池中选取,见 §2)
  - `damaged` —— string[] 或 `null` —— 受损板块大类
  - `mapping_detail` —— string[] —— 受益/受损 A 股标的简写清单(如"中国平安/中国人寿/中国太保/新华保险"),与 `phase-0-policies-corpus-v0.1.md §3 各 POL 条 mapping` 对齐
- **缺失值**:`mapping_detail` 可填 `[]`,`beneficiary`/`damaged` 至少有一项非空

---

## §2 8 大类受益板块池

8 大类受益板块池与现有政策库 32 大类受益板块映射对齐(沿用 `phase-0-policies-corpus-v0.1.md §3 POL-29/30/31/32` 4 条 8 大类映射)。RAG 提取时按受益板块"大类 → 子类 → A 股标的"三层展开。

| 受益大类 | 典型子类 | 标的池(示例) |
|---|---|---|
| 金融顶层 | 银行/保险/证券/治理/科技金融/普惠/养老/数字金融 | 工行/建行/中国平安/中信证券 等 |
| 数字经济 | 算力链/数字视听/6G/词元工厂/机器人/数据要素/网络安全/IDC | 浪潮/紫光/海光/中际旭创 等 |
| 工业供给侧 | 钢铁头部/黑色系/PPI 工业品/钢铁出口/三季报预期/并购重组/绿色低碳钢/配套金融 | 河钢/宝武/鞍钢/首钢/中信特钢/沙钢 等 |
| 平台监管(供给侧修复) | 中小酒店餐饮/合规供应商/差异化平台/酒店用品产业链/酒店 SaaS/反垄断合规科技/消费者权益保护链/合规咨询 | 美团/抖音/京东/携程/同程/飞猪 上下游标的 |
| 房地产新模式 | 保障房/REITs/城市更新/收并购/优质房企/物业服务/装修家电/房贷利率敏感 | 保利/万科/招商蛇口/华夏幸福 等 |
| 中小企业 | 融资/商业票据/账款披露/小微贷款/科创金融/创业扶持 | 各地城商行/网商银行 等 |
| 国际对照 | 历史相似情境救市标的 | 不直接映射,仅作为"历史剧本"对照 |
| 宏观顶层 | 5 年规划受益板块/顶层方略长期标的 | 全市场映射 |

---

## §3 提取流水线位置

Phase 1 启动后,政策 RAG 提取流水线分 4 步:

```
[Step 1] 政策原文 PDF / 日报段落级
    ↓
[Step 2] 本模板 5 字段提取(extractor + LLM 兜底)
    ↓
[Step 3] 受益/受损板块 8 大类映射(本模板 §2 池 + RAG 检索补充)
    ↓
[Step 4] LLM 解读(政策可行动 prompt,Phase 1 飞书 Agent)
```

**本模板定位**:第 2-3 步规范,不替代第 4 步 LLM 解读。

---

## §4 缺失与下一步

### 4.1 当前缺失

- **extractor 实现**:Phase 0 期间 `backend/` 全删(工作树 29 文件删除悬空),extractor 代码未落地,本模板为规范层不涉及实现
- **5 字段抽取 prompt**:Phase 1 启动后再起草,与飞书 Agent 解读 prompt 配套
- **8 大类受益池标的清单**:仅给示例,需 Phase 1 启动后基于 25/50 政策库全量映射后固化 v1.0

### 4.2 下一日 9-20 T1 计划(由 9-19 cron 提建议)

- **优先级 1(P0)**:待张勇决策 29 文件删除(a/b/c)+ Phase 0 验收标准(继续/降级)
- **优先级 2(P1)**:政策语料库续补 POL-33+(候选:POL-33 国资委央企带头按时足额支付中小企业款项 + POL-34 证监会上市公司应付账款披露强化 + POL-35 工信部商业票据承兑期限监管 + POL-28 国际对照 1 条),目标 9-30 累计 50/50
- **优先级 3(P1)**:inspiration-index §2 末尾追加 POL-19 ~ POL-32 14 条索引(9-6 地产前史 6 条 + 9-9 POL-25 + 9-10 POL-26 + 9-11 POL-29 + 9-12 POL-27 + 9-14 POL-30 + 9-16 POL-31 + 9-17 POL-32 = 14 条)
- **跳过项**:5 字段 extractor 代码实现 / 飞书 Agent 政策解读 prompt / 受益池标的清单固化 —— 均依赖 §5-2 装包 + Phase 1 启动决策

---

## §5 命名与归档约定

- 本文件位置:`EconomyWeb/docs/phase-0-policy-rag-template-v0.1.md`
- 字段名固定:5 字段 + 实施窗口子字段,跨政策可引用
- enum 取值固定:政策层级 6 类 + 政策类别 8 类,枚举值变更须升 v1.0
- 受益板块用大类 → 子类 → A 股标的三层,不扁平化
- 缺失值用 `null`,不用空字符串/占位字符串

---

## 关联文档

- [`项目开发计划.md §3 政策文件解读`](../项目开发计划.md) —— 工作树已删,git HEAD cc824a0 历史可查
- [`docs/phase-0-policies-corpus-v0.1.md`](phase-0-policies-corpus-v0.1.md) —— 工作树已删,git HEAD cc824a0 历史可查 · 25/50 政策语料库
- [`docs/phase-0-attribution-schema-v0.1.md`](phase-0-attribution-schema-v0.1.md) —— 工作树已删,git HEAD cc824a0 历史可查 · 资产归因 schema
- [`docs/phase-0-event-library-design-v0.1.md`](phase-0-event-library-design-v0.1.md) —— 工作树已删,git HEAD cc824a0 历史可查 · 事件库设计

## 变更记录

| 时间 | 变更 | 触发 |
|---|---|---|
| 2026-09-19 03:10 | 首次建库:5 字段提取规范 + 8 大类受益板块池 + 与 25/50 政策语料库对接 + 提取流水线 4 步定位 + §4 缺失与下一步 + §5 命名约定 + 关联文档段 | 每日 03:10 cron · .plan/20260919.md · 9-19 巡检 P0 第②项挂账应对 · 避开 29 文件删除决策 |
