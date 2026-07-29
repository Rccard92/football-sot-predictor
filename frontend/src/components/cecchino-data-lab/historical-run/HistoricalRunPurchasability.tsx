import ReactECharts from 'echarts-for-react'
import {
  formatNullableNumber,
  purchasabilityGateDisplayLabel,
  type HistoricalPurchasabilityDecision,
  type HistoricalPurchasabilityScoreRow,
  type HistoricalRunPurchasabilityAnalytics,
} from '../../../lib/cecchinoLabApi'

type Props = { data: HistoricalRunPurchasabilityAnalytics }

type PurchRow = Record<string, unknown> & {
  keys?: string[]
  market_key?: string
  band?: string
  sample_size?: number
  hit_rate?: number | null
  real_roi_pct?: number | null
  real_quote_count?: number
  derived_quote_count?: number
}

const DECISION_GROUP_LABELS: Record<string, string> = {
  ONE_X_TWO_REAL: '1X2 (quote reali)',
  GOALS_FT_2_5_REAL: 'Goal 2.5 (quote reali)',
  DOUBLE_CHANCE_DERIVED: 'Doppia chance (sintetica)',
}

function rowKeys(row: PurchRow): string[] {
  return Array.isArray(row.keys) ? row.keys.map(String) : []
}

function oddsLabel(row: HistoricalPurchasabilityScoreRow): string {
  if (row.real_book_odds != null) return `${row.real_book_odds} (reale)`
  if (row.derived_odds != null) return `${row.derived_odds} (derivata)`
  return '—'
}

export function HistoricalRunPurchasability({ data }: Props) {
  const byMarket = (data.by_market || []) as PurchRow[]
  const markets = [...new Set(byMarket.map((r) => String(rowKeys(r)[0] ?? r.market_key ?? '')))]
  const bands = data.bands
  const gate = data.gate
  const blockedLabel = gate?.blocked_label || 'Bloccato dal gate'
  const warningText =
    data.observational_warning ||
    "L'Acquistabilità storica è un modulo osservazionale. Il report descrive la formula congelata del Run #3 e non costituisce una strategia o una modifica della formula operativa."

  const scoreRows: HistoricalPurchasabilityScoreRow[] = Object.values(
    data.scores_by_market || {},
  ).flat()

  const heatData: Array<[number, number, number | null, PurchRow]> = []
  for (const row of byMarket) {
    const keys = rowKeys(row)
    const mk = String(keys[0] ?? row.market_key ?? '')
    const band = String(keys[1] ?? row.band ?? '')
    const x = bands.indexOf(band)
    const y = markets.indexOf(mk)
    if (x < 0 || y < 0) continue
    const n = Number(row.sample_size ?? 0)
    heatData.push([x, y, n > 0 ? n : null, row])
  }

  const heatOption = {
    backgroundColor: 'transparent',
    tooltip: {
      formatter: (p: { data: [number, number, number | null, PurchRow] }) => {
        const c = p.data[3]
        const keys = rowKeys(c)
        const roi = c.real_roi_pct
        return [
          `<b>${String(keys[0] ?? '')} · ${String(keys[1] ?? '')}</b>`,
          `N ${String(c.sample_size ?? 0)}`,
          `hit ${c.hit_rate != null ? `${(Number(c.hit_rate) * 100).toFixed(1)}%` : '—'}`,
          `ROI reale ${roi != null ? `${roi}%` : '—'}`,
          `reali ${String(c.real_quote_count ?? 0)} · derivate ${String(c.derived_quote_count ?? 0)}`,
        ].join('<br/>')
      },
    },
    grid: { left: 90, right: 20, top: 20, bottom: 60 },
    xAxis: {
      type: 'category',
      data: bands,
      axisLabel: { color: '#8aa0b5', rotate: 35, fontSize: 10 },
    },
    yAxis: {
      type: 'category',
      data: markets,
      axisLabel: { color: '#8aa0b5', fontSize: 10 },
    },
    visualMap: {
      min: 0,
      max: Math.max(1, ...heatData.map((d) => d[2] ?? 0)),
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      textStyle: { color: '#8aa0b5' },
      inRange: { color: ['#122033', '#2a7a55', '#3dd68c'] },
    },
    series: [{ type: 'heatmap', data: heatData }],
  }

  const monthEntries = Object.entries(data.drift?.by_month || {}).sort(([a], [b]) =>
    a.localeCompare(b),
  )
  const driftOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['Score zero %', 'Gate accepted %', 'Score ≥80 %', 'Sample norm (media)'],
      textStyle: { color: '#8aa0b5', fontSize: 10 },
      bottom: 0,
    },
    grid: { left: 48, right: 48, top: 24, bottom: 56 },
    xAxis: {
      type: 'category',
      data: monthEntries.map(([m]) => m),
      axisLabel: { color: '#8aa0b5', rotate: 35, fontSize: 10 },
    },
    yAxis: [
      {
        type: 'value',
        name: '%',
        axisLabel: { color: '#8aa0b5' },
        splitLine: { lineStyle: { color: 'rgba(120,190,220,0.08)' } },
      },
      {
        type: 'value',
        name: 'N',
        axisLabel: { color: '#8aa0b5' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'Score zero %',
        type: 'line',
        data: monthEntries.map(([, b]) => b.score_zero_pct ?? null),
        itemStyle: { color: '#e07a5f' },
      },
      {
        name: 'Gate accepted %',
        type: 'line',
        data: monthEntries.map(([, b]) => b.gate_accepted_pct ?? null),
        itemStyle: { color: '#3dd68c' },
      },
      {
        name: 'Score ≥80 %',
        type: 'line',
        data: monthEntries.map(([, b]) => b.score_ge_80_pct ?? null),
        itemStyle: { color: '#6cb6ff' },
      },
      {
        name: 'Sample norm (media)',
        type: 'bar',
        yAxisIndex: 1,
        data: monthEntries.map(([, b]) => b.mean_normalization_sample_size ?? null),
        itemStyle: { color: 'rgba(138,160,181,0.35)' },
      },
    ],
  }

  const profileHashWarning =
    (data.drift?.overall?.distinct_profile_hashes ?? 0) > 1
      ? 'Attenzione: più profili di normalizzazione distinti — la scala può cambiare distribuzione nel tempo.'
      : null

  const decisionGroups = Object.entries(data.decisions_by_group || {})

  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">Acquistabilità Lab</h3>
      <p
        className="mb-3 rounded-lg border px-3 py-2 text-xs"
        style={{ borderColor: 'var(--lab-warn)', color: 'var(--lab-warn)', background: 'rgba(224,122,95,0.08)' }}
        data-testid="purch-observational-warning"
      >
        {warningText}
      </p>
      <p className="mb-2 text-xs text-[var(--lab-muted)]">
        Completi {data.complete_count} · parziali {data.partial_count} · N/D{' '}
        {data.unavailable_count}
        {data.evaluations_total != null ? ` · valutazioni ${data.evaluations_total}` : ''}.
      </p>

      {/* 1. Punteggi per mercato */}
      <h4 className="mb-2 mt-4 text-sm font-semibold">1. Punteggi per mercato</h4>
      <p className="mb-2 text-xs text-[var(--lab-muted)]">
        Heatmap legacy mercato × fascia (diagnostica). Sotto: score finale persistito, gate e
        diagnostico pre-gate.
      </p>
      <div
        className="mb-3 rounded-xl border p-2"
        style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
      >
        <ReactECharts option={heatOption} style={{ height: 320 }} />
      </div>
      {scoreRows.length > 0 ? (
        <div className="lab-table-wrap mb-4 overflow-x-auto">
          <table className="lab-table w-full text-xs">
            <thead>
              <tr>
                <th>Mercato</th>
                <th>Gate</th>
                <th>Score finale</th>
                <th>Diagnostico pre-gate</th>
                <th>Rating</th>
                <th>Edge</th>
                <th>Vantaggio</th>
                <th>Quota</th>
                <th>Risultato</th>
                <th>Profitto</th>
              </tr>
            </thead>
            <tbody>
              {scoreRows.slice(0, 60).map((r, i) => {
                const gateLabel = purchasabilityGateDisplayLabel(r.gate_status, r.score_class)
                const isBlocked = Boolean(
                  r.gate_status && String(r.gate_status).startsWith('rejected_'),
                )
                return (
                  <tr key={`${r.market_key}-${r.kickoff_at}-${i}`}>
                    <td>{r.market_key ?? '—'}</td>
                    <td data-testid={isBlocked ? 'gate-blocked-label' : undefined}>
                      {isBlocked ? blockedLabel : gateLabel}
                    </td>
                    <td>{formatNullableNumber(r.final_score, 1)}</td>
                    <td>{formatNullableNumber(r.diagnostic_ungated_score, 1)}</td>
                    <td>{formatNullableNumber(r.rating, 0)}</td>
                    <td>{formatNullableNumber(r.edge_pct, 2)}</td>
                    <td>{formatNullableNumber(r.vantaggio_prob, 3)}</td>
                    <td>{oddsLabel(r)}</td>
                    <td>
                      {r.won == null ? '—' : r.won ? 'W' : 'L'}
                    </td>
                    <td>
                      {r.profit_1u_real != null
                        ? formatNullableNumber(r.profit_1u_real, 2)
                        : r.profit_1u_synthetic != null
                          ? `${formatNullableNumber(r.profit_1u_synthetic, 2)} (sint.)`
                          : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {/* 2. Gate */}
      <h4 className="mb-2 mt-4 text-sm font-semibold">2. Gate</h4>
      <p className="mb-2 text-xs text-[var(--lab-muted)]">
        Accettati {gate?.accepted ?? '—'} · Rifiutati {gate?.rejected ?? '—'} · Score zero da gate{' '}
        {gate?.gate_rejected_zero_count ?? '—'}. Etichetta obbligatoria:{' '}
        <strong>{blockedLabel}</strong> (mai «Molto Bassa» per gate rejected).
      </p>
      {gate?.gate_reason_counts && Object.keys(gate.gate_reason_counts).length > 0 ? (
        <ul className="mb-3 list-inside list-disc text-xs text-[var(--lab-muted)]">
          {Object.entries(gate.gate_reason_counts).map(([reason, n]) => (
            <li key={reason}>
              {reason}: {n}
            </li>
          ))}
        </ul>
      ) : null}
      {gate?.gate_status_by_market ? (
        <div className="lab-table-wrap mb-4 overflow-x-auto">
          <table className="lab-table w-full text-xs">
            <thead>
              <tr>
                <th>Mercato</th>
                <th>Stati gate</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(gate.gate_status_by_market).map(([mk, counts]) => (
                <tr key={mk}>
                  <td>{mk}</td>
                  <td>
                    {Object.entries(counts)
                      .map(([st, n]) => `${st}: ${n}`)
                      .join(' · ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {/* 3. Scelta per famiglia */}
      <h4 className="mb-2 mt-4 text-sm font-semibold">3. Scelta per famiglia</h4>
      <p className="mb-2 text-xs text-[var(--lab-muted)]">
        Solo diagnostica: massimo score persistito nella famiglia. Non è una strategia produttiva.
      </p>
      {decisionGroups.length === 0 ? (
        <p className="mb-3 text-xs text-[var(--lab-muted)]">Nessuna decisione disponibile.</p>
      ) : (
        decisionGroups.map(([group, rows]) => (
          <div key={group} className="mb-4">
            <h5 className="mb-1 text-xs font-medium">
              {DECISION_GROUP_LABELS[group] || group}
              {group === 'DOUBLE_CHANCE_DERIVED' ? ' · performance sintetica' : ''}
            </h5>
            <div className="lab-table-wrap overflow-x-auto">
              <table className="lab-table w-full text-xs">
                <thead>
                  <tr>
                    <th>Kickoff</th>
                    <th>Selezionato</th>
                    <th>Score</th>
                    <th>Gate</th>
                    <th>Pareggio</th>
                    <th>Won</th>
                    <th>Profitto</th>
                  </tr>
                </thead>
                <tbody>
                  {(rows as HistoricalPurchasabilityDecision[]).slice(0, 25).map((d) => (
                    <tr key={d.decision_id}>
                      <td>{d.kickoff_at ? String(d.kickoff_at).slice(0, 16) : '—'}</td>
                      <td>
                        {d.selected_market_key ?? (
                          <span data-testid="decision-no-selection">Nessuna selezione</span>
                        )}
                      </td>
                      <td>{formatNullableNumber(d.selected_score, 1)}</td>
                      <td>
                        {d.selected_gate_status
                          ? purchasabilityGateDisplayLabel(d.selected_gate_status, null)
                          : '—'}
                      </td>
                      <td>
                        {d.selection_tied
                          ? `Sì (${(d.tied_market_keys || []).join(', ')})`
                          : 'No'}
                      </td>
                      <td>
                        {d.selected_won == null ? '—' : d.selected_won ? 'W' : 'L'}
                      </td>
                      <td>
                        {d.selected_profit_1u_real != null
                          ? formatNullableNumber(d.selected_profit_1u_real, 2)
                          : d.selected_profit_1u_synthetic != null
                            ? `${formatNullableNumber(d.selected_profit_1u_synthetic, 2)} (sint.)`
                            : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))
      )}

      {/* 4. Drift */}
      <h4 className="mb-2 mt-4 text-sm font-semibold">4. Drift normalizzazione</h4>
      {profileHashWarning ? (
        <p className="mb-2 text-xs" style={{ color: 'var(--lab-warn)' }}>
          {profileHashWarning}
        </p>
      ) : null}
      <p className="mb-2 text-xs text-[var(--lab-muted)]">
        Profili distinti: {data.drift?.overall?.distinct_profile_hashes ?? '—'} · sample norm medio:{' '}
        {formatNullableNumber(data.drift?.overall?.mean_normalization_sample_size ?? null, 1)}
      </p>
      {monthEntries.length > 0 ? (
        <div
          className="mb-3 rounded-xl border p-2"
          style={{ borderColor: 'var(--lab-border)', background: 'var(--lab-surface)' }}
        >
          <ReactECharts option={driftOption} style={{ height: 260 }} />
        </div>
      ) : (
        <p className="text-xs text-[var(--lab-muted)]">Nessun dato drift mensile.</p>
      )}
    </section>
  )
}
