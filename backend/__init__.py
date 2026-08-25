"""EconomyAdvisor backend package.

Phase 0 §5-2 起步:5 大免费宏观数据源接入层骨架。
- ingest.economy_ingest:SQLite schema + 5 指标数据契约 + UPSERT
- ingest.probe_akshare_5indicators:akshare 5 指标 probe 入口(akshare 不可用时 mock 落库)
"""
__version__ = "0.1.0"
