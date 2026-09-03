# backend/event · 事件库落地层

> Phase 0 §5 事件库 v0.1 代码实现
> 对应设计:`../docs/phase-0-event-library-design-v0.1.md`(2026-09-03)

## 4 个文件

| 文件 | 职责 |
|---|---|
| `__init__.py` | 子包 docstring |
| `event_schema.py` | DDL + 8 大类 + 30 tag 词典 + 关系枚举 + `init_schema()` + `connect()` |
| `ingest_event.py` | 录入 CLI(`add` / `add-json` / `batch` / `list` / `init`) |
| `self_test_event.py` | 5 步自检(DDL 幂等 / 插入 / 标签白名单 / 列表 / 关系) |

## 三张表(同 `data/economy_ingest.db`)

- `event` —— 主表
- `event_tag` —— 多对多标签
- `event_relation` —— 事件↔事件 / 事件↔指标

## 5 大类、30 tag 起步词典、4 关系类型

- 8 大类见 `event_schema.CATEGORIES`(总目标 100 条)
- 30 tag 见 `event_schema.TAG_DICTIONARY`(Phase 0 期间滚动扩到 80)
- 4 关系:`cause` / `followup` / `similar` / `related`

## CLI 用法

```bash
# 1) 初始化(幂等,任何 cmd 都会先跑一次)
python3 -m backend.event.ingest_event init

# 2) 单条录入(命令行参数)
python3 -m backend.event.ingest_event add \
  --date 2024-09-24 \
  --category policy-monetary \
  --title "央行宣布降准 0.5pct + 降息 20bp" \
  --summary "..." \
  --source "央行" --url "http://www.pbc.gov.cn/" \
  --tags "降准 降息 逆回购"

# 3) 单条 JSON
python3 -m backend.event.ingest_event add-json --file one.json

# 4) 批量 JSONL
python3 -m backend.event.ingest_event batch --file events.jsonl

# 5) 列最近 10 条
python3 -m backend.event.ingest_event list --limit 10
```

## 自检

```bash
python3 backend/event/self_test_event.py
# 期望:=== 5/5 PASS ===
```

## 与 §5 归因 schema 的关系

| 归因档位 | 事件库对应字段 |
|---|---|
| 政策 | `event.category in policy-*` |
| 资金 | `event.tag` 含 `流动性` / `MLF` / `降准` / `社融` |
| 海外 | `event.category = global-event` |
| 情绪 | `event.tag` 含 `恐慌` / `VIX` / `北向资金` |
| 技术 | 不在事件库,归因时单独算 |

> 即:归因 schema 是"对当下资产波动的解释",事件库是"对历史上发生过的同类事情的记忆"。
> 两者通过 `playbook_id` 关联,Phase 1 再打通。
