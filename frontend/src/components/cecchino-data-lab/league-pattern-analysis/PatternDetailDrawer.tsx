import { useEffect, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import {
  fetchLeaguePatternAnalysisNative,
  fetchLeaguePatternAnalysisPattern,
  formatNum,
  formatPct01,
  formatRoiPct,
  type LpaPatternDetail,
} from '../../../lib/leaguePatternAnalysisApi'
import { roiColor } from '../overview/overviewTheme'
import { LabInfoTooltip } from './LabInfoTooltip'

type Props = {
  patternId: string | null
  kind: 'global' | 'native'
  onClose: () => void
}

const SEASON_ORDER = ['2021/2022', '2022/2023', '2023/2024', '2024/2025']

export function PatternDetailDrawer({ patternId, kind, onClose }: Props) {
  const [detail, setDetail] = useState<LpaPatternDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<'n' | 'roi_pct' | 'profit_1u' | 'positive_seasons'>(
    'roi_pct',
  )

  useEffect(() => {
    if (!patternId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    const loader =
      kind === 'native'
        ? fetchLeaguePatternAnalysisNative(patternId)
        : fetchLeaguePatternAnalysisPattern(patternId)
    loader
      .then((d) => {
        if (!cancelled) {
          setDetail(d)
          setLoading(false)
        }
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setError(e.message || 'Errore caricamento')
          setDetail(null)
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [patternId, kind])

  if (patternId == null) return null

  const p = detail?.pattern
  const human = p?.human
  const total = p?.total

  const chartOption = {
    backgroundColor: 'transparent',
    tooltip: { backgroundColor: '#0f1c2c', textStyle: { color: '#e8eef5' } },
    grid: { left: 48, right: 16, top: 24, bottom: 32 },
    xAxis: {
      type: 'category',
      data: SEASON_ORDER.map((s) => s.replace('20', '').replace('/20', '/')),
      axisLabel: { color: '#8aa0b5' },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#8aa0b5', formatter: '{value}%' },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
    },
    series: [
      {
        type: 'bar',
        data: SEASON_ORDER.map((s) => {
          const v = p?.by_season?.[s]?.roi_pct
          return {
            value: v ?? null,
            itemStyle: { color: roiColor(v ?? 0) },
          }
        }),
      },
    ],
  }

  const comps = Object.values(p?.by_competition || {}).sort((a, b) => {
    const av = Number(a.total?.[sortKey] ?? -Infinity)
    const bv = Number(b.total?.[sortKey] ?? -Infinity)
    return bv - av
  })

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/45" onClick={onClose}>
      <aside
        className="flex h-full w-full max-w-xl flex-col overflow-y-auto border-l shadow-2xl"
        style={{
          background: 'var(--lab-bg-elevated)',
          borderColor: 'var(--lab-border)',
          color: 'var(--lab-text)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="sticky top-0 z-10 flex items-center justify-between border-b px-5 py-4"
          style={{ background: 'var(--lab-surface)', borderColor: 'var(--lab-border)' }}
        >
          <div>
            <div className="text-xs uppercase tracking-wider" style={{ color: 'var(--lab-muted)' }}>
              {kind === 'native' ? 'League-Native' : 'Global Pattern'}
            </div>
            <div className="text-lg font-semibold">{patternId}</div>
          </div>
          <button type="button" className="lab-btn-ghost" onClick={onClose}>
            Chiudi
          </button>
        </div>

        <div className="space-y-5 p-5">
          {loading && <p style={{ color: 'var(--lab-muted)' }}>Caricamento…</p>}
          {error && <p style={{ color: 'var(--lab-err)' }}>{error}</p>}
          {p && (
            <>
              <div>
                <h3 className="text-base font-semibold">
                  {human?.human_title || p.human_title || p.label}
                </h3>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                  <code className="rounded px-2 py-1 text-xs" style={{ background: 'var(--lab-surface-2)' }}>
                    {human?.technical_formula || '—'}
                  </code>
                  <LabInfoTooltip
                    title="Cosa identifica"
                    text={human?.long_explanation || human?.short_explanation || ''}
                  />
                </div>
                <p className="mt-2 text-sm" style={{ color: 'var(--lab-muted)' }}>
                  {human?.short_explanation}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {(
                  [
                    ['N totale', String(total?.n ?? 0)],
                    ['Profit', `${formatNum(total?.profit_1u, 2)}u`],
                    ['ROI pooled', formatRoiPct(total?.roi_pct)],
                    ['Stabilità', total?.stability_label || '—'],
                  ] as Array<[string, string]>
                ).map(([label, value]) => (
                  <div key={label} className="lab-card p-3">
                    <div className="text-[10px] uppercase" style={{ color: 'var(--lab-muted)' }}>
                      {label}
                    </div>
                    <div
                      className="mt-1 text-lg font-semibold tabular-nums"
                      style={{
                        color:
                          label === 'ROI pooled' ? roiColor(total?.roi_pct ?? 0) : undefined,
                      }}
                    >
                      {value}
                    </div>
                  </div>
                ))}
              </div>

              <div className="lab-card p-3">
                <div className="mb-2 text-sm font-semibold">ROI per stagione</div>
                <ReactECharts option={chartOption} style={{ height: 200 }} />
              </div>

              <div className="overflow-x-auto">
                <table className="lab-table w-full text-sm">
                  <thead>
                    <tr>
                      <th>Season</th>
                      <th>N</th>
                      <th>W</th>
                      <th>L</th>
                      <th>Void</th>
                      <th>WR</th>
                      <th>Avg Odds</th>
                      <th>Profit</th>
                      <th>ROI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {SEASON_ORDER.map((seasonKey) => {
                      const s = p?.by_season?.[seasonKey]
                      if (!s) return null
                      return (
                      <tr key={seasonKey}>
                        <td>{s.season_short || seasonKey}</td>
                        <td className="tabular-nums">{s.n ?? 0}</td>
                        <td className="tabular-nums">{s.wins ?? 0}</td>
                        <td className="tabular-nums">{s.losses ?? 0}</td>
                        <td className="tabular-nums">{s.void ?? 0}</td>
                        <td className="tabular-nums">{formatPct01(s.win_rate)}</td>
                        <td className="tabular-nums">{formatNum(s.avg_odds, 2)}</td>
                        <td className="tabular-nums">{formatNum(s.profit_1u, 2)}</td>
                        <td
                          className="tabular-nums font-medium"
                          style={{ color: roiColor(s.roi_pct ?? 0) }}
                        >
                          {formatRoiPct(s.roi_pct)}
                        </td>
                      </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {kind === 'global' && comps.length > 0 && (
                <div>
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-semibold">Performance per campionato</div>
                    <select
                      className="lab-input text-xs"
                      value={sortKey}
                      onChange={(e) =>
                        setSortKey(e.target.value as typeof sortKey)
                      }
                    >
                      <option value="n">Ordina per N</option>
                      <option value="roi_pct">Ordina per ROI</option>
                      <option value="profit_1u">Ordina per profit</option>
                      <option value="positive_seasons">Ordina per stagioni +</option>
                    </select>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="lab-table w-full text-sm">
                      <thead>
                        <tr>
                          <th>Campionato</th>
                          <th>N</th>
                          <th>ROI</th>
                          <th>Profit</th>
                          <th>Stabilità</th>
                        </tr>
                      </thead>
                      <tbody>
                        {comps.map((c) => (
                          <tr key={c.competition}>
                            <td>{c.competition}</td>
                            <td className="tabular-nums">{c.total?.n ?? 0}</td>
                            <td
                              className="tabular-nums"
                              style={{ color: roiColor(c.total?.roi_pct ?? 0) }}
                            >
                              {formatRoiPct(c.total?.roi_pct)}
                            </td>
                            <td className="tabular-nums">
                              {formatNum(c.total?.profit_1u, 2)}
                            </td>
                            <td>{c.total?.stability_label || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  )
}
