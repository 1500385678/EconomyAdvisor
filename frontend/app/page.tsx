/**
 * EconomyAdvisor · 主页:5 核心宏观指标卡片
 *
 * 数据流
 * ------
 * - Server Component,直接读 SQLite(`frontend/lib/db.ts`)
 * - 5 张卡片:code / 中文名 / 来源 / 频率 / 单位 / 优先级 / 已落库条数 / 最新一期
 * - 无 LLM 解读(留给 Phase 1 MVP 飞书 Agent 接入)
 *
 * akshare 未装时显示 mock 数据(见 `backend/ingest/probe_akshare_5indicators.py`)
 */

import { listIndicatorsWithStats, getDbPath, type IndicatorWithStats } from "@/lib/db";

function formatValue(value: number | null, unit: string): string {
  if (value === null) return "-";
  if (unit === "%") return `${value.toFixed(1)} %`;
  if (value >= 10000) return `${(value / 10000).toFixed(2)} 万亿`;
  if (value >= 1000) return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  return value.toFixed(2);
}

function IndicatorCard({ ind }: { ind: IndicatorWithStats }) {
  const sourceClass = `badge-source badge-source-${ind.source}`;
  return (
    <article className="indicator-card">
      <header>
        <div>
          <h2>{ind.name_cn}</h2>
          <div className="code">{ind.code}</div>
          <div className="name-en">{ind.name_en}</div>
        </div>
        <span className={`badge badge-${ind.priority.toLowerCase()}`}>{ind.priority}</span>
      </header>

      <dl className="facts">
        <dt>来源</dt>
        <dd>
          <span className={sourceClass}>{ind.source}</span>
        </dd>
        <dt>频率</dt>
        <dd>{ind.freq}</dd>
        <dt>单位</dt>
        <dd>{ind.unit}</dd>
        <dt>akshare 函数</dt>
        <dd>{ind.akshare_fn ?? "-"}</dd>
        <dt>已落库</dt>
        <dd>{ind.value_count} 期</dd>
      </dl>

      {ind.latest_value !== null ? (
        <div className="latest-value">
          <div>最新期 {ind.latest_period}</div>
          <strong>{formatValue(ind.latest_value, ind.unit)}</strong>
          <div className="source-raw">来源:{ind.latest_source}</div>
        </div>
      ) : (
        <div className="latest-value" style={{ background: "#fff5f5", borderLeftColor: "#dc2626" }}>
          <strong>暂无数据</strong>
          <div className="source-raw">需先跑 backend/ingest probe 落库</div>
        </div>
      )}
    </article>
  );
}

export default function HomePage() {
  const indicators = listIndicatorsWithStats();
  const dbPath = getDbPath();
  const totalValues = indicators.reduce((s, i) => s + i.value_count, 0);
  const mockCount = indicators.filter((i) => i.latest_source === "mock").length;

  return (
    <>
      <header className="page-header">
        <h1>EconomyAdvisor · 5 核心宏观指标看板</h1>
        <p>20-经济-Economy 行业 Web 端 · v0.1 起步(frontend 最小骨架 · 2026-08-28)</p>
      </header>
      <main>
        <div className="meta-bar">
          <span>DB:<code>{dbPath}</code></span>
          <span>指标数:<strong>{indicators.length}</strong></span>
          <span>已落库合计:<strong>{totalValues}</strong> 期</span>
          {mockCount > 0 && <span>其中 mock:<strong>{mockCount}</strong> 条(待 akshare 接入后转真实)</span>}
        </div>

        {indicators.length === 0 ? (
          <div className="empty-state">
            <p>SQLite 里还没有指标字典。</p>
            <p>请先在 EconomyWeb 根目录跑:<br />
              <code>python3 backend/ingest/probe_akshare_5indicators.py --db data/economy_ingest.db</code>
            </p>
          </div>
        ) : (
          <section className="indicator-grid">
            {indicators.map((ind) => (
              <IndicatorCard key={ind.code} ind={ind} />
            ))}
          </section>
        )}
      </main>
      <footer className="page-footer">
        Phase 0 §5-2 Day 4 · frontend 最小骨架 · 见 <code>项目开发计划.md</code> &amp; <code>backend/ingest/README.md</code>
      </footer>
    </>
  );
}
