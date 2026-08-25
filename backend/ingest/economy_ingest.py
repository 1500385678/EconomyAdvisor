"""EconomyIngest:统一接入层的 SQLite schema 与 5 指标数据契约。

设计目标
--------
- 把 5 大官方宏观数据源(NBS / PBOC / MOF / GACC / MOFCOM)的指标落库口径统一到一个 SQLite 表
- 表结构在 `项目开发计划.md §4 技术架构` 的 EconomyIngest(table) 层
- 不依赖 akshare / pandas / numpy,只用 stdlib,便于任何环境先跑通 schema

两张表
------
1. `indicator` —— 指标字典
   - code(PK):指标代码,如 `NBS.GDP` / `PBOC.M2` / `PBOC.SHRZGM`
   - name_cn / name_en:中英文名
   - source:数据源(NBS / PBOC / MOF / GACC / MOFCOM)
   - freq:频率(D / W / M / Q / Y)
   - unit:单位(亿元 / % / 万吨)
   - akshare_fn:akshare 函数名(如 `macro_china_gdp`)
   - priority:P0 / P1 / P2

2. `indicator_value` —— 指标值
   - (indicator_code, period_date) 联合 PK
   - value:数值
   - yoy / mom:同比 / 环比(可空)
   - source_raw:原始来源(akshare / html / pdf / manual)
   - fetched_at:取数时间戳(ISO 8601)
   - note:备注

5 核心指标(对应 §5-2 Day 1 akshare 接入清单)
---------------------------------------------
| code          | name_cn     | source | freq | unit  | akshare_fn              |
|---------------|-------------|--------|------|-------|-------------------------|
| NBS.GDP       | GDP(国内生产总值)| NBS    | Q    | 亿元  | macro_china_gdp         |
| NBS.CPI       | CPI         | NBS    | M    | %     | macro_china_cpi         |
| NBS.PMI       | PMI(制造业)  | NBS    | M    | %     | macro_china_pmi         |
| PBOC.M2       | M2(货币供应) | PBOC   | M    | 亿元  | macro_china_m2           |
| PBOC.SHRZGM   | 社会融资规模 | PBOC   | M    | 亿元  | macro_china_shrzgm      |
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

# ---------------------------------------------------------------------------
# 5 核心指标字典
# ---------------------------------------------------------------------------

INDICATORS: list[dict] = [
    {
        "code": "NBS.GDP",
        "name_cn": "国内生产总值",
        "name_en": "Gross Domestic Product",
        "source": "NBS",
        "freq": "Q",
        "unit": "亿元",
        "akshare_fn": "macro_china_gdp",
        "priority": "P0",
    },
    {
        "code": "NBS.CPI",
        "name_cn": "居民消费价格指数(同比)",
        "name_en": "Consumer Price Index (YoY)",
        "source": "NBS",
        "freq": "M",
        "unit": "%",
        "akshare_fn": "macro_china_cpi",
        "priority": "P0",
    },
    {
        "code": "NBS.PMI",
        "name_cn": "制造业采购经理指数",
        "name_en": "Manufacturing PMI",
        "source": "NBS",
        "freq": "M",
        "unit": "%",
        "akshare_fn": "macro_china_pmi",
        "priority": "P0",
    },
    {
        "code": "PBOC.M2",
        "name_cn": "广义货币供应量 M2",
        "name_en": "Broad Money M2",
        "source": "PBOC",
        "freq": "M",
        "unit": "亿元",
        "akshare_fn": "macro_china_m2",
        "priority": "P0",
    },
    {
        "code": "PBOC.SHRZGM",
        "name_cn": "社会融资规模增量",
        "name_en": "Aggregate Financing to the Real Economy",
        "source": "PBOC",
        "freq": "M",
        "unit": "亿元",
        "akshare_fn": "macro_china_shrzgm",
        "priority": "P0",
    },
]

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

DDL_INDICATOR = """
CREATE TABLE IF NOT EXISTS indicator (
    code        TEXT PRIMARY KEY,
    name_cn     TEXT NOT NULL,
    name_en     TEXT NOT NULL,
    source      TEXT NOT NULL,
    freq        TEXT NOT NULL,
    unit        TEXT NOT NULL,
    akshare_fn  TEXT,
    priority    TEXT NOT NULL,
    first_seen  TEXT,
    last_seen   TEXT,
    created_at  TEXT NOT NULL
);
"""

DDL_INDICATOR_VALUE_TABLE = """
CREATE TABLE IF NOT EXISTS indicator_value (
    indicator_code  TEXT NOT NULL,
    period_date     TEXT NOT NULL,           -- ISO 8601 date (YYYY-MM-DD)
    value           REAL NOT NULL,
    yoy             REAL,
    mom             REAL,
    source_raw      TEXT NOT NULL,           -- akshare / html / pdf / manual / mock
    fetched_at      TEXT NOT NULL,           -- ISO 8601 datetime (UTC)
    note            TEXT,
    PRIMARY KEY (indicator_code, period_date),
    FOREIGN KEY (indicator_code) REFERENCES indicator(code)
);
"""

DDL_INDICATOR_VALUE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_iv_period ON indicator_value(period_date);",
    "CREATE INDEX IF NOT EXISTS idx_iv_code_period ON indicator_value(indicator_code, period_date);",
]


# ---------------------------------------------------------------------------
# 数据契约(给 probe / adapter 复用)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorValue:
    """一条指标值记录(送入 upsert_value)。"""

    indicator_code: str
    period_date: str          # YYYY-MM-DD
    value: float
    yoy: float | None = None
    mom: float | None = None
    source_raw: str = "manual"
    note: str | None = None


# ---------------------------------------------------------------------------
# 初始化 / 连接
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def connect(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """上下文管理 SQLite 连接,自动 commit / close。"""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str | Path) -> None:
    """初始化 schema + 写入 5 核心指标字典(若已存在则更新 last_seen)。"""
    with connect(db_path) as conn:
        conn.execute(DDL_INDICATOR)
        conn.execute(DDL_INDICATOR_VALUE_TABLE)
        for ddl in DDL_INDICATOR_VALUE_INDEXES:
            conn.execute(ddl)
        now = _now_iso()
        for ind in INDICATORS:
            conn.execute(
                """
                INSERT INTO indicator (code, name_cn, name_en, source, freq, unit,
                                       akshare_fn, priority, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name_cn = excluded.name_cn,
                    name_en = excluded.name_en,
                    source  = excluded.source,
                    freq    = excluded.freq,
                    unit    = excluded.unit,
                    akshare_fn = excluded.akshare_fn,
                    priority = excluded.priority
                """,
                (
                    ind["code"], ind["name_cn"], ind["name_en"], ind["source"],
                    ind["freq"], ind["unit"], ind["akshare_fn"], ind["priority"],
                    now,
                ),
            )


def upsert_value(db_path: str | Path, rec: IndicatorValue) -> None:
    """写入或更新一条指标值。"""
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO indicator_value
                (indicator_code, period_date, value, yoy, mom, source_raw, fetched_at, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(indicator_code, period_date) DO UPDATE SET
                value       = excluded.value,
                yoy         = excluded.yoy,
                mom         = excluded.mom,
                source_raw  = excluded.source_raw,
                fetched_at  = excluded.fetched_at,
                note        = excluded.note
            """,
            (
                rec.indicator_code, rec.period_date, rec.value,
                rec.yoy, rec.mom, rec.source_raw, _now_iso(), rec.note,
            ),
        )
        # 同步更新 indicator.last_seen
        conn.execute(
            "UPDATE indicator SET last_seen = ? WHERE code = ?",
            (rec.period_date, rec.indicator_code),
        )


def upsert_many(db_path: str | Path, records: Iterable[IndicatorValue]) -> int:
    """批量 upsert,返回成功条数。"""
    n = 0
    with connect(db_path) as conn:
        for rec in records:
            conn.execute(
                """
                INSERT INTO indicator_value
                    (indicator_code, period_date, value, yoy, mom, source_raw, fetched_at, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(indicator_code, period_date) DO UPDATE SET
                    value       = excluded.value,
                    yoy         = excluded.yoy,
                    mom         = excluded.mom,
                    source_raw  = excluded.source_raw,
                    fetched_at  = excluded.fetched_at,
                    note        = excluded.note
                """,
                (
                    rec.indicator_code, rec.period_date, rec.value,
                    rec.yoy, rec.mom, rec.source_raw, _now_iso(), rec.note,
                ),
            )
            conn.execute(
                "UPDATE indicator SET last_seen = ? WHERE code = ?",
                (rec.period_date, rec.indicator_code),
            )
            n += 1
    return n


def list_indicators(db_path: str | Path) -> list[dict]:
    """列出所有指标字典(给 CLI / dashboard 用)。"""
    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT code, name_cn, name_en, source, freq, unit, akshare_fn, "
            "priority, first_seen, last_seen FROM indicator ORDER BY priority, code"
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def count_values(db_path: str | Path) -> dict[str, int]:
    """返回每个指标已落库的值条数(给 probe 自检用)。"""
    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT indicator_code, COUNT(*) FROM indicator_value GROUP BY indicator_code"
        )
        return {code: cnt for code, cnt in cur.fetchall()}


__all__ = [
    "INDICATORS",
    "IndicatorValue",
    "connect",
    "init_db",
    "upsert_value",
    "upsert_many",
    "list_indicators",
    "count_values",
]
