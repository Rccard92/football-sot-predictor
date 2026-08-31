import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  fetchLeaguePatternAnalysisLatest,
  fetchLeaguePatternAnalysisLeague,
  formatNum,
  formatPct01,
  formatRoiPct,
  type LpaLatestPayload,
  type LpaLeagueDetail,
  type LpaMetrics,
  type LpaSeasonCell,
} from '../../../lib/leaguePatternAnalysisApi'
import { roiColor } from '../overview/overviewTheme'
import { LabInfoTooltip } from './LabInfoTooltip'
import { PatternDetailDrawer } from './PatternDetailDrawer'
import { PatternLeagueHeatmap } from './PatternLeagueHeatmap'

type SubTab = 'global' | 'league' | 'native'

const SEASONS = ['2021/2022', '2022/2023', '2023/2024', '2024/2025'] as const
const SEASON_SHORT = ['21/22', '22/23', '23/24', '24/25'] as const

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <motion.div
      className="relative overflow-hidden rounded-2xl p-4"
      style={{
        background: 'linear-gradient(145deg, rgba(26,47,71,0.9) 0%, rgba(18,32,51,0.95) 100%)',
        border: '1px solid var(--lab-border)',
      }}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="text-[11px] uppercase tracking-wider" style={{ color: 'var(--lab-muted)' }}>
        {label}
      </div>
      <div className="mt-2 text-xl font-semibold tabular-nums">{value}</div>
    </motion.div>
  )
}

function SeasonCell({ cell }: { cell?: LpaSeasonCell }) {
  if (!cell || !cell.n) {
    return <span style={{ color: 'var(--lab-muted)' }}>—</span>
  }
  return (
    <div className="space-y-0.5 text-xs tabular-nums" title={`N ${cell.n} · WR ${formatPct01(cell.win_rate)} · ROI ${formatRoiPct(cell.roi_pct)} · Profit ${formatNum(cell.profit_1u)}`}>
      <div>N {cell.n}</div>
      <div>WR {formatPct01(cell.win_rate)}</div>
      <div style={{ color: roiColor(cell.roi_pct ?? 0) }}>ROI {formatRoiPct(cell.roi_pct)}</div>
      <div>P {formatNum(cell.profit_1u, 1)}</div>
    </div>
  )
}

function TotalCell({ total }: { total?: LpaMetrics }) {
  if (!total) return <span>—</span>
  return (
    <div className="space-y-0.5 text-xs tabular-nums">
      <div>N {total.n ?? 0}</div>
      <div>WR {formatPct01(total.win_rate)}</div>
      <div>Odds {formatNum(total.avg_odds, 2)}</div>
      <div>P {formatNum(total.profit_1u, 1)}</div>
      <div style={{ color: roiColor(total.roi_pct ?? 0) }} className="font-semibold">
        ROI {formatRoiPct(total.roi_pct)}
      </div>
      <div>{total.stability_label || '—'}</div>
    </div>
  )
}

export function LeaguePatternAnalysisTab() {
  const [sub, setSub] = useState<SubTab>('global')
  const [data, setData] = useState<LpaLatestPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [drawer, setDrawer] = useState<{ id: string; kind: 'global' | 'native' } | null>(
    null,
  )
  const [selectedLeague, setSelectedLeague] = useState<string | null>(null)
  const [leagueDetail, setLeagueDetail] = useState<LpaLeagueDetail | null>(null)
  const [leagueLoading, setLeagueLoading] = useState(false)
  const [methodOpen, setMethodOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchLeaguePatternAnalysisLatest()
      .then((payload) => {
        if (!cancelled) {
          setData(payload)
          setError(null)
          setLoading(false)
          const first = payload.competition_regimes_overview?.[0]?.competition
          if (first) setSelectedLeague(first)
        }
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setError(e.message || 'Snapshot non disponibile')
          setData(null)
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!selectedLeague || sub !== 'league') return
    let cancelled = false
    setLeagueLoading(true)
    fetchLeaguePatternAnalysisLeague(selectedLeague)
      .then((d) => {
        if (!cancelled) {
          setLeagueDetail(d)
          setLeagueLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLeagueDetail(null)
          setLeagueLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [selectedLeague, sub])

  const insights = useMemo(() => {
    const t = data?.summary?.top_insights as Record<string, unknown> | undefined
    return t || {}
  }, [data])

  return (
    <div className="space-y-6 p-4 sm:p-6" data-testid="league-pattern-analysis-tab">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">LEAGUE PATTERN ANALYSIS</h2>
          <p className="mt-1 text-sm" style={{ color: 'var(--lab-muted)' }}>
            Analisi globale e per campionato dei pattern storici
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span
            className="lab-badge-ok rounded-full px-3 py-1 text-xs font-semibold"
            data-testid="lpa-dataset-locked"
          >
            ANALYSIS DATASET LOCKED · 2021/22 → 2024/25
          </span>
          <span
            className="rounded-full px-3 py-1 text-xs font-semibold"
            style={{
              background: 'rgba(239,68,68,0.15)',
              color: 'var(--lab-err)',
              border: '1px solid rgba(239,68,68,0.35)',
            }}
            data-testid="lpa-no-2025-26"
          >
            2025/26 NON UTILIZZATA
          </span>
        </div>
      </div>

      <nav className="flex flex-wrap gap-1" data-testid="lpa-subtabs">
        {(
          [
            ['global', 'Panoramica globale'],
            ['league', 'Per campionato'],
            ['native', 'League-native'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`lab-tab rounded-t-lg px-4 py-2 text-sm font-medium ${
              sub === id ? 'lab-tab-active' : ''
            }`}
            onClick={() => setSub(id)}
            data-testid={`lpa-subtab-${id}`}
          >
            {label}
          </button>
        ))}
      </nav>

      {loading && <p style={{ color: 'var(--lab-muted)' }}>Caricamento snapshot…</p>}
      {error && (
        <div className="lab-card p-4" style={{ color: 'var(--lab-warn)' }}>
          {error}
          <div className="mt-2 text-xs" style={{ color: 'var(--lab-muted)' }}>
            Genera lo snapshot con:{' '}
            <code>python -m scripts.build_league_pattern_analysis_snapshot</code>
          </div>
        </div>
      )}

      {data && sub === 'global' && (
        <div className="space-y-6" data-testid="lpa-panel-global">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <KpiCard label="Stagioni" value={String(data.summary.seasons_count ?? 4)} />
            <KpiCard
              label="Campionati"
              value={String(data.summary.competitions_count ?? 16)}
            />
            <KpiCard
              label="Match eligible"
              value={String(data.summary.eligible_matches_analyzed ?? '—')}
            />
            <KpiCard
              label="Market rows"
              value={String(data.summary.informative_market_rows_analyzed ?? '—')}
            />
            <KpiCard
              label="Global Patterns"
              value={String(data.summary.global_patterns_count ?? 12)}
            />
            <KpiCard
              label="League-Native"
              value={String(data.summary.league_native_count ?? 10)}
            />
          </div>

          <div className="lab-card overflow-x-auto p-4">
            <div className="mb-3 text-sm font-semibold">P01–P12 · andamento stagionale</div>
            <table className="lab-table w-full min-w-[900px] text-sm">
              <thead className="sticky top-0">
                <tr>
                  <th>Pattern</th>
                  {SEASON_SHORT.map((s) => (
                    <th key={s}>{s}</th>
                  ))}
                  <th>TOTALE</th>
                  <th>STABILITÀ</th>
                </tr>
              </thead>
              <tbody>
                {data.global_patterns.map((p) => (
                  <tr
                    key={p.pattern_id}
                    className="cursor-pointer hover:bg-white/5"
                    onClick={() => setDrawer({ id: p.pattern_id, kind: 'global' })}
                  >
                    <td>
                      <div className="font-medium">{p.pattern_id}</div>
                      <div className="flex items-center gap-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
                        <span>{p.human?.human_title || p.label}</span>
                        <LabInfoTooltip
                          title="Cosa identifica"
                          text={p.human?.long_explanation || p.human?.short_explanation || ''}
                        />
                      </div>
                      <code className="text-[10px]" style={{ color: 'var(--lab-cyan)' }}>
                        {p.human?.technical_formula}
                      </code>
                    </td>
                    {SEASONS.map((s) => (
                      <td key={s}>
                        <SeasonCell cell={p.by_season?.[s]} />
                      </td>
                    ))}
                    <td>
                      <TotalCell total={p.total} />
                    </td>
                    <td className="text-xs">{p.total?.stability_label || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="lab-card p-4" data-testid="lpa-top-insights">
            <div className="mb-3 text-sm font-semibold">TOP INSIGHTS</div>
            <p className="mb-3 text-xs" style={{ color: 'var(--lab-muted)' }}>
              Sample minimo N ≥ {(insights.min_sample as number) || 20}. ROI sempre con N.
            </p>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {[
                ['Miglior ROI pooled', insights.best_pooled_roi],
                ['Maggior profitto', insights.most_profit],
                ['Maggior N', insights.most_selections],
                ['Miglior worst-season ROI', insights.best_worst_season_roi],
              ].map(([label, item]) => {
                const row = item as {
                  pattern_id?: string
                  n?: number
                  roi_pct?: number
                  profit_1u?: number
                } | null
                return (
                  <div key={String(label)} className="rounded-xl p-3" style={{ background: 'var(--lab-surface-2)' }}>
                    <div className="text-[11px] uppercase" style={{ color: 'var(--lab-muted)' }}>
                      {label as string}
                    </div>
                    {row ? (
                      <button
                        type="button"
                        className="mt-1 text-left"
                        onClick={() =>
                          row.pattern_id &&
                          setDrawer({ id: row.pattern_id, kind: 'global' })
                        }
                      >
                        <div className="font-semibold">{row.pattern_id}</div>
                        <div className="text-sm tabular-nums">
                          N {row.n} · ROI{' '}
                          <span style={{ color: roiColor(row.roi_pct ?? 0) }}>
                            {formatRoiPct(row.roi_pct)}
                          </span>
                          {row.profit_1u != null ? ` · P ${formatNum(row.profit_1u, 1)}` : ''}
                        </div>
                      </button>
                    ) : (
                      <div className="mt-1 text-sm" style={{ color: 'var(--lab-muted)' }}>
                        —
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            {Array.isArray(insights.four_of_four_positive) &&
            (insights.four_of_four_positive as unknown[]).length > 0 ? (
              <div className="mt-4">
                <div className="text-xs font-semibold uppercase" style={{ color: 'var(--lab-muted)' }}>
                  4/4 stagioni positive
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {(insights.four_of_four_positive as Array<{ pattern_id: string; n: number; roi_pct: number }>).map(
                    (r) => (
                      <button
                        key={r.pattern_id}
                        type="button"
                        className="lab-btn-ghost text-xs"
                        onClick={() => setDrawer({ id: r.pattern_id, kind: 'global' })}
                      >
                        {r.pattern_id} · N {r.n} · {formatRoiPct(r.roi_pct)}
                      </button>
                    ),
                  )}
                </div>
              </div>
            ) : null}
          </div>

          <PatternLeagueHeatmap
            heatmap={data.heatmap}
            onSelectCell={(pid) => setDrawer({ id: pid, kind: 'global' })}
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="lab-card p-4">
              <div className="mb-3 text-sm font-semibold">Specializzazioni da validare</div>
              <div className="space-y-3">
                {data.specializations.map((s) => (
                  <div key={s.id} className="rounded-xl p-3" style={{ background: 'var(--lab-surface-2)' }}>
                    <div className="flex items-center justify-between gap-2">
                      <button
                        type="button"
                        className="font-semibold"
                        onClick={() => setDrawer({ id: s.pattern_id, kind: 'global' })}
                      >
                        {s.pattern_id} × {s.competition}
                      </button>
                      <span className="text-[10px] uppercase" style={{ color: 'var(--lab-cyan)' }}>
                        {s.label}
                      </span>
                    </div>
                    <div className="mt-2 text-sm tabular-nums">
                      N {s.metrics?.n ?? 0} · ROI{' '}
                      <span style={{ color: roiColor(s.metrics?.roi_pct ?? 0) }}>
                        {formatRoiPct(s.metrics?.roi_pct)}
                      </span>{' '}
                      · P {formatNum(s.metrics?.profit_1u, 1)} ·{' '}
                      {s.metrics?.stability_label || '—'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="lab-card p-4">
              <div className="mb-3 text-sm font-semibold">Possibili incompatibilità</div>
              <div className="space-y-3">
                {data.incompatibilities.map((s) => (
                  <div key={s.id} className="rounded-xl p-3" style={{ background: 'var(--lab-surface-2)' }}>
                    <div className="flex items-center justify-between gap-2">
                      <button
                        type="button"
                        className="font-semibold"
                        onClick={() => setDrawer({ id: s.pattern_id, kind: 'global' })}
                      >
                        {s.pattern_id} × {s.competition}
                      </button>
                      <span className="text-[10px] uppercase" style={{ color: 'var(--lab-err)' }}>
                        {s.label}
                      </span>
                    </div>
                    <div className="mt-2 text-sm tabular-nums">
                      N {s.metrics?.n ?? 0} · ROI{' '}
                      <span style={{ color: roiColor(s.metrics?.roi_pct ?? 0) }}>
                        {formatRoiPct(s.metrics?.roi_pct)}
                      </span>{' '}
                      · {s.negative_label || '—'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {data && sub === 'league' && (
        <div className="space-y-6" data-testid="lpa-panel-league">
          <div className="lab-card overflow-x-auto p-4">
            <div className="mb-3 text-sm font-semibold">Overview 16 campionati (match-level)</div>
            <table className="lab-table w-full min-w-[800px] text-sm">
              <thead>
                <tr>
                  <th>Campionato</th>
                  <th>Match</th>
                  <th>HOME %</th>
                  <th>DRAW %</th>
                  <th>AWAY %</th>
                  <th>O2.5 %</th>
                  <th>U2.5 %</th>
                  <th>Avg FT goals</th>
                </tr>
              </thead>
              <tbody>
                {data.competition_regimes_overview.map((L) => (
                  <tr
                    key={L.competition}
                    className="cursor-pointer hover:bg-white/5"
                    onClick={() => setSelectedLeague(L.competition)}
                  >
                    <td className="font-medium">{L.competition}</td>
                    <td className="tabular-nums">{L.total?.matches ?? 0}</td>
                    <td className="tabular-nums">{formatNum(L.total?.home_pct, 1)}%</td>
                    <td className="tabular-nums">{formatNum(L.total?.draw_pct, 1)}%</td>
                    <td className="tabular-nums">{formatNum(L.total?.away_pct, 1)}%</td>
                    <td className="tabular-nums">{formatNum(L.total?.over_25_pct, 1)}%</td>
                    <td className="tabular-nums">{formatNum(L.total?.under_25_pct, 1)}%</td>
                    <td className="tabular-nums">{formatNum(L.total?.avg_ft_goals, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap gap-2" data-testid="lpa-league-chips">
            {data.competition_regimes_overview.map((L) => (
              <button
                key={L.competition}
                type="button"
                className={`lab-tab rounded-lg px-3 py-1.5 text-xs ${
                  selectedLeague === L.competition ? 'lab-tab-active' : ''
                }`}
                onClick={() => setSelectedLeague(L.competition)}
              >
                {L.competition}
              </button>
            ))}
          </div>

          {leagueLoading && <p style={{ color: 'var(--lab-muted)' }}>Caricamento lega…</p>}
          {leagueDetail && (
            <div className="space-y-4">
              <div className="lab-card p-4">
                <div className="text-sm font-semibold">
                  League Overview · {leagueDetail.competition}
                </div>
                <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {SEASONS.map((s, i) => {
                    const row = leagueDetail.league_overview.by_season?.[s] as
                      | Record<string, number | null>
                      | undefined
                    return (
                      <div key={s} className="rounded-xl p-3" style={{ background: 'var(--lab-surface-2)' }}>
                        <div className="text-xs font-semibold">{SEASON_SHORT[i]}</div>
                        <div className="mt-1 text-xs tabular-nums" style={{ color: 'var(--lab-muted)' }}>
                          Match {row?.matches ?? 0} · H {formatNum(row?.home_pct as number, 1)}% ·
                          D {formatNum(row?.draw_pct as number, 1)}% · A{' '}
                          {formatNum(row?.away_pct as number, 1)}%
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="lab-card overflow-x-auto p-4">
                <div className="mb-3 text-sm font-semibold">
                  P01–P12 in {leagueDetail.competition}
                </div>
                <table className="lab-table w-full min-w-[900px] text-sm">
                  <thead>
                    <tr>
                      <th>Pattern</th>
                      {SEASON_SHORT.map((s) => (
                        <th key={s}>{s}</th>
                      ))}
                      <th>Total N</th>
                      <th>Profit</th>
                      <th>ROI</th>
                      <th>+</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leagueDetail.patterns.map((p) => (
                      <tr
                        key={p.pattern_id}
                        className="cursor-pointer hover:bg-white/5"
                        onClick={() => setDrawer({ id: p.pattern_id, kind: 'global' })}
                      >
                        <td className="font-medium">{p.pattern_id}</td>
                        {SEASONS.map((s) => (
                          <td key={s}>
                            <SeasonCell cell={p.by_season?.[s]} />
                          </td>
                        ))}
                        <td className="tabular-nums">{p.total?.n ?? 0}</td>
                        <td className="tabular-nums">{formatNum(p.total?.profit_1u, 1)}</td>
                        <td
                          className="tabular-nums font-medium"
                          style={{ color: roiColor(p.total?.roi_pct ?? 0) }}
                        >
                          {formatRoiPct(p.total?.roi_pct)}
                        </td>
                        <td className="text-xs">{p.total?.stability_label || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {data && sub === 'native' && (
        <div className="space-y-4" data-testid="lpa-panel-native">
          <p className="text-sm" style={{ color: 'var(--lab-muted)' }}>
            LN01–LN10 sono candidati league-native separati da P01–P12. Status:{' '}
            <strong>candidate_oos_2025_26</strong>. Prima OOS vera: 2025/26 (non usata).
          </p>
          <div className="lab-card overflow-x-auto p-4">
            <table className="lab-table w-full min-w-[900px] text-sm">
              <thead>
                <tr>
                  <th>LN</th>
                  <th>Campionato</th>
                  {SEASON_SHORT.map((s) => (
                    <th key={s}>{s}</th>
                  ))}
                  <th>TOTALE</th>
                </tr>
              </thead>
              <tbody>
                {data.league_native.map((p) => (
                  <tr
                    key={p.pattern_id}
                    className="cursor-pointer hover:bg-white/5"
                    onClick={() => setDrawer({ id: p.pattern_id, kind: 'native' })}
                  >
                    <td>
                      <div className="font-medium">{p.pattern_id}</div>
                      <div className="flex items-center gap-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
                        {p.human_title || p.human?.human_title}
                        <LabInfoTooltip
                          title="Cosa identifica"
                          text={p.human?.long_explanation || p.human?.short_explanation || ''}
                        />
                      </div>
                    </td>
                    <td>{p.competition}</td>
                    {SEASONS.map((s) => (
                      <td key={s}>
                        <SeasonCell cell={p.by_season?.[s]} />
                      </td>
                    ))}
                    <td>
                      <TotalCell total={p.total} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {data && (
        <div className="lab-card p-4" data-testid="lpa-methodology">
          <button
            type="button"
            className="flex w-full items-center justify-between text-left text-sm font-semibold"
            onClick={() => setMethodOpen((v) => !v)}
          >
            METODOLOGIA
            <span style={{ color: 'var(--lab-muted)' }}>{methodOpen ? '▾' : '▸'}</span>
          </button>
          {methodOpen && (
            <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
              <div>
                <dt style={{ color: 'var(--lab-muted)' }}>Dataset</dt>
                <dd>2021/22 - 2024/25</dd>
              </div>
              <div>
                <dt style={{ color: 'var(--lab-muted)' }}>Run</dt>
                <dd>{(data.metadata.source_run_ids || []).join(' / ')}</dd>
              </div>
              <div>
                <dt style={{ color: 'var(--lab-muted)' }}>Global Patterns</dt>
                <dd>P01-P12</dd>
              </div>
              <div>
                <dt style={{ color: 'var(--lab-muted)' }}>League-native</dt>
                <dd>LN01-LN10</dd>
              </div>
              <div>
                <dt style={{ color: 'var(--lab-muted)' }}>LN discovery</dt>
                <dd>21/22 - 23/24</dd>
              </div>
              <div>
                <dt style={{ color: 'var(--lab-muted)' }}>Internal validation</dt>
                <dd>24/25</dd>
              </div>
              <div>
                <dt style={{ color: 'var(--lab-muted)' }}>First true OOS</dt>
                <dd>25/26</dd>
              </div>
              <div>
                <dt style={{ color: 'var(--lab-muted)' }}>2025/26</dt>
                <dd data-testid="lpa-method-oos-not-used">NOT USED</dd>
              </div>
              <div>
                <dt style={{ color: 'var(--lab-muted)' }}>Economic unit</dt>
                <dd>1u flat stake</dd>
              </div>
              <div>
                <dt style={{ color: 'var(--lab-muted)' }}>Snapshot</dt>
                <dd>
                  #{data.metadata.snapshot_id} · {data.metadata.analysis_version}
                </dd>
              </div>
            </dl>
          )}
        </div>
      )}

      <PatternDetailDrawer
        patternId={drawer?.id ?? null}
        kind={drawer?.kind ?? 'global'}
        onClose={() => setDrawer(null)}
      />
    </div>
  )
}
