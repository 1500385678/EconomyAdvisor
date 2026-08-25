# EconomyAdvisor

> 20-经济-Economy 行业 Web 项目 · 内部代号 EconomyAdvisor

## 项目说明
基于张勇的 36 行业架构,EconomyAdvisor 是 经济-Economy 行业的 Web 端顾问产品。

## 同步
- GitHub: https://github.com/1500385678/EconomyAdvisor
- Gitee: https://gitee.com/architectzy/EconomyAdvisor

## 自动化(cron 实际触发时间)
- T1 `daily-经济` 每日 00:10 写日报到 `Daily/`,推飞书私聊
- T2 `log-经济-日报` 每日 01:10 写日志到 `../.Log/`
- T3 `巡检-经济` 每日 02:10 巡检 + 写 `Logs/巡检-经济-YYYYMMDD.md` + commit
- T4 `dev-经济-日报` 每日 03:10 按 `.plan/YYYYMMDD.md` 写 1 个小变更 + commit + push

> README 历史口径曾写"02:00 / 03:00",已对齐到 00:10 / 01:10 / 02:10 / 03:10(2026-08-26)。

## 项目结构
```
EconomyWeb/
├── README.md                 # 本文件
├── 项目开发计划.md            # Phase 0-3 主计划
├── 经济顾问开发架构与计划.md    # 完整产品立项 + 技术方案 v1.0
├── backend/
│   └── ingest/                # §5-2 宏观数据接入层(2026-08-26 起步)
│       ├── economy_ingest.py              # SQLite schema + 5 指标数据契约
│       ├── probe_akshare_5indicators.py   # probe CLI(akshare 不可用时 mock 落库)
│       └── README.md                      # 使用说明 + 后续 §5-2 Day 1-5 任务分解
├── docs/                      # 阶段性调研文档
│   └── phase-0-data-source-catalog-v0.1.md
├── .plan/                     # 每日 dev plan(消费后清理)
├── Logs/                      # 每日巡检报告
└── data/                      # EconomyIngest SQLite 落库(运行时产物,不入 git)
```

## 跑通 probe(§5-2 起步基线)

```bash
cd /Users/aaron/Mac/Consultant/20-经济-Economy/_EconomyLib/EconomyWeb
python3 backend/ingest/probe_akshare_5indicators.py --db data/economy_ingest.db
```

akshare 不可用时自动落 mock,5 指标(GDP/CPI/PMI/M2/社融)schema 验证。详见 `backend/ingest/README.md`。
