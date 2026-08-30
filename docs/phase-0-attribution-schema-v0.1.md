---
aliases:
  - 20260831-attribution-schema
tags:
  - plan
  - phase-0
  - attribution
  - schema
  - v0.1
created: 2026-08-31
updated: 2026-08-31
---

# 2026-08-31 · 资产波动归因 Schema v0.1

> Phase 0 §5-6 · EconomyAdvisor
> 对应 `项目开发计划.md §5` 第 6 条:`设计"归因"输出的标准 schema(政策/资金/海外/情绪/技术 五档 + 权重)`
> 目的:把"今天为什么跌/涨"这种主观问题,固化成 LLM 可生成、程序可解析、人可读懂的结构化 JSON,作为 §3 资产波动归因 MVP 的输入/输出契约

---

## §0 背景与定位

### 0.1 为什么先定 schema

- **MVP 强依赖**:§3 资产波动归因 MVP 覆盖沪深300/国债/原油/USDJPY 4 个标的,日度输出,必须先有 schema 才能开始写 prompt / 写评测 / 写展示
- **评测前置**:§5-4 LLM 在 4 类任务(指标解读/政策摘要/归因/历史对比)基线准确率评估,**归因这一档的"标准答案"必须用结构化 schema 才能打分**
- **避免先实现后重构**:v0.1 宁可在字段层"少而精",不要把 4 档堆成 N 档后,又因为粒度太粗/太细返工

### 0.2 适用场景

- 输入:资产 + 日期 + 当日涨跌幅 + 1-3 条原始新闻
- 输出:5 档归因(政策/资金/海外/情绪/技术) + 权重 + 置信度 + 时间戳 + 解释文本
- 目标读者:投资人 / 企业战略 / 媒体内容生产者(均非专业宏观研究员,但要"看得懂、敢引用、能追问")

### 0.3 不在 v0.1 范围

- ❌ 多日趋势归因(只做"日度单日",跨周/跨月归因留 v0.2)
- ❌ 个股归因(只做指数/标的级,个股留 v0.3 + §3 接入财报数据后再做)
- ❌ 自动归因引擎(只定 schema,实现留 Phase 1)
- ❌ 历史相似情境对比(那是 §3 跨周期对比模块,留 v0.2)

---

## §1 设计原则(5 条)

1. **5 档穷尽**:政策 / 资金 / 海外 / 情绪 / 技术,任何日度资产波动都应能归到这 5 档里,且一般会有 1-3 档同时显著
2. **权重可加和归一**:`Σ weight = 1.0`,避免 LLM 把"政策 0.9 + 资金 0.9"两个独立答案堆出来无法比较
3. **置信度独立于权重**:`weight` 是"这一档对当日波动的解释力",`confidence` 是"模型对这一档判断的把握",两者必须分开;典型场景:政策权重 0.7 但置信度 0.4(政策有风声但未落地)
4. **可枚举可解释**:每个档位的 `evidence` 字段必须有原始新闻/数据可追溯,不能只给"政策因素"一个空标签
5. **JSON-first · 人可读**:主输出是 JSON,`summary` 字段给一段 30-80 字的人话总结,UI 端直接展示

---

## §2 Schema 定义(JSON Schema 草案)

### 2.1 顶层结构

```json
{
  "$schema": "https://json-schema.org/draft-07/schema",
  "title": "EconomyAdvisor.Attribution",
  "type": "object",
  "required": ["asset", "date", "buckets", "summary", "generated_at", "model"],
  "properties": {
    "asset": {
      "type": "string",
      "description": "标的代码或简称,沪深300/国债/原油/USDJPY 等"
    },
    "date": {
      "type": "string",
      "format": "date",
      "description": "归因目标日期,ISO 8601 (YYYY-MM-DD)"
    },
    "movement": {
      "type": "object",
      "description": "当日实际涨跌(可选,用于校验归因方向)",
      "properties": {
        "change_pct": { "type": "number" },
        "direction": { "enum": ["up", "down", "flat"] }
      }
    },
    "buckets": {
      "type": "array",
      "minItems": 1,
      "maxItems": 5,
      "description": "5 档归因(实际只出现显著档位,但 schema 允许只填 1-5 档)",
      "items": { "$ref": "#/definitions/Bucket" }
    },
    "summary": {
      "type": "string",
      "minLength": 30,
      "maxLength": 200,
      "description": "30-80 字人话总结,UI 主展示"
    },
    "generated_at": {
      "type": "string",
      "format": "date-time",
      "description": "归因生成时间戳(ISO 8601 + 北京时)"
    },
    "model": {
      "type": "string",
      "description": "归因所用 LLM,例 'claude-sonnet-4' / 'deepseek-chat'"
    }
  },
  "definitions": {
    "Bucket": {
      "type": "object",
      "required": ["category", "weight", "confidence", "direction", "evidence"],
      "properties": {
        "category": {
          "enum": ["policy", "capital", "overseas", "sentiment", "technical"],
          "description": "5 档枚举"
        },
        "weight": {
          "type": "number",
          "minimum": 0,
          "maximum": 1,
          "description": "该档对当日波动的解释权重,Σ weight = 1.0"
        },
        "confidence": {
          "type": "number",
          "minimum": 0,
          "maximum": 1,
          "description": "模型对该档判断的置信度,独立于 weight"
        },
        "direction": {
          "enum": ["up", "down", "neutral"],
          "description": "该档是推动上涨/下跌/中性"
        },
        "evidence": {
          "type": "array",
          "minItems": 1,
          "maxItems": 5,
          "items": {
            "type": "object",
            "required": ["text", "source", "timestamp"],
            "properties": {
              "text": { "type": "string", "description": "证据原文(<= 100 字)" },
              "source": { "type": "string", "description": "来源(媒体名/官网/数据库)" },
              "timestamp": { "type": "string", "format": "date-time" }
            }
          }
        }
      }
    }
  }
}
```

### 2.2 5 档枚举语义

| 档位 (category) | 包含 | 不包含 |
|---|---|---|
| **policy(政策)** | 央行/财政部/发改委/监管文件、重要讲话、窗口指导、监管处罚 | 政策预期/吹风(归 sentiment) |
| **capital(资金)** | 北向资金、融资融券、ETF 申赎、社融、M2、DR007/Shibor、回购利率 | 长期资金面叙事(归 sentiment) |
| **overseas(海外)** | 美股/欧股/日股、商品(油/铜/金)、美债收益率、美元指数、海外央行政策、地缘 | 国内政策溢出(归 policy) |
| **sentiment(情绪)** | 风险偏好、VIX、媒体头条情绪、社交平台情绪、政策预期/吹风、机构观点 | 已落地的政策/数据(归对应档) |
| **technical(技术)** | 突破/跌破关键位、均线交叉、量能异动、期货升贴水、期权 PCR、波动率曲面 | 基本面驱动(归前 4 档) |

---

## §3 字段约束与边界

### 3.1 权重规则

- **Σ weight = 1.0**(同 `buckets` 内全部相加,允许 0.001 浮点误差)
- **最小 weight 阈值**:`weight < 0.05` 的档位应直接 drop,不进 `buckets` 数组(避免 5 档全 0.2 这种无信息归因)
- **典型分布**:
  - 1 档主导(政策日/数据日):`[0.85, 0.15]`
  - 2 档并列(政策 + 资金):`[0.50, 0.40, 0.10]`
  - 3 档混合(海外 + 资金 + 情绪):`[0.45, 0.30, 0.20, 0.05]`
  - 极少见 4 档,5 档全占基本不会出现

### 3.2 置信度规则

- **0.0-0.3**:低(单一信号 / 解读空间大)
- **0.3-0.6**:中(多源印证但有分歧)
- **0.6-0.9**:高(数据落地 + 多家媒体一致)
- **0.9-1.0**:极高(政策原文/官方数据直接驱动,几乎无解读空间)

### 3.3 evidence 规则

- 每档至少 1 条 evidence,最多 5 条
- `text` 必须是可直接引用的原文(<= 100 字),不允许"据报道""市场认为"这种转述
- `source` 用统一格式:`媒体名/官网/数据库`,例 `新华社` / `央行官网` / `Bloomberg` / `akshare:macro_china_cpi`
- `timestamp` 必须是 ISO 8601,允许与 `date` 不同(隔夜事件可早于 `date`)

### 3.4 direction 规则

- 与 `movement.direction` 一致性:5 档的 `direction` 加权(Σ weight × direction_score)应与 `movement.direction` 大致对齐
- 例:沪深300 跌 1.2%,归因 `[(policy, weight=0.6, dir=down), (capital, weight=0.4, dir=down)]` → 加权方向 = down,匹配
- 若 5 档加权方向与 `movement.direction` 矛盾,提示归因有误,应在 summary 显式说明(避免静默错误)

---

## §4 输出样例(沪深 300 · 2026-09-15)

```json
{
  "asset": "000300.SH",
  "date": "2026-09-15",
  "movement": {
    "change_pct": -1.18,
    "direction": "down"
  },
  "buckets": [
    {
      "category": "overseas",
      "weight": 0.45,
      "confidence": 0.82,
      "direction": "down",
      "evidence": [
        {
          "text": "美国 8 月 CPI 同比 3.2%,高于市场预期 3.0%,9 月降息预期回落",
          "source": "Bloomberg",
          "timestamp": "2026-09-15T20:30:00+08:00"
        },
        {
          "text": "10Y 美债收益率上行 12bp 至 4.35%,美元指数升至 103.8",
          "source": "akshare:bond_zh_us_rate",
          "timestamp": "2026-09-15T23:00:00+08:00"
        }
      ]
    },
    {
      "category": "capital",
      "weight": 0.35,
      "confidence": 0.71,
      "direction": "down",
      "evidence": [
        {
          "text": "北向资金净流出 68 亿元,连续 3 日净流出",
          "source": "akshare:stock_hsgt_fund_flow_summary",
          "timestamp": "2026-09-15T15:00:00+08:00"
        }
      ]
    },
    {
      "category": "sentiment",
      "weight": 0.20,
      "confidence": 0.45,
      "direction": "down",
      "evidence": [
        {
          "text": "市场对国内 8 月经济数据预期偏弱,等待下周一发布",
          "source": "财新",
          "timestamp": "2026-09-15T18:00:00+08:00"
        }
      ]
    }
  ],
  "summary": "9 月 15 日沪深300 跌 1.18%,主因美 8 月 CPI 超预期推升美债利率 + 美元,北向资金连续 3 日净流出加剧跌幅;国内经济数据预期偏弱提供情绪背景。",
  "generated_at": "2026-09-15T23:30:00+08:00",
  "model": "claude-sonnet-4"
}
```

---

## §5 校验规则(用于 LLM 评测)

### 5.1 结构性校验(pydantic 即可)

| 规则 | 错误等级 |
|---|---|
| `Σ weight = 1.0`(±0.01) | ❌ 拒绝 |
| 至少 1 档 `weight ≥ 0.10` | ❌ 拒绝 |
| 每档至少 1 条 evidence | ❌ 拒绝 |
| `confidence ∈ [0, 1]` | ❌ 拒绝 |
| `summary` 30-200 字 | ⚠️ 警告 |
| `model` 非空 | ⚠️ 警告 |

### 5.2 语义性校验(LLM-as-judge,留 §5-4 实现)

| 规则 | 评分维度 |
|---|---|
| 5 档加权方向 ≈ `movement.direction` | 一致性(0/1) |
| evidence 原文可追溯、不是"市场认为" | 可信度(0-5) |
| `summary` 提到主导档位(weight 最高) | 完整性(0/1) |
| weight 分布符合典型形态(1-3 档显著) | 分布合理性(0-5) |
| 不出现幻觉(evidence 来源真实存在) | 真实性(0/1) |

### 5.3 失败兜底

- 结构校验失败 → 重新生成 1 次,仍失败 → 降级返回 `{asset, date, summary: "归因生成失败,请人工补充"}`
- 语义校验低分 → 在 `summary` 末尾追加 `⚠️ 本次归因置信度较低,建议交叉验证`

---

## §6 与其他模块的接口

```
┌─────────────────────────────────────────────────────────┐
│ §3 资产波动归因 MVP 流水线                                │
├─────────────────────────────────────────────────────────┤
│ [Input Layer]                                           │
│   • 资产列表(沪深300/国债/原油/USDJPY)                  │
│   • 当日行情(来自 §5-2 EconomyIngest · indicator_value)│
│   • 当日新闻/政策(来自 §5-3 政策文件库 + §3-1 事件库)    │
│                                                         │
│ [Attribution Engine]  ← 本 schema 落地                   │
│   • LLM(Claude Sonnet 4)按本 schema 输出                │
│   • pydantic 校验 + LLM-as-judge 评分                    │
│   • 通过 → 入库,失败 → 降级/重试                         │
│                                                         │
│ [Output Layer]                                          │
│   • 飞书 Agent:直接展示 summary + 5 档卡                │
│   • Web App:5 档权重柱状图 + evidence 卡片               │
│   • 评估:§5-4 评测数据集 + 基线准确率                    │
└─────────────────────────────────────────────────────────┘
```

---

## §7 局限与下一步

### 7.1 v0.1 已知局限

- 5 档是手动枚举,极端事件(自然灾害/战争)无独立档位,目前归 `overseas` 或 `sentiment` 的兜底
- `weight` 是 LLM 主观打分,缺乏客观锚定(无 Granger 因果/回归权重作 baseline)
- `evidence` 时效只到 timestamp,未做"近 24h / 48h / 1 周"衰减加权
- 跨资产传染(国债跌带动股票跌)未在 schema 中显式建模,只能靠 evidence 串接

### 7.2 演进路线

| 版本 | 增量 | 触发 |
|---|---|---|
| **v0.1(本次)** | 5 档 + weight/confidence/evidence + JSON Schema + 校验 | Phase 0 收尾 |
| v0.2 | + 跨日归因(过去 5 日累积归因) + 历史相似情境联动 | Phase 1 启动后 1 个月 |
| v0.3 | + 个股归因(对接 §3-2 财报数据) | Phase 1 中期 |
| v1.0 | + 客观权重校准(用历史归因准确率反推 LLM 偏差) | Phase 2 评测充分后 |

### 7.3 与 §5 其他主项的依赖

- **§5-2 行情数据**(5 指标已入库)→ ✅ 可用
- **§5-3 政策文件库**(50 份政策未入库)→ ⏳ evidence 来源会偏少,先靠 akshare/媒体原文顶
- **§5-4 LLM 基线评测**→ 依赖本 schema 作为"标准答案"格式
- **§5-5 Wind 合规 memo**→ 若 v0.2 引入 Wind 事件流,evidence 来源会更丰富

---

## 变更记录

| 时间 | 变更 | 触发 |
|------|------|------|
| 2026-08-31 03:10 | 完成归因 schema v0.1:5 档枚举 + weight/confidence/evidence 字段 + JSON Schema 草案 + 校验规则 + 输出样例 + 与 §3 流水线接口 | 每日 03:10 cron · 项目开发计划 §5-6 起步,§5-2 真实拉取连续 2 日卡 pip 升级,优先推进无外部依赖的 §5-6 |
