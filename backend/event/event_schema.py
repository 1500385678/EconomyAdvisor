"""EventSchema:历史事件库 v0.1 的 SQLite 建表 + 字典常量 + 连接 helper。

设计目标
--------
- 三张表:`event` 主表 / `event_tag` 多对多标签 / `event_relation` 事件↔事件 或 事件↔指标
- 与 `economy_ingest.indicator` 同库 `data/economy_ingest.db`,便于跨表 JOIN
- 不依赖任何第三方包,只用 stdlib,任何环境先跑通 schema

8 大类(§3.1)
-------------
policy-monetary / policy-fiscal / policy-regulatory / data-release /
market-shock / global-event / industry-event / structural

30 tag 起步词典(§3.3,Phase 0 期间滚动扩到 80)
-------------------------------------------
货币政策 8 / 财政政策 4 / 监管政策 6 / 市场异动 6 / 海外 4 / 数据 2

关系类型(§2.3)
--------------
cause / followup / similar / related,带 weight 0-1
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

# ---------------------------------------------------------------------------
# 路径常量(与 backend/ingest/economy_ingest.py 保持一致)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "economy_ingest.db"


# ---------------------------------------------------------------------------
# 8 大类(§3.1) + 目标条数
# ---------------------------------------------------------------------------

CATEGORIES: list[tuple[str, str, int]] = [
    # (code, 中文名, Phase 0 目标条数)
    ("policy-monetary", "货币政策", 12),
    ("policy-fiscal", "财政政策", 8),
    ("policy-regulatory", "监管政策", 10),
    ("data-release", "关键数据公布", 20),
    ("market-shock", "市场异动", 15),
    ("global-event", "海外事件", 20),
    ("industry-event", "行业事件", 10),
    ("structural", "结构性事件", 5),
]
CATEGORY_CODES: set[str] = {code for code, _, _ in CATEGORIES}
CATEGORY_TARGET_SUM: int = sum(n for _, _, n in CATEGORIES)  # = 100

# ---------------------------------------------------------------------------
# 30 tag 起步词典(§3.3)
# ---------------------------------------------------------------------------

TAG_DICTIONARY: list[tuple[str, str]] = [
    # (tag, 适用大类)
    # 货币政策 8
    ("降息", "policy-monetary"),
    ("降准", "policy-monetary"),
    ("LPR 调降", "policy-monetary"),
    ("MLF 续作", "policy-monetary"),
    ("逆回购", "policy-monetary"),
    ("再贷款", "policy-monetary"),
    ("PSL", "policy-monetary"),
    ("结构性工具", "policy-monetary"),
    # 财政政策 4
    ("专项债", "policy-fiscal"),
    ("特别国债", "policy-fiscal"),
    ("减税降费", "policy-fiscal"),
    ("赤字率", "policy-fiscal"),
    # 监管政策 6
    ("资管新规", "policy-regulatory"),
    ("房地产三支箭", "policy-regulatory"),
    ("平台经济", "policy-regulatory"),
    ("注册制", "policy-regulatory"),
    ("退市新规", "policy-regulatory"),
    ("减持新规", "policy-regulatory"),
    # 市场异动 6
    ("股灾", "market-shock"),
    ("债灾", "market-shock"),
    ("汇市闪崩", "market-shock"),
    ("商品暴跌", "market-shock"),
    ("流动性危机", "market-shock"),
    ("信用违约", "market-shock"),
    # 海外 4
    ("美联储加息", "global-event"),
    ("美联储降息", "global-event"),
    ("欧债危机", "global-event"),
    ("中美贸易摩擦", "global-event"),
    # 数据 2
    ("GDP 超预期", "data-release"),
    ("CPI 超预期", "data-release"),
]
TAG_SET: set[str] = {tag for tag, _ in TAG_DICTIONARY}

# ---------------------------------------------------------------------------
# 关系类型枚举(§2.3)
# ---------------------------------------------------------------------------

RELATION_TYPES: set[str] = {"cause", "followup", "similar", "related"}


# ---------------------------------------------------------------------------
# DDL(§2.1-2.3)
# ---------------------------------------------------------------------------

_DDL_STATEMENTS: list[str] = [
    # event 主表
    """
    CREATE TABLE IF NOT EXISTS event (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        event_code      TEXT UNIQUE NOT NULL,
        event_date      TEXT NOT NULL,
        category        TEXT NOT NULL,
        title_cn        TEXT NOT NULL,
        title_en        TEXT,
        summary         TEXT,
        source_url      TEXT,
        source_org      TEXT,
        impact_score    INTEGER,
        playbook_id     TEXT,
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # event_date / category / playbook_id 索引
    "CREATE INDEX IF NOT EXISTS idx_event_date ON event(event_date)",
    "CREATE INDEX IF NOT EXISTS idx_event_category ON event(category)",
    "CREATE INDEX IF NOT EXISTS idx_event_playbook ON event(playbook_id)",
    # event_tag 多对多
    """
    CREATE TABLE IF NOT EXISTS event_tag (
        event_id    INTEGER NOT NULL,
        tag         TEXT NOT NULL,
        PRIMARY KEY (event_id, tag),
        FOREIGN KEY (event_id) REFERENCES event(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_event_tag_tag ON event_tag(tag)",
    # event_relation
    """
    CREATE TABLE IF NOT EXISTS event_relation (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        from_event_id       INTEGER NOT NULL,
        to_event_id         INTEGER,
        to_indicator_code   TEXT,
        relation_type       TEXT NOT NULL,
        weight              REAL DEFAULT 1.0,
        FOREIGN KEY (from_event_id) REFERENCES event(id) ON DELETE CASCADE,
        FOREIGN KEY (to_event_id) REFERENCES event(id) ON DELETE CASCADE,
        FOREIGN KEY (to_indicator_code) REFERENCES indicator(code)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_er_from ON event_relation(from_event_id)",
    "CREATE INDEX IF NOT EXISTS idx_er_to_event ON event_relation(to_event_id)",
    "CREATE INDEX IF NOT EXISTS idx_er_to_ind ON event_relation(to_indicator_code)",
]


# ---------------------------------------------------------------------------
# 连接 helper(与 ingest.economy_ingest.connect() 同款)
# ---------------------------------------------------------------------------

@contextmanager
def connect(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """打开 SQLite 连接,自动 close,Row 工厂。"""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(db_path: str | Path | None = None) -> list[str]:
    """幂等建表:3 张表 + 6 索引。返回已执行的 DDL 列表(供自检)。"""
    with connect(db_path) as conn:
        for ddl in _DDL_STATEMENTS:
            conn.execute(ddl)
    return [_ddl_one_liner(d) for d in _DDL_STATEMENTS]


def _ddl_one_liner(ddl: str) -> str:
    """把 DDL 折成首行预览,避免日志噪音。"""
    return " ".join(ddl.split())[:80]


def now_iso() -> str:
    """UTC ISO 8601,秒精度。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
