"""akshare 5 核心宏观指标 probe 入口。

对应 `项目开发计划.md §5-2` 跑通 5 大免费宏观数据源 + `docs/phase-0-data-source-catalog-v0.1.md §6.3 Day 1`。

行为
----
1. 探测 akshare 是否可用
   - 可用:走 `akshare.macro_china_*` 真实拉取(GDP / CPI / PMI / M2 / 社融)
   - 不可用(包未装 / 网络受限 / 依赖冲突):落 5 条 mock 数据并标记 `source_raw='mock'`
2. 把 5 指标的最新 1-3 期数据 upsert 到 `EconomyIngest.indicator_value`
3. 输出 probe 报告(指标条数 + 各指标已落库总条数 + 最近一条)

为什么允许 mock
--------------
- akshare 在本机 pip 21.2 + Python 3.9 下因 xlrd 依赖冲突无法安装(2026-08-26 验证)
- mock 落库后,本周 §5-2 Day 1 真正装上 akshare 时只需替换 `_fetch_*` 函数为真实调用,schema 契约不变
- 这样 schema / 数据契约 / 落库流程**先固化**,网络/包问题不阻塞开发

使用
----
    python3 -m backend.ingest.probe_akshare_5indicators \\
        --db data/economy_ingest.db \\
        [--allow-mock]

默认 `--allow-mock` 开启:akshare 拉取失败时自动落 mock 数据并在 stderr 打印原因。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

# 允许 `python3 backend/ingest/probe_akshare_5indicators.py` 直接跑
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.ingest.economy_ingest import (  # noqa: E402
    INDICATORS,
    IndicatorValue,
    count_values,
    init_db,
    list_indicators,
    upsert_many,
)

# ---------------------------------------------------------------------------
# 数据契约:每个指标对应一个 fetch 函数
# 真实接入(§5-2 Day 1)时,把这 5 个函数体替换为 akshare 调用
# ---------------------------------------------------------------------------

# 真实 akshare 接口(参考 docs/phase-0-data-source-catalog-v0.1.md §6.3 Day 1)
AKSHARE_PROBES: dict[str, str] = {
    "NBS.GDP": "macro_china_gdp",
    "NBS.CPI": "macro_china_cpi",
    "NBS.PMI": "macro_china_pmi",
    "PBOC.M2": "macro_china_m2",
    "PBOC.SHRZGM": "macro_china_shrzgm",
}

# mock 数据:每个指标 1 条最新期数据(用于无 akshare 时的 schema 验证)
# 数值参考 Daily/20-经济-Economy-日报-20260824.md 与 20260823.md
MOCK_LATEST: dict[str, IndicatorValue] = {
    "NBS.GDP": IndicatorValue(
        indicator_code="NBS.GDP",
        period_date="2026-06-30",
        value=341000.0,        # Q2 GDP(亿元, 2026 估算)
        yoy=4.3,                # 高盛下调 Q3 后 Q2 实际值(日报 8-23 要闻 2)
        mom=None,
        source_raw="mock",
        note="mock 来自日报 8-23:Q2 GDP 4.3%,akshare 未装时 schema 验证用",
    ),
    "NBS.CPI": IndicatorValue(
        indicator_code="NBS.CPI",
        period_date="2026-07-31",
        value=0.2,              # 7 月 CPI 同比(日报 8-23 推算)
        yoy=0.2,
        mom=0.1,
        source_raw="mock",
        note="mock:CPI 同比 0.2%(近月低位),akshare 未装时 schema 验证用",
    ),
    "NBS.PMI": IndicatorValue(
        indicator_code="NBS.PMI",
        period_date="2026-07-31",
        value=50.1,             # 7 月制造业 PMI
        yoy=None,
        mom=0.3,
        source_raw="mock",
        note="mock:制造业 PMI 50.1(略高于荣枯线),akshare 未装时 schema 验证用",
    ),
    "PBOC.M2": IndicatorValue(
        indicator_code="PBOC.M2",
        period_date="2026-07-31",
        value=3300000.0,        # M2 余额(亿元, 估算)
        yoy=8.6,
        mom=0.5,
        source_raw="mock",
        note="mock:M2 YoY 8.6%,akshare 未装时 schema 验证用",
    ),
    "PBOC.SHRZGM": IndicatorValue(
        indicator_code="PBOC.SHRZGM",
        period_date="2026-07-31",
        value=7700.0,           # 7 月社融增量(亿元, 估算)
        yoy=8.0,
        mom=-0.4,
        source_raw="mock",
        note="mock:7 月社融 7700 亿(同比多增, Q4 降准 25BP 预期博弈),akshare 未装时 schema 验证用",
    ),
}


# ---------------------------------------------------------------------------
# akshare 真实接入占位(§5-2 Day 1 替换)
# ---------------------------------------------------------------------------


def _fetch_via_akshare(code: str) -> list[IndicatorValue] | None:
    """尝试走 akshare 拉取 1 条最新期数据。

    返回 None 表示 akshare 不可用 / 拉取失败(由调用方降级到 mock)。
    """
    try:
        import akshare as ak  # type: ignore
    except Exception as exc:  # noqa: BLE001
        print(f"[akshare] import 失败:{type(exc).__name__}: {exc}", file=sys.stderr)
        return None

    fn_name = AKSHARE_PROBES.get(code)
    if not fn_name:
        return None
    try:
        fn = getattr(ak, fn_name, None)
        if fn is None:
            print(f"[akshare] {fn_name} 不存在", file=sys.stderr)
            return None
        df = fn()
        if df is None or len(df) == 0:
            print(f"[akshare] {fn_name} 返回空 DataFrame", file=sys.stderr)
            return None
        # 真实接入时这里做 DataFrame → IndicatorValue 转换
        # 当前先返回 None 触发 mock 降级
        print(f"[akshare] {fn_name} 拉取成功 {len(df)} 行(待 §5-2 Day 1 写 DataFrame → IndicatorValue 转换)", file=sys.stderr)
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[akshare] {fn_name} 调用失败:{type(exc).__name__}: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Probe 主流程
# ---------------------------------------------------------------------------


def probe(db_path: Path, allow_mock: bool = True) -> dict:
    """跑一次 5 指标 probe,返回报告 dict。"""
    init_db(db_path)
    print(f"[probe] init_db OK · {db_path}")

    results: list[dict] = []
    records: list[IndicatorValue] = []
    for ind in INDICATORS:
        code = ind["code"]
        recs = _fetch_via_akshare(code)
        if recs is None:
            if not allow_mock:
                results.append({"code": code, "status": "skipped", "n": 0})
                continue
            rec = MOCK_LATEST[code]
            records.append(rec)
            results.append({"code": code, "status": "mock", "n": 1,
                            "period": rec.period_date, "value": rec.value})
            print(f"[probe] {code} → mock({rec.period_date}={rec.value}{ind['unit']})")
        else:
            records.extend(recs)
            results.append({"code": code, "status": "akshare", "n": len(recs)})

    n = upsert_many(db_path, records)
    print(f"[probe] upsert_many OK · {n} 条")

    counts = count_values(db_path)
    return {
        "db": str(db_path),
        "results": results,
        "stored": counts,
        "indicators_total": len(INDICATORS),
    }


def render_report(report: dict) -> str:
    """给人看的报告(纯文本,不打彩色)。"""
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("EconomyAdvisor · 5 核心宏观指标 probe 报告")
    lines.append("=" * 64)
    lines.append(f"DB: {report['db']}")
    lines.append(f"指标数: {report['indicators_total']}")
    lines.append("")
    lines.append(f"{'指标':<14} {'状态':<10} {'最新期':<12} {'值':<14} {'已落库':<6}")
    lines.append("-" * 64)
    ind_map = {i["code"]: i for i in INDICATORS}
    for r in report["results"]:
        code = r["code"]
        ind = ind_map[code]
        unit = ind["unit"]
        period = r.get("period", "-")
        value = r.get("value", "-")
        if isinstance(value, float):
            value_s = f"{value:,.2f} {unit}"
        else:
            value_s = "-"
        stored = report["stored"].get(code, 0)
        lines.append(
            f"{code:<14} {r['status']:<10} {period:<12} {value_s:<14} {stored:<6}"
        )
    lines.append("-" * 64)
    lines.append(f"已落库指标值合计:{sum(report['stored'].values())} 条")
    lines.append("=" * 64)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="akshare 5 核心宏观指标 probe")
    parser.add_argument(
        "--db",
        default="data/economy_ingest.db",
        help="SQLite 路径(相对 EconomyWeb 根)",
    )
    parser.add_argument(
        "--allow-mock",
        action="store_true",
        default=True,
        help="akshare 拉取失败时是否落 mock 数据(默认开)",
    )
    parser.add_argument(
        "--no-mock",
        dest="allow_mock",
        action="store_false",
        help="akshare 拉取失败时跳过(不落库)",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    report = probe(db_path, allow_mock=args.allow_mock)
    print()
    print(render_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
