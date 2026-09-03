"""event 子包:历史事件库落地层。

对应 `项目开发计划.md §5` 第 3 条:整理近 10 年 50 个关键政策文件 + 100 个历史宏观事件,
建结构化事件库。Schema 设计见 `docs/phase-0-event-library-design-v0.1.md`(2026-09-03)。

当前实现
--------
- `event_schema.py` —— DDL 建表 + 8 大类枚举 + 30 tag 起步词典 + 连接 helper
- `ingest_event.py` —— 人工录入 CLI(支持单条 + 批量 JSON)
- `self_test_event.py` —— 5 步自检(DDL 幂等 / 插入 / 标签 / 关联 / 查询)
"""
