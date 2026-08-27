---
tags:
  - phase-0
  - frontend
  - nextjs
  - skeleton
created: 2026-08-28
updated: 2026-08-28
---

# frontend · Next.js 14 最小骨架

> EconomyAdvisor Web 端 Phase 1 MVP 启动基线 v2 · §5-2 Day 4(2026-08-28)
> 不在本 README 展开的部分:`backend/ingest/` 接入层 + SQLite schema 契约

## 0. 当前阶段(2026-08-28)

- 起步:Next.js 14 (App Router) + React 18 + TypeScript + better-sqlite3
- 范围:**1 个主页 + 1 个 API 路由**,5 指标卡片展示,无 LLM 解读、无图表
- 状态:代码已落库,本机 `npm install` + `npm run dev` **未验证**(本机 Python 3.9.6 + Node 24.19,`better-sqlite3@11.3.0` 需要重编译,首次安装可能 1-3 分钟)

## 1. 文件清单

| 文件 | 作用 |
|---|---|
| `package.json` | Next.js 14 / React 18 / better-sqlite3 / TypeScript 5 依赖 |
| `tsconfig.json` | Next.js 标准 + `@/*` paths 解析 |
| `next.config.js` | `serverComponentsExternalPackages: ["better-sqlite3"]` + `outputFileTracingRoot` |
| `.gitignore` | node_modules / .next / 锁文件策略(显式禁 `package-lock.json`,项目以 `package.json` 为单一来源) |
| `app/layout.tsx` | 根布局,中文 lang + 标题 |
| `app/globals.css` | 极简 CSS variables + 5 指标栅格卡片样式 |
| `app/page.tsx` | Server Component 主页,5 指标卡片(读 SQLite) |
| `app/api/indicators/route.ts` | GET `/api/indicators` REST 路由,JSON 输出 |
| `lib/db.ts` | better-sqlite3 单例 + `listIndicatorsWithStats()` 复用 `indicator` + `indicator_value` |

## 2. 数据契约(与 backend/ingest 对齐)

- **DB 路径**:`EconomyWeb/data/economy_ingest.db`
  - 解析顺序:① `process.env.ECONOMY_INGEST_DB` ② `cwd/../data/` ③ `cwd/data/` ④ `__dirname/../../data/`
  - Next.js 默认从 `frontend/` 启动,`cwd/../` 即 EconomyWeb 根
- **表结构**:`indicator` + `indicator_value`,DDL 见 `backend/ingest/economy_ingest.py`
- **同步关系**:本模块**只读**,所有写入仍走 `backend/ingest/probe_akshare_5indicators.py`
- **5 指标**(P0):NBS.GDP / NBS.CPI / NBS.PMI / PBOC.M2 / PBOC.SHRZGM

## 3. 使用

### 3.1 安装(首次,需本机有 Node 18+ 与 Python 编译链)

```bash
cd /Users/aaron/Mac/Consultant/20-经济-Economy/_EconomyLib/EconomyWeb/frontend
npm install
```

### 3.2 跑通(先有 DB 数据)

```bash
# 1) 跑 backend probe 落库(macOS 自带 Python 3.9,akshare 不可用时落 mock)
cd /Users/aaron/Mac/Consultant/20-经济-Economy/_EconomyLib/EconomyWeb
python3 backend/ingest/probe_akshare_5indicators.py --db data/economy_ingest.db

# 2) 启 frontend
cd frontend
npm run dev
# 浏览器打开 http://localhost:3001
```

### 3.3 JSON API(给后续 LLM Agent / 飞书 Bot 调用)

```bash
curl http://localhost:3001/api/indicators
# 返回 {ok, db, count, indicators:[{code, name_cn, ..., value_count, latest_period, latest_value, latest_source}]}
```

## 4. 已知约束

### 4.1 本机未验证

- `npm install` 未跑(`better-sqlite3@11.3.0` 需要 node-gyp 编译,本机 `python3` 已存在但 xcode-select CLT 是否齐全未知)
- `npm run dev` / `npm run build` 未跑(本任务定位"代码可入库",运行验证留给显式环境验证轮次)

### 4.2 与项目整体的对齐

- **akshare 真实拉取**:本模块对数据来源透明,`source_raw='mock'` 与 `'akshare'` 都正确展示,等 §5-2 Day 5 5 源端到端后自动出现 `source_raw='akshare'`
- **LLM 解读卡片**:未实现,等 §6 Phase 1 MVP 飞书 Agent 接入
- **归因引擎**:未实现,等 §5-6 归因 schema v0.1
- **ECharts 图表**:未引入,先有"指标字典"页面,图表留给 §6 Phase 1 Web 看板

## 5. 关联文档

- `项目开发计划.md §5-2` 跑通 5 大免费宏观数据源(本任务为子项"frontend 最小骨架")
- `项目开发计划.md §6 Phase 1 MVP` 第 3 项 Web 看板(本任务为前置依赖)
- `backend/ingest/README.md` EconomyIngest schema + 5 指标字典(本模块读取的对象)
- `backend/ingest/probe_akshare_5indicators.py` probe 入口(本模块的喂数脚本)
- `Logs/巡检-经济-20260828.md` §"T4 今日硬性目标"上游决策
- `.plan/20260828.md` 2026-08-28 当日 T4 dev 计划

## 变更记录

| 时间 | 变更 | 触发 |
|---|---|---|
| 2026-08-28 03:10 | §5-2 Day 4:Next.js 14 + React 18 + better-sqlite3 最小骨架;1 主页 + 1 API 路由 + lib/db.ts + 样式 + 配置 7 文件;与 `backend/ingest/` 形成最小可运行栈 | 每日 03:10 cron T4 · 项目开发计划 §5-2 第 4 步 |
