"""self_test_event:事件库 6 步自检。

每步必须 PASS,任一 FAIL 立即 raise。退出码:0=PASS / 1=FAIL。

6 步
----
T1 DDL 幂等:init_schema() 跑 2 次不报错,3 张表都存在
T2 单条插入:add_event() 1 条,返回 dict 含新 id
T3 标签白名单:tag 在 §3.3 词典 → PASS;tag 不在 → EventValidationError
T4 列表查询:list_recent(limit=2) 返回最近 2 条,按 event_date DESC
T5 关系录入:add_relation() 事件↔事件 + 事件↔指标 各 1 条,互斥校验
T6 统计输出:stats_by_category() 返回 8 大类齐全 + 目标 100 + tag_usage 字典齐全
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# 让 `python3 backend/event/self_test_event.py` 也能跑
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.event.event_schema import (  # noqa: E402
    CATEGORIES,
    CATEGORY_CODES,
    CATEGORY_TARGET_SUM,
    DEFAULT_DB_PATH,
    RELATION_TYPES,
    TAG_DICTIONARY,
    TAG_SET,
    connect,
    init_schema,
)
from backend.event.ingest_event import (  # noqa: E402
    EventValidationError,
    add_event,
    add_relation,
    list_recent,
    stats_by_category,
)


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")
    raise SystemExit(1)


def t1_ddl_idempotent(tmp_db: Path) -> None:
    print("T1 DDL 幂等")
    init_schema(tmp_db)  # 1st
    init_schema(tmp_db)  # 2nd
    with connect(tmp_db) as conn:
        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    expected = {"event", "event_tag", "event_relation"}
    if not expected.issubset(tables):
        _fail(f"缺表: 实际 {tables & expected}, 缺 {expected - tables}")
    _ok(f"3 表都在: {sorted(expected & tables)}")


def t2_single_insert(tmp_db: Path) -> int:
    print("T2 单条插入")
    if len(CATEGORY_CODES) != 8:
        _fail(f"8 大类应 = 8, 实际 {len(CATEGORY_CODES)}")
    if CATEGORY_TARGET_SUM != 100:
        _fail(f"100 事件目标应 = 100, 实际 {CATEGORY_TARGET_SUM}")
    if len(TAG_SET) != 30:
        _fail(f"§3.3 起步词典应 = 30, 实际 {len(TAG_SET)}")
    if len(RELATION_TYPES) != 4:
        _fail(f"关系类型应 = 4, 实际 {len(RELATION_TYPES)}")

    result = add_event(
        event_date="2024-09-24",
        category="policy-monetary",
        title_cn="央行宣布降准 0.5pct + 降息 20bp",
        summary="中国人民银行下调存款准备金率 0.5pct,7 天逆回购利率下调 20bp",
        source_org="央行",
        source_url="http://www.pbc.gov.cn/",
        impact_score=5,
        tags=["降准", "降息", "逆回购"],
        db_path=tmp_db,
    )
    if not result.get("id"):
        _fail("返回 dict 缺 id")
    if result["tags"] != ["降准", "降息", "逆回购"]:
        _fail(f"tags 去重保序失败: {result['tags']}")
    _ok(f"event_id={result['id']}, event_code 含 EVT-2024-09-24 前缀")
    return result["id"]


def t3_tag_whitelist(tmp_db: Path) -> None:
    print("T3 标签白名单")
    # 在词典内 → OK
    add_event(
        event_date="2024-10-01",
        category="global-event",
        title_cn="美联储 9 月议息降息 50bp",
        tags=["美联储降息"],
        db_path=tmp_db,
    )
    _ok("词典内 tag '美联储降息' PASS")
    # 不在词典 → 抛 EventValidationError
    try:
        add_event(
            event_date="2024-10-02",
            category="global-event",
            title_cn="测试 tag 拒绝",
            tags=["不存在的 tag"],
            db_path=tmp_db,
        )
    except EventValidationError as e:
        if "不存在的 tag" not in str(e):
            _fail(f"错误信息应包含 '不存在的 tag': {e}")
        _ok(f"词典外 tag 被拒: {e!s:.50}...")
    else:
        _fail("词典外 tag 应抛 EventValidationError,但没抛")


def t4_list_recent(tmp_db: Path) -> None:
    print("T4 列表查询")
    rows = list_recent(limit=2, db_path=tmp_db)
    if len(rows) != 2:
        _fail(f"应返回 2 条,实际 {len(rows)}")
    # 第二条插入日期更晚,应排第一
    if rows[0]["event_date"] != "2024-10-01":
        _fail(f"最近一条 event_date 应 = 2024-10-01, 实际 {rows[0]['event_date']}")
    _ok(f"最近 2 条: {[(r['event_date'], r['category']) for r in rows]}")


def t5_relation(tmp_db: Path) -> None:
    print("T5 关系录入")
    # event_relation.to_indicator_code 有外键→indicator.code,临时 DB 要先建 indicator 表
    from backend.ingest.economy_ingest import init_db as init_ingest_db
    init_ingest_db(tmp_db)
    with connect(tmp_db) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO indicator (
                code, name_cn, name_en, source, freq, unit, priority, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "NBS.GDP", "国内生产总值", "GDP", "NBS", "Q", "亿元", "P0",
                "2026-09-04T00:00:00Z",
            ),
        )
    eid_1 = add_event(
        event_date="2024-09-24",
        category="policy-monetary",
        title_cn="测试关系-事件 A",
        db_path=tmp_db,
    )["id"]
    eid_2 = add_event(
        event_date="2024-10-15",
        category="data-release",
        title_cn="测试关系-事件 B",
        db_path=tmp_db,
    )["id"]

    # 事件↔事件
    rid_1 = add_relation(
        from_event_id=eid_1, to_event_id=eid_2, relation_type="followup",
        weight=0.7, db_path=tmp_db,
    )
    # 事件↔指标
    rid_2 = add_relation(
        from_event_id=eid_2, to_indicator_code="NBS.GDP",
        relation_type="cause", weight=0.9, db_path=tmp_db,
    )
    if not (rid_1 and rid_2):
        _fail(f"两条关系应都返回 id, 实际 rid_1={rid_1}, rid_2={rid_2}")
    _ok(f"事件↔事件 rid={rid_1}, 事件↔指标 rid={rid_2}")

    # 互斥校验:两个都填应抛
    try:
        add_relation(
            from_event_id=eid_1, to_event_id=eid_2,
            to_indicator_code="NBS.GDP",
            relation_type="similar", db_path=tmp_db,
        )
    except EventValidationError:
        _ok("to_event_id + to_indicator_code 互斥校验 PASS")
    else:
        _fail("应抛 EventValidationError 但没抛")


def t6_stats(tmp_db: Path) -> None:
    print("T6 统计输出")
    result = stats_by_category(db_path=tmp_db)
    # 必含 key
    for key in (
        "db_path", "db_size_bytes", "total_event", "total_event_tag",
        "total_event_relation", "target_sum", "by_category", "tag_usage",
    ):
        if key not in result:
            _fail(f"stats 缺 key: {key!r}")
    # by_category 必须 8 大类齐全 + 顺序按 CATEGORIES
    if len(result["by_category"]) != len(CATEGORIES):
        _fail(
            f"by_category 应含 8 大类={len(CATEGORIES)}, 实际 {len(result['by_category'])}"
        )
    for i, (code, name_cn, target) in enumerate(CATEGORIES):
        row = result["by_category"][i]
        if row["category"] != code:
            _fail(f"by_category[{i}].category={row['category']}, 应 {code}")
        if row["name_cn"] != name_cn:
            _fail(f"by_category[{i}].name_cn={row['name_cn']}, 应 {name_cn}")
        if row["target"] != target:
            _fail(f"by_category[{i}].target={row['target']}, 应 {target}")
        if "gap" not in row or row["gap"] != max(target - row["current"], 0):
            _fail(f"by_category[{i}].gap 算错: {row}")
    # target_sum 必须 = 100
    if result["target_sum"] != 100:
        _fail(f"target_sum 应 = 100, 实际 {result['target_sum']}")
    # tag_usage 字典齐全
    for key in ("in_dict_used", "in_dict_unused", "out_of_dict_count", "top10_used"):
        if key not in result["tag_usage"]:
            _fail(f"tag_usage 缺 key: {key!r}")
    # T2 + T3 + T5 共 1+1+2 = 4 个 event
    if result["total_event"] != 4:
        _fail(
            f"total_event 应 = 4(T2+T3+T5 各 1+1+2), 实际 {result['total_event']}"
        )
    if result["total_event_relation"] != 2:
        _fail(
            f"total_event_relation 应 = 2(T5 关系×2), 实际 {result['total_event_relation']}"
        )
    # 临时 DB 存在 + size > 0
    if result["db_size_bytes"] <= 0:
        _fail(f"db_size_bytes 应 > 0, 实际 {result['db_size_bytes']}")
    _ok(
        f"8 大类齐全 + target_sum=100 + 4 event / {result['total_event_tag']} tag / "
        f"2 relation / {result['db_size_bytes']}B"
    )


def main() -> int:
    print("=== self_test_event · 6 步自检 ===")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_db = Path(f.name)
    try:
        t1_ddl_idempotent(tmp_db)
        t2_single_insert(tmp_db)
        t3_tag_whitelist(tmp_db)
        t4_list_recent(tmp_db)
        t5_relation(tmp_db)
        t6_stats(tmp_db)
    finally:
        tmp_db.unlink(missing_ok=True)
    print("=== 6/6 PASS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
