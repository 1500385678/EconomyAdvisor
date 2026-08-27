/**
 * EconomyAdvisor · 共享 SQLite 访问层(frontend ↔ backend/ingest)
 *
 * 数据契约
 * --------
 * - DB 路径:`EconomyWeb/data/economy_ingest.db`(由 `backend/ingest/probe_akshare_5indicators.py` 落库)
 * - 表结构:见 `backend/ingest/economy_ingest.py` DDL_INDICATOR / DDL_INDICATOR_VALUE_TABLE
 * - 同步关系:本文件只读,所有写入仍走 backend/ingest 脚本
 *
 * 路径解析
 * --------
 * - 默认:`process.cwd() + '/../data/economy_ingest.db'`
 *   (Next.js dev/build 在 `frontend/` 下启动 cwd=`frontend/`,`../` 即 EconomyWeb 根)
 * - 兜底:相对本文件的 `../../data/economy_ingest.db`
 * - 显式:环境变量 `ECONOMY_INGEST_DB` 可指定绝对路径
 */

import Database from "better-sqlite3";
import path from "node:path";
import fs from "node:fs";

const DB_PATH_ENV = process.env.ECONOMY_INGEST_DB;

function resolveDbPath(): string {
  if (DB_PATH_ENV && fs.existsSync(DB_PATH_ENV)) return DB_PATH_ENV;
  const candidates = [
    path.join(process.cwd(), "..", "data", "economy_ingest.db"),
    path.join(process.cwd(), "data", "economy_ingest.db"),
    path.join(__dirname, "..", "..", "data", "economy_ingest.db"),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  // 不存在时返回默认,调用方按需报错
  return candidates[0];
}

const DB_PATH = resolveDbPath();

let _db: Database.Database | null = null;

/** 复用单例,避免热重载时重复打开导致文件锁。 */
export function getDb(): Database.Database {
  if (_db) return _db;
  _db = new Database(DB_PATH, { readonly: true, fileMustExist: false });
  _db.pragma("journal_mode = WAL");
  return _db;
}

/** 当前实际命中的 DB 路径(供日志/排错)。 */
export function getDbPath(): string {
  return DB_PATH;
}

export interface IndicatorRow {
  code: string;
  name_cn: string;
  name_en: string;
  source: string;
  freq: string;
  unit: string;
  akshare_fn: string | null;
  priority: string;
  first_seen: string | null;
  last_seen: string | null;
  created_at: string;
}

export interface IndicatorWithStats extends IndicatorRow {
  value_count: number;
  latest_period: string | null;
  latest_value: number | null;
  latest_source: string | null;
}

/** 列出全部指标 + 已落库条数 + 最新一期值(给 dashboard 卡片用)。 */
export function listIndicatorsWithStats(): IndicatorWithStats[] {
  const db = getDb();
  const rows = db
    .prepare(
      `SELECT code, name_cn, name_en, source, freq, unit, akshare_fn, priority,
              first_seen, last_seen, created_at
       FROM indicator
       ORDER BY priority, code`,
    )
    .all() as IndicatorRow[];

  const countStmt = db.prepare(
    `SELECT COUNT(*) AS n FROM indicator_value WHERE indicator_code = ?`,
  );
  const latestStmt = db.prepare(
    `SELECT period_date, value, source_raw
     FROM indicator_value
     WHERE indicator_code = ?
     ORDER BY period_date DESC
     LIMIT 1`,
  );

  return rows.map((r) => {
    const cnt = countStmt.get(r.code) as { n: number };
    const latest = latestStmt.get(r.code) as
      | { period_date: string; value: number; source_raw: string }
      | undefined;
    return {
      ...r,
      value_count: cnt.n,
      latest_period: latest?.period_date ?? null,
      latest_value: latest?.value ?? null,
      latest_source: latest?.source_raw ?? null,
    };
  });
}
