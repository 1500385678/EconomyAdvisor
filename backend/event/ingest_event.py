"""ingest_event:事件库人工录入 CLI。

用法
----
单条录入(交互式):
    python3 -m backend.event.ingest_event add \\
        --date 2024-09-24 \\
        --category policy-monetary \\
        --title "央行宣布降准 0.5pct + 降息 20bp" \\
        --summary "中国人民银行决定下调金融机构存款准备金率 0.5pct,7 天逆回购利率下调 20bp" \\
        --source "央行" --url "http://www.pbc.gov.cn/" \\
        --tags "降准 降息 逆回购"

单条录入(从 JSON):
    python3 -m backend.event.ingest_event add-json --file one_event.json

批量录入(从 JSON 数组):
    python3 -m backend.event.ingest_event batch --file events.jsonl

列出最近 10 条:
    python3 -m backend.event.ingest_event list --limit 10
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from .event_schema import (
    CATEGORIES,
    CATEGORY_CODES,
    DEFAULT_DB_PATH,
    RELATION_TYPES,
    TAG_DICTIONARY,
    TAG_SET,
    connect,
    init_schema,
    now_iso,
)


# ---------------------------------------------------------------------------
# 业务校验
# ---------------------------------------------------------------------------

class EventValidationError(ValueError):
    """录入数据不合规。"""


def _validate_category(category: str) -> None:
    if category not in CATEGORY_CODES:
        raise EventValidationError(
            f"category={category!r} 不在 8 大类内,可选: {sorted(CATEGORY_CODES)}"
        )


def _validate_tags(tags: list[str]) -> list[str]:
    """对 tag 做白名单校验,不在 §3.3 词典的拒绝。"""
    unknown = [t for t in tags if t not in TAG_SET]
    if unknown:
        raise EventValidationError(
            f"tag 不在 §3.3 起步词典({len(TAG_SET)} 个): {unknown}\n"
            f"  如必须新增词典外 tag,请先在 `event_schema.TAG_DICTIONARY` 注册"
        )
    # 去重保序
    seen: set[str] = set()
    deduped: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    return deduped


def _validate_event_date(s: str) -> str:
    """YYYY-MM-DD 校验,失败抛 EventValidationError。"""
    try:
        date.fromisoformat(s)
    except ValueError as e:
        raise EventValidationError(f"event_date={s!r} 不是 YYYY-MM-DD: {e}") from None
    return s


def _validate_impact_score(n: int | None) -> int | None:
    if n is None:
        return None
    if not (1 <= n <= 5):
        raise EventValidationError(f"impact_score={n} 超出 1-5 范围")
    return n


# ---------------------------------------------------------------------------
# 单条入库
# ---------------------------------------------------------------------------

def add_event(
    *,
    event_date: str,
    category: str,
    title_cn: str,
    title_en: str | None = None,
    summary: str | None = None,
    source_url: str | None = None,
    source_org: str | None = None,
    impact_score: int | None = None,
    playbook_id: str | None = None,
    tags: list[str] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """插入 1 条事件 + 0..N 个 tag。返回 dict(包含新 id)。"""
    if not title_cn or len(title_cn) > 40:
        raise EventValidationError(
            f"title_cn 必填且 <= 40 字,当前 {len(title_cn or '')} 字"
        )
    _validate_event_date(event_date)
    _validate_category(category)
    _validate_impact_score(impact_score)
    cleaned_tags = _validate_tags(tags or [])

    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO event (
                event_code, event_date, category, title_cn, title_en, summary,
                source_url, source_org, impact_score, playbook_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _make_event_code(event_date, category, conn),
                event_date,
                category,
                title_cn,
                title_en,
                summary,
                source_url,
                source_org,
                impact_score,
                playbook_id,
                now_iso(),
                now_iso(),
            ),
        )
        new_id = cur.lastrowid
        for tag in cleaned_tags:
            conn.execute(
                "INSERT OR IGNORE INTO event_tag (event_id, tag) VALUES (?, ?)",
                (new_id, tag),
            )

    return {
        "id": new_id,
        "event_date": event_date,
        "category": category,
        "title_cn": title_cn,
        "tags": cleaned_tags,
    }


def _make_event_code(event_date: str, category: str, conn) -> str:
    """生成 `EVT-YYYY-MM-DD-NNN` 业务码,同日期按 category 前缀 + 序号。"""
    # 简化:直接 event_date + 同日 count + 001
    cur = conn.execute(
        "SELECT COUNT(*) AS n FROM event WHERE event_date = ?", (event_date,)
    )
    n = cur.fetchone()["n"] + 1
    return f"EVT-{event_date}-{n:03d}"


# ---------------------------------------------------------------------------
# 关系录入(Phase 1 再用,先占位)
# ---------------------------------------------------------------------------

def add_relation(
    *,
    from_event_id: int,
    to_event_id: int | None = None,
    to_indicator_code: str | None = None,
    relation_type: str,
    weight: float = 1.0,
    db_path: str | Path | None = None,
) -> int:
    """事件↔事件 / 事件↔指标 关系。Phase 1 相似度算法主用。"""
    if relation_type not in RELATION_TYPES:
        raise EventValidationError(
            f"relation_type={relation_type!r} 不在 {sorted(RELATION_TYPES)}"
        )
    if to_event_id is None and to_indicator_code is None:
        raise EventValidationError("to_event_id 与 to_indicator_code 必须二选一")
    if to_event_id is not None and to_indicator_code is not None:
        raise EventValidationError("to_event_id 与 to_indicator_code 互斥,只能填一个")
    if not (0.0 <= weight <= 1.0):
        raise EventValidationError(f"weight={weight} 超出 0-1 范围")

    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO event_relation (
                from_event_id, to_event_id, to_indicator_code, relation_type, weight
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (from_event_id, to_event_id, to_indicator_code, relation_type, weight),
        )
        return cur.lastrowid


# ---------------------------------------------------------------------------
# 列表
# ---------------------------------------------------------------------------

def list_recent(
    *,
    limit: int = 10,
    category: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """按 event_date DESC 列出最近 N 条;可选 category 过滤。"""
    sql = "SELECT id, event_code, event_date, category, title_cn FROM event"
    params: list[Any] = []
    if category:
        sql += " WHERE category = ?"
        params.append(category)
    sql += " ORDER BY event_date DESC, id DESC LIMIT ?"
    params.append(limit)
    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 统计(8 大类 / 30 tag 词典 / DB 现状)
# ---------------------------------------------------------------------------

def stats_by_category(*, db_path: str | Path | None = None) -> dict[str, Any]:
    """统计 8 大类当前条数 + Phase 0 目标缺额 + 30 tag 词典使用频次 + DB 现状。

    返回结构
    --------
    {
        "db_path": "<绝对路径>",
        "db_size_bytes": <int>,
        "total_event": <int>,
        "total_event_tag": <int>,
        "total_event_relation": <int>,
        "target_sum": 100,
        "by_category": [
            {"category": "policy-monetary", "name_cn": "货币政策",
             "current": <int>, "target": 12, "gap": <int>},
            ...
            # 8 大类全列,按 CATEGORIES 顺序
        ],
        "tag_usage": {
            "词典内已用": <int>, "词典内未用": <int>,
            "词典外使用": <int>,  # event_tag.tag 不在 TAG_SET 的数量
            "top10_used": [{"tag": ..., "count": ...}, ...]
        }
    }
    """
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    # DB 体积(文件不存在则 0)
    db_size = path.stat().st_size if path.exists() else 0

    with connect(path) as conn:
        total_event = conn.execute("SELECT COUNT(*) AS n FROM event").fetchone()["n"]
        total_event_tag = conn.execute("SELECT COUNT(*) AS n FROM event_tag").fetchone()["n"]
        total_event_relation = conn.execute("SELECT COUNT(*) AS n FROM event_relation").fetchone()["n"]

        # 8 大类当前数(LEFT JOIN 保证未用大类也出现,current=0)
        by_cat: list[dict[str, Any]] = []
        for code, name_cn, target in CATEGORIES:
            cur = conn.execute(
                "SELECT COUNT(*) AS n FROM event WHERE category = ?", (code,)
            ).fetchone()["n"]
            by_cat.append({
                "category": code,
                "name_cn": name_cn,
                "current": cur,
                "target": target,
                "gap": max(target - cur, 0),
            })

        # tag 词典使用频次
        used_rows = conn.execute(
            """
            SELECT tag, COUNT(*) AS n FROM event_tag
            GROUP BY tag ORDER BY n DESC
            """
        ).fetchall()
        used_tags = {r["tag"]: r["n"] for r in used_rows}
        in_dict_used = sum(n for t, n in used_tags.items() if t in TAG_SET)
        in_dict_unused = len(TAG_SET) - sum(1 for t in TAG_SET if t in used_tags)
        out_of_dict = sum(n for t, n in used_tags.items() if t not in TAG_SET)
        top10 = [{"tag": r["tag"], "count": r["n"]} for r in used_rows[:10]]

    return {
        "db_path": str(path),
        "db_size_bytes": db_size,
        "total_event": total_event,
        "total_event_tag": total_event_tag,
        "total_event_relation": total_event_relation,
        "target_sum": sum(n for _, _, n in CATEGORIES),
        "by_category": by_cat,
        "tag_usage": {
            "in_dict_used": in_dict_used,
            "in_dict_unused": in_dict_unused,
            "out_of_dict_count": out_of_dict,
            "top10_used": top10,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ingest_event",
        description="EconomyAdvisor 事件库录入 CLI",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="命令行参数单条录入")
    p_add.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_add.add_argument("--category", required=True, help="8 大类之一")
    p_add.add_argument("--title", required=True, help="中文标题 <= 40 字")
    p_add.add_argument("--title-en", default=None)
    p_add.add_argument("--summary", default=None)
    p_add.add_argument("--url", default=None)
    p_add.add_argument("--source", default=None)
    p_add.add_argument("--impact", type=int, default=None, help="1-5 主观分")
    p_add.add_argument("--playbook", default=None)
    p_add.add_argument("--tags", nargs="*", default=[], help="空格分隔,白名单校验")
    p_add.add_argument("--db", default=None)

    p_json = sub.add_parser("add-json", help="从 JSON 文件单条录入")
    p_json.add_argument("--file", required=True)
    p_json.add_argument("--db", default=None)

    p_batch = sub.add_parser("batch", help="批量 JSONL 录入")
    p_batch.add_argument("--file", required=True)
    p_batch.add_argument("--db", default=None)

    p_list = sub.add_parser("list", help="列出最近 N 条")
    p_list.add_argument("--limit", type=int, default=10)
    p_list.add_argument("--category", default=None)
    p_list.add_argument("--db", default=None)

    p_init = sub.add_parser("init", help="仅建表(幂等)")
    p_init.add_argument("--db", default=None)

    p_stats = sub.add_parser("stats", help="统计 8 大类进度 + 30 tag 词典使用频次 + DB 现状")
    p_stats.add_argument("--db", default=None)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    # init 永远先跑一次,确保 3 表存在
    if args.cmd != "init":
        init_schema(getattr(args, "db", None))

    if args.cmd == "add":
        result = add_event(
            event_date=args.date,
            category=args.category,
            title_cn=args.title,
            title_en=args.title_en,
            summary=args.summary,
            source_url=args.url,
            source_org=args.source,
            impact_score=args.impact,
            playbook_id=args.playbook,
            tags=args.tags,
            db_path=args.db,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "add-json":
        with open(args.file, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = add_event(db_path=args.db, **data)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "batch":
        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        with open(args.file, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(add_event(db_path=args.db, **json.loads(line)))
                except (EventValidationError, sqlite3_error_factory()) as e:
                    errors.append({"line": i, "error": str(e)})
        print(json.dumps({"ok": len(results), "fail": len(errors), "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if not errors else 1

    if args.cmd == "list":
        rows = list_recent(limit=args.limit, category=args.category, db_path=args.db)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "init":
        ddl_lines = init_schema(args.db)
        for line in ddl_lines:
            print(f"  ✓ {line}")
        print(f"DB: {args.db or DEFAULT_DB_PATH}")
        return 0

    if args.cmd == "stats":
        result = stats_by_category(db_path=args.db)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    return 1


def sqlite3_error_factory():
    """避免顶部 import sqlite3,运行时再读;仅供 batch 段异常类型用。"""
    import sqlite3
    return sqlite3.Error


if __name__ == "__main__":
    sys.exit(main())
