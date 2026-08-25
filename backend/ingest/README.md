---
tags:
  - phase-0
  - data-source
  - ingest
  - akshare
created: 2026-08-26
updated: 2026-08-26
---

# backend/ingest · 宏观数据接入层

> 对应 `项目开发计划.md §5-2` 跑通 5 大免费宏观数据源 + `docs/phase-0-data-source-catalog-v0.1.md §6.3 Day 1`。

## 0. 当前阶段

- 起步(2026-08-26):固化 EconomyIngest SQLite schema + 5 核心指标数据契约 + probe 入口
- 真实 akshare 接入:§5-2 Day 1(本周内)
- 5 源端到端:§5-2 Day 5(2026-08-30)

## 1. 文件清单

| 文件 | 作用 |
|---|---|
| `economy_ingest.py` | SQLite schema(`indicator` + `indicator_value`)+ 5 指标字典 + upsert / list / count 接口 |
| `probe_akshare_5indicators.py` | probe CLI:akshare 不可用时落 mock,验证 schema 与数据契约 |
| `data/economy_ingest.db` | SQLite 落库(运行时生成,不入 git) |

## 2. 5 核心指标(对应 §5-2 Day 1)

| code | name_cn | source | freq | unit | akshare_fn |
|---|---|---|---|---|---|
| `NBS.GDP` | 国内生产总值 | NBS | Q | 亿元 | `macro_china_gdp` |
| `NBS.CPI` | 居民消费价格指数(同比) | NBS | M | % | `macro_china_cpi` |
| `NBS.PMI` | 制造业采购经理指数 | NBS | M | % | `macro_china_pmi` |
| `PBOC.M2` | 广义货币供应量 M2 | PBOC | M | 亿元 | `macro_china_m2` |
| `PBOC.SHRZGM` | 社会融资规模增量 | PBOC | M | 亿元 | `macro_china_shrzgm` |

## 3. Schema(简版)

```sql
CREATE TABLE indicator (
    code TEXT PRIMARY KEY,
    name_cn TEXT NOT NULL,
    name_en TEXT NOT NULL,
    source TEXT NOT NULL,        -- NBS / PBOC / MOF / GACC / MOFCOM
    freq TEXT NOT NULL,           -- D / W / M / Q / Y
    unit TEXT NOT NULL,
    akshare_fn TEXT,
    priority TEXT NOT NULL,       -- P0 / P1 / P2
    first_seen TEXT,
    last_seen TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE indicator_value (
    indicator_code TEXT NOT NULL,
    period_date TEXT NOT NULL,    -- YYYY-MM-DD
    value REAL NOT NULL,
    yoy REAL,
    mom REAL,
    source_raw TEXT NOT NULL,     -- akshare / html / pdf / manual / mock
    fetched_at TEXT NOT NULL,     -- ISO 8601 UTC
    note TEXT,
    PRIMARY KEY (indicator_code, period_date)
);
```

## 4. 使用

### 4.1 跑 probe(落库 + 报告)

```bash
cd /Users/aaron/Mac/Consultant/20-经济-Economy/_EconomyLib/EconomyWeb
python3 backend/ingest/probe_akshare_5indicators.py --db data/economy_ingest.db
```

- 默认 `--allow-mock` 开启:akshare 拉取失败时落 mock 数据并在 stderr 打印原因
- `--no-mock`:akshare 拉取失败时跳过该指标

### 4.2 在 Python 里复用

```python
from backend.ingest.economy_ingest import (
    init_db, upsert_value, list_indicators, count_values,
    INDICATORS, IndicatorValue,
)

init_db("data/economy_ingest.db")
upsert_value("data/economy_ingest.db",
    IndicatorValue(indicator_code="NBS.CPI", period_date="2026-07-31",
                   value=0.2, yoy=0.2, mom=0.1, source_raw="akshare"))
print(list_indicators("data/economy_ingest.db"))
print(count_values("data/economy_ingest.db"))
```

## 5. 已知约束与下一步

### 5.1 已验证(2026-08-26)

- ✅ stdlib only:`economy_ingest.py` 不依赖 akshare / pandas / numpy,Python 3.9 系统 pip 21.2 下可跑
- ✅ schema 落库 + 5 指标 mock 落库:probe 跑通,SQLite 文件 `data/economy_ingest.db` 生成

### 5.2 未做(等 §5-2 Day 1 装 akshare 后)

- ⏳ `_fetch_via_akshare` 真实 DataFrame → IndicatorValue 转换
- ⏳ PBOC 公开市场操作每日 HTML 解析(Day 2)
- ⏳ NBS 直抓降级路径验证(Day 3)
- ⏳ 5 源 → EconomyIngest → 后续 ClickHouse 端到端(Day 5)

### 5.3 暂时性折中

- 当前用 `source_raw='mock'` 的 5 条最新期数据,**数值参考 Daily/20-经济-Economy-日报-20260823/24.md**;akshare 真实接入时这 5 条会被覆盖

## 6. 关联文档

- `项目开发计划.md §5-2` 跑通 5 大免费宏观数据源
- `docs/phase-0-data-source-catalog-v0.1.md` 5 大源接入清单(本模块的施工图)
- `.plan/20260824-inspiration-index.md` 指标/政策/事件/资产四类索引(IND-01 指标库底座)
- `Logs/巡检-经济-20260826.md` 巡检建议:本模块是 §5-2 启动基线

## 变更记录

| 时间 | 变更 | 触发 |
|---|---|---|
| 2026-08-26 03:15 | 起步:EconomyIngest schema + 5 指标字典 + probe CLI(akshare 不可用时 mock 落库) | 每日 03:10 cron · 项目开发计划 §5-2 起步 |
