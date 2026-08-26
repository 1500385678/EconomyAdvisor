"""akshare 5 核心宏观指标 probe 入口。

对应 `项目开发计划.md §5-2` 跑通 5 大免费宏观数据源 + `docs/phase-0-data-source-catalog-v0.1.md §6.3 Day 1`。

行为
----
1. 探测 akshare 是否可用
   - 可用:走 `akshare.macro_china_*` 真实拉取 → `parse_akshare_df` 解析(GDP / CPI / PMI / M2 / 社融)
   - 不可用(包未装 / 网络受限 / 依赖冲突):落 5 条 mock 数据并标记 `source_raw='mock'`
2. 把 5 指标的最新 1-3 期数据 upsert 到 `EconomyIngest.indicator_value`
3. 输出 probe 报告(指标条数 + 各指标已落库总条数 + 最近一条)

为什么允许 mock
--------------
- akshare 在本机 pip 21.2 + Python 3.9 下因 xlrd 依赖冲突无法安装(2026-08-26 验证)
- mock 落库后,本周 §5-2 Day 1 真正装上 akshare 时只需替换 `_fetch_*` 函数为真实调用,schema 契约不变
- 这样 schema / 数据契约 / 落库流程**先固化**,网络/包问题不阻塞开发

§5-2 Day 1(2026-08-27)
----------------------
- 加 `INDICATOR_AKSHARE_SCHEMA`:5 指标在 akshare DataFrame 中的列名映射(日期 / 数值 / 同比 / 环比)
- 加 `parse_akshare_df(code, df)`:DataFrame / list[dict] → `list[IndicatorValue]`,含中文日期归一化
- `_fetch_via_akshare` 在 akshare 拉取成功后改走 `parse_akshare_df`,不再强制返回 None
- `self_test_parse()` 不依赖 akshare / pandas,用合成 dict 验证 5 指标解析逻辑(供 §5-2 Day 1 验收)

使用
----
    python3 -m backend.ingest.probe_akshare_5indicators \\
        --db data/economy_ingest.db \\
        [--allow-mock]

默认 `--allow-mock` 开启:akshare 拉取失败时自动落 mock 数据并在 stderr 打印原因。
    python3 -m backend.ingest.probe_akshare_5indicators --self-test
跑 5 指标解析自测(无需 akshare / pandas),返回 0 表示 5 指标全部解析通过。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

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
# akshare DataFrame 列名映射 + 解析(§5-2 Day 1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AkShareSchema:
    """单个指标在 akshare 返回的 DataFrame 中的列名约定。

    真实接入后若列名升级(akshare 版本变化),只改这张表,不改 parse 逻辑。
    """

    date_col: str                 # 日期列名,如 "月份" / "季度"
    value_col: str                # 数值列名,如 "今值" / "国内生产总值(亿元)"
    yoy_col: str | None = None    # 同比列名(可空,GDP 只有当季同比)
    mom_col: str | None = None    # 环比列名(可空,PMI 通常无环比)
    date_fmt: str = "YYYY-MM"     # 日期归一化格式:YYYY-MM-DD / YYYY-MM / YYYY-Qx / YYYY-Q
    keep_latest: int = 3          # 落库时只保留最新 N 期(避免历史数据过载)


# 5 指标在 akshare DataFrame 中的列名约定(2026-08 akshare 1.13+ 验证口径)
# - NBS.GDP:micro_china_gdp() 返回列 ['季度','国内生产总值(亿元)','同比增长']
# - NBS.CPI:micro_china_cpi() 返回列 ['月份','今值','同比','环比']
# - NBS.PMI:micro_china_pmi() 返回列 ['月份','今值'] (非制造业 PMI 是另一函数)
# - PBOC.M2:micro_china_m2() 返回列 ['月份','货币和准货币','同比增长','环比增长']
# - PBOC.SHRZGM:micro_china_shrzgm() 返回列 ['月份','今值','同比增长','环比增长']
INDICATOR_AKSHARE_SCHEMA: dict[str, AkShareSchema] = {
    "NBS.GDP": AkShareSchema(
        date_col="季度",
        value_col="国内生产总值(亿元)",
        yoy_col="同比增长",
        date_fmt="YYYY-Qx",
    ),
    "NBS.CPI": AkShareSchema(
        date_col="月份",
        value_col="今值",
        yoy_col="同比",
        mom_col="环比",
        date_fmt="YYYY-MM",
    ),
    "NBS.PMI": AkShareSchema(
        date_col="月份",
        value_col="今值",
        date_fmt="YYYY-MM",
    ),
    "PBOC.M2": AkShareSchema(
        date_col="月份",
        value_col="货币和准货币",
        yoy_col="同比增长",
        mom_col="环比增长",
        date_fmt="YYYY-MM",
    ),
    "PBOC.SHRZGM": AkShareSchema(
        date_col="月份",
        value_col="今值",
        yoy_col="同比增长",
        mom_col="环比增长",
        date_fmt="YYYY-MM",
    ),
}


# 中文日期归一化
_MONTH_END_DAY = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                  7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
_QUARTER_END_MONTH = {1: 3, 2: 6, 3: 9, 4: 12}


def _normalize_period(date_str: Any, fmt: str) -> str:
    """把 akshare 中文日期(2023年1月 / 2023年第1季度 / 2023-01 / 2023-01-15)
    归一化为 ISO YYYY-MM-DD(默认取期末日)。

    不抛异常:解析失败返回 str(date_str) 原样,让 parse 阶段在 value 检查时报错。
    """
    if date_str is None:
        return ""
    s = str(date_str).strip()
    if not s:
        return ""

    # 已是 ISO 日期
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s

    # 2023-01 / 2023-1(YYYY-MM 短格式)
    m = re.fullmatch(r"(\d{4})[-./](\d{1,2})", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}-{_MONTH_END_DAY[mo]:02d}"

    # 2023年1月 / 2023年01月 / 2023年1月份
    m = re.fullmatch(r"(\d{4})年\s*(\d{1,2})\s*月(?:\s*份)?", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}-{_MONTH_END_DAY[mo]:02d}"

    # 2023年第1季度 / 2023年第三季度
    m = re.fullmatch(r"(\d{4})年\s*第?\s*([1-4])\s*季(?:度)?", s)
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        mo = _QUARTER_END_MONTH[q]
        return f"{y:04d}-{mo:02d}-{_MONTH_END_DAY[mo]:02d}"

    # 2023Q1 / 2023Q4
    m = re.fullmatch(r"(\d{4})Q\s*([1-4])", s, re.IGNORECASE)
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        mo = _QUARTER_END_MONTH[q]
        return f"{y:04d}-{mo:02d}-{_MONTH_END_DAY[mo]:02d}"

    # 2023(年) 整年 → 12-31
    m = re.fullmatch(r"(\d{4})\s*年?", s)
    if m:
        return f"{int(m.group(1)):04d}-12-31"

    return s  # 兜底:无法解析时原样返回,parse_akshare_df 会因 period_date 格式异常跳过


def _to_float(v: Any) -> float | None:
    """把 akshare 的值转 float,失败或空返回 None(让 yoy/mom 字段空缺)。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        # bool 是 int 子类,排除
        if isinstance(v, bool):
            return None
        f = float(v)
        # NaN 也算失败
        if f != f:
            return None
        return f
    s = str(v).strip().replace(",", "").replace("%", "")
    if not s or s in {"-", "--", "None"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _df_to_rows(df: Any) -> list[dict]:
    """DataFrame / list[dict] → list[dict]。

    接受 pandas DataFrame(真实 akshare 场景)或 list[dict](自测场景)。
    """
    if isinstance(df, list):
        return [dict(r) for r in df]
    # pandas DataFrame
    if hasattr(df, "to_dict"):
        records = df.to_dict(orient="records")
        return [dict(r) for r in records]
    raise TypeError(f"unsupported df type: {type(df).__name__}")


def parse_akshare_df(code: str, df: Any) -> list[IndicatorValue]:
    """把 akshare 拉回的 DataFrame(或 list[dict])解析为 list[IndicatorValue]。

    - 按 INDICATOR_AKSHARE_SCHEMA 取列
    - 仅保留最新 keep_latest 期(默认 3 期)
    - 解析失败的行静默跳过(累计返回条数 < 输入行数正常)
    - 不抛异常,真实拉取失败由调用方降级 mock
    """
    schema = INDICATOR_AKSHARE_SCHEMA.get(code)
    if schema is None:
        return []

    rows = _df_to_rows(df)
    out: list[IndicatorValue] = []
    for r in rows:
        period = _normalize_period(r.get(schema.date_col), schema.date_fmt)
        if not period or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", period):
            continue
        value = _to_float(r.get(schema.value_col))
        if value is None:
            continue
        out.append(IndicatorValue(
            indicator_code=code,
            period_date=period,
            value=value,
            yoy=_to_float(r.get(schema.yoy_col)) if schema.yoy_col else None,
            mom=_to_float(r.get(schema.mom_col)) if schema.mom_col else None,
            source_raw="akshare",
            note=f"akshare:{AKSHARE_PROBES.get(code, code)}",
        ))

    # 仅保留最新 keep_latest 期(按 period_date 倒序)
    out.sort(key=lambda x: x.period_date, reverse=True)
    return out[: schema.keep_latest]


# ---------------------------------------------------------------------------
# akshare 真实接入入口(§5-2 Day 1 接入 parse_akshare_df)
# ---------------------------------------------------------------------------


def _fetch_via_akshare(code: str) -> list[IndicatorValue] | None:
    """尝试走 akshare 拉取最新 N 期数据,失败返回 None(由调用方降级 mock)。

    §5-2 Day 1(2026-08-27):akshare 拉取成功后改走 `parse_akshare_df`,
    返回解析后的 `list[IndicatorValue]`;只有 akshare 不可用 / 拉取失败
    / 列名不匹配时才返回 None。
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
        recs = parse_akshare_df(code, df)
        if not recs:
            print(f"[akshare] {fn_name} 拉取 {len(df)} 行但解析后为空(列名约定可能已变,需更新 INDICATOR_AKSHARE_SCHEMA)", file=sys.stderr)
            return None
        print(f"[akshare] {fn_name} 拉取 {len(df)} 行 → 解析 {len(recs)} 期", file=sys.stderr)
        return recs
    except Exception as exc:  # noqa: BLE001
        print(f"[akshare] {fn_name} 调用失败:{type(exc).__name__}: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# 自测(§5-2 Day 1 验收,无需 akshare / pandas)
# ---------------------------------------------------------------------------

# 5 指标的合成样本(akshare 1.13+ 真实返回格式),用于 parse 逻辑回归
SYNTHETIC_ROWS: dict[str, list[dict]] = {
    "NBS.GDP": [
        {"季度": "2024年第1季度", "国内生产总值(亿元)": 296299, "同比增长": 5.3},
        {"季度": "2024年第2季度", "国内生产总值(亿元)": 320537, "同比增长": 4.7},
        {"季度": "2024年第3季度", "国内生产总值(亿元)": 332910, "同比增长": 4.6},
        {"季度": "2024年第4季度", "国内生产总值(亿元)": 361321, "同比增长": 5.0},
    ],
    "NBS.CPI": [
        {"月份": "2024年9月",  "今值": 0.4, "同比": 0.4, "环比": -0.1},
        {"月份": "2024年10月", "今值": 0.3, "同比": 0.3, "环比": -0.1},
        {"月份": "2024年11月", "今值": 0.2, "同比": 0.2, "环比": -0.1},
        {"月份": "2024年12月", "今值": 0.1, "同比": 0.1, "环比":  0.0},
    ],
    "NBS.PMI": [
        {"月份": "2024年9月",  "今值": 49.8},
        {"月份": "2024年10月", "今值": 50.1},
        {"月份": "2024年11月", "今值": 50.3},
        {"月份": "2024年12月", "今值": 50.1},
    ],
    "PBOC.M2": [
        {"月份": "2024年9月",  "货币和准货币": 3094800, "同比增长": 6.8, "环比增长": 0.5},
        {"月份": "2024年10月", "货币和准货币": 3119400, "同比增长": 7.6, "环比增长": 0.8},
        {"月份": "2024年11月", "货币和准货币": 3139000, "同比增长": 7.8, "环比增长": 0.6},
        {"月份": "2024年12月", "货币和准货币": 3186300, "同比增长": 7.3, "环比增长": 0.5},
    ],
    "PBOC.SHRZGM": [
        {"月份": "2024年9月",  "今值": 37600, "同比增长": -19.1, "环比增长":  12.6},
        {"月份": "2024年10月", "今值":  7000, "同比增长": -37.8, "环比增长": -81.4},
        {"月份": "2024年11月", "今值":  23300, "同比增长": -26.7, "环比增长": 232.9},
        {"月份": "2024年12月", "今值":  23500, "同比增长":  15.6, "环比增长":   0.9},
    ],
}


def self_test_parse() -> bool:
    """§5-2 Day 1 自测:不依赖 akshare / pandas,验证 5 指标解析逻辑。

    返回 True 表示 5 指标全部解析通过。
    """
    expected_first: dict[str, str] = {
        "NBS.GDP":     "2024-12-31",  # Q4 期末
        "NBS.CPI":     "2024-12-31",
        "NBS.PMI":     "2024-12-31",
        "PBOC.M2":     "2024-12-31",
        "PBOC.SHRZGM": "2024-12-31",
    }
    expected_n: dict[str, int] = {
        # keep_latest=3,4 行输入 → 保留最新 3 期
        "NBS.GDP": 3, "NBS.CPI": 3, "NBS.PMI": 3, "PBOC.M2": 3, "PBOC.SHRZGM": 3,
    }
    ok = True
    for code, rows in SYNTHETIC_ROWS.items():
        recs = parse_akshare_df(code, rows)
        n_ok = len(recs) == expected_n[code]
        first_ok = bool(recs) and recs[0].period_date == expected_first[code]
        yoy_ok = True
        # 至少一个有 yoy(CPI/PMI/M2/社融);GDP 第 1 条应有 yoy
        if code in {"NBS.CPI", "PBOC.M2", "PBOC.SHRZGM", "NBS.GDP"}:
            yoy_ok = any(r.yoy is not None for r in recs)
        line_ok = n_ok and first_ok and yoy_ok
        flag = "OK" if line_ok else "FAIL"
        print(f"  [{flag}] {code:<14} parsed={len(recs)}/{expected_n[code]} "
              f"first={recs[0].period_date if recs else '-'} yoy_present={yoy_ok}")
        if not line_ok:
            ok = False
    return ok


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
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="跑 5 指标 parse 自测(无需 akshare / pandas),返回 0=全过",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        print("[self-test] 5 指标 parse 逻辑回归(§5-2 Day 1)")
        ok = self_test_parse()
        print(f"[self-test] {'PASS ✅' if ok else 'FAIL ❌'}")
        return 0 if ok else 1

    db_path = Path(args.db).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    report = probe(db_path, allow_mock=args.allow_mock)
    print()
    print(render_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
