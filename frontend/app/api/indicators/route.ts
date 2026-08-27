/**
 * EconomyAdvisor · GET /api/indicators
 *
 * 返回 5 核心宏观指标 + 已落库条数 + 最新一期值。
 * 与 `frontend/app/page.tsx` 同源(均走 `frontend/lib/db.ts`),
 * 此路由主要为后续 LLM Agent / 飞书 Bot 提供 JSON 入口。
 */

import { NextResponse } from "next/server";
import {
  listIndicatorsWithStats,
  getDbPath,
  type IndicatorWithStats,
} from "@/lib/db";

// 强制路由在 Node.js runtime(better-sqlite3 是 native 模块)
export const runtime = "nodejs";
// 不缓存,确保每次拿到最新落库数据
export const dynamic = "force-dynamic";

export function GET() {
  let indicators: IndicatorWithStats[];
  let dbPath: string;
  try {
    indicators = listIndicatorsWithStats();
    dbPath = getDbPath();
  } catch (err) {
    return NextResponse.json(
      {
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      },
      { status: 500 },
    );
  }
  return NextResponse.json({
    ok: true,
    db: dbPath,
    count: indicators.length,
    indicators,
  });
}
