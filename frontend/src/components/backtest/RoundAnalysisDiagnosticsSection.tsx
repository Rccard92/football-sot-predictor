import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getRoundAnalysisDiagnostics,
  getRoundAnalysisDiagnosticsReportJson,
  type DiagnosticsModelBlock,
  type RoundAnalysisDiagnostics,
} from '../../lib/api'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'sot', label: 'Fasce SOT' },
  { id: 'lines', label: 'Linee' },
  { id: 'edge', label: 'Edge' },
  { id: 'advice', label: 'GIOCA / NON GIOCARE' },
  { id: 'macro', label: 'Macro v2.1' },
  { id: 'critical', label: 'Partite critiche' },
] as const

type TabId = (typeof TABS)[number]['id']

type Props = {
  competitionId: number | null
  seasonYear: number
  reloadToken: number
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v.toFixed(1)}%`
}

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null) return '—'
  return v.toFixed(digits)
}

function hitDisplay(s: { wins?: number; losses?: number; hit_rate?: number | null } | undefined): string {
  if (!s) return '—'
  const w = s.wins ?? 0
  const l = s.losses ?? 0
  if (w + l === 0) return '—'
  return `${w}/${w + l} · ${fmtPct(s.hit_rate)}`
}

function OverviewTab({ models }: { models: Record<string, DiagnosticsModelBlock> }) {
  const entries = Object.values(models)
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {entries.map((m) => {
        const o = m.overview
        return (
          <div key={o.model_key} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="font-semibold text-slate-900">{o.label}</h3>
            <dl className="mt-2 space-y-1 text-xs text-slate-700">
              <div className="flex justify-between">
                <dt>Cauta consigliata</dt>
                <dd>{hitDisplay(o.cautious_advised)}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Aggressiva consigliata</dt>
                <dd>{hitDisplay(o.aggressive_advised)}</dd>
              </div>
              <div className="flex justify-between">
                <dt>MAE</dt>
                <dd>{fmtNum(o.mae)}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Bias</dt>
                <dd>{fmtNum(o.bias)}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Low / Med / High</dt>
                <dd>
                  {['low_total', 'medium_total', 'high_total']
                    .map((b) => fmtPct(o.sot_buckets_summary?.[b]?.hit_rate_cautious_advised))
                    .join(' · ')}
                </dd>
              </div>
            </dl>
          </div>
        )
      })}
    </div>
  )
}

function SotBucketsTab({ models }: { models: Record<string, DiagnosticsModelBlock> }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-xs">
        <thead>
          <tr className="border-b border-slate-200 text-left text-slate-600">
            <th className="px-2 py-2">Modello</th>
            <th className="px-2 py-2">Low</th>
            <th className="px-2 py-2">Medium</th>
            <th className="px-2 py-2">High</th>
            <th className="px-2 py-2">MAE</th>
            <th className="px-2 py-2">Bias</th>
          </tr>
        </thead>
        <tbody>
          {Object.values(models).map((m) => {
            const o = m.overview
            const sb = m.sot_buckets
            return (
              <tr key={o.model_key} className="border-b border-slate-100">
                <td className="px-2 py-2 font-medium">{o.label}</td>
                <td className="px-2 py-2">{hitDisplay(sb.low_total?.advised_cautious)}</td>
                <td className="px-2 py-2">{hitDisplay(sb.medium_total?.advised_cautious)}</td>
                <td className="px-2 py-2">{hitDisplay(sb.high_total?.advised_cautious)}</td>
                <td className="px-2 py-2">{fmtNum(o.mae)}</td>
                <td className="px-2 py-2">{fmtNum(o.bias)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function LinesTab({ models }: { models: Record<string, DiagnosticsModelBlock> }) {
  const modelEntries = Object.values(models)
  const lines = modelEntries[0]?.lines?.aggressive
    ? Object.keys(modelEntries[0].lines.aggressive)
    : []
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-xs">
        <thead>
          <tr className="border-b border-slate-200 text-left text-slate-600">
            <th className="px-2 py-2">Modello</th>
            <th className="px-2 py-2">Modo</th>
            {lines.map((ln) => (
              <th key={ln} className="px-2 py-2">
                {ln}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {modelEntries.flatMap((m) =>
            (['aggressive', 'cautious'] as const).map((mode) => (
              <tr key={`${m.overview.model_key}-${mode}`} className="border-b border-slate-100">
                <td className="px-2 py-2 font-medium">{m.overview.label}</td>
                <td className="px-2 py-2 capitalize">{mode === 'aggressive' ? 'Aggressiva' : 'Cauta'}</td>
                {lines.map((ln) => (
                  <td key={ln} className="px-2 py-2">
                    {hitDisplay(m.lines[mode]?.[ln]?.advised_only)}
                  </td>
                ))}
              </tr>
            )),
          )}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500">Hit rate consigliato (solo GIOCA) per linea.</p>
    </div>
  )
}

function EdgeTab({ models }: { models: Record<string, DiagnosticsModelBlock> }) {
  const buckets = ['edge_low', 'edge_medium', 'edge_high']
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-xs">
        <thead>
          <tr className="border-b border-slate-200 text-left text-slate-600">
            <th className="px-2 py-2">Modello</th>
            <th className="px-2 py-2">Modo</th>
            {buckets.map((b) => (
              <th key={b} className="px-2 py-2">
                {b.replace('edge_', '')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Object.values(models).flatMap((m) =>
            (['aggressive', 'cautious'] as const).map((mode) => (
              <tr key={`${m.overview.model_key}-${mode}`} className="border-b border-slate-100">
                <td className="px-2 py-2 font-medium">{m.overview.label}</td>
                <td className="px-2 py-2 capitalize">{mode === 'aggressive' ? 'Aggressiva' : 'Cauta'}</td>
                {buckets.map((b) => (
                  <td key={b} className="px-2 py-2">
                    {hitDisplay(m.edge_buckets[mode]?.[b])}
                  </td>
                ))}
              </tr>
            )),
          )}
        </tbody>
      </table>
    </div>
  )
}

function AdviceTab({ models }: { models: Record<string, DiagnosticsModelBlock> }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-xs">
        <thead>
          <tr className="border-b border-slate-200 text-left text-slate-600">
            <th className="px-2 py-2">Modello</th>
            <th className="px-2 py-2">Modo</th>
            <th className="px-2 py-2">GIOCA hit</th>
            <th className="px-2 py-2">Evitate perdite</th>
            <th className="px-2 py-2">Vittorie perse</th>
            <th className="px-2 py-2">NON GIOCA avrebbe vinto</th>
            <th className="px-2 py-2">NON GIOCA avrebbe perso</th>
          </tr>
        </thead>
        <tbody>
          {Object.values(models).flatMap((m) =>
            (['aggressive', 'cautious'] as const).map((mode) => {
              const a = m.advice_diagnostic[mode]
              return (
                <tr key={`${m.overview.model_key}-${mode}`} className="border-b border-slate-100">
                  <td className="px-2 py-2 font-medium">{m.overview.label}</td>
                  <td className="px-2 py-2 capitalize">{mode === 'aggressive' ? 'Aggressiva' : 'Cauta'}</td>
                  <td className="px-2 py-2">{fmtPct(a?.advised_play_hit_rate)}</td>
                  <td className="px-2 py-2">{a?.avoided_losses ?? '—'}</td>
                  <td className="px-2 py-2">{a?.missed_wins ?? '—'}</td>
                  <td className="px-2 py-2">{a?.no_play_would_have_won ?? '—'}</td>
                  <td className="px-2 py-2">{a?.no_play_would_have_lost ?? '—'}</td>
                </tr>
              )
            }),
          )}
        </tbody>
      </table>
    </div>
  )
}

function MacroTab({ diagnostics }: { diagnostics: RoundAnalysisDiagnostics }) {
  const macros = diagnostics.v21_diagnostics.macro_buckets
  const keys = Object.keys(macros)
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-xs">
        <thead>
          <tr className="border-b border-slate-200 text-left text-slate-600">
            <th className="px-2 py-2">Macro</th>
            <th className="px-2 py-2">Low hit</th>
            <th className="px-2 py-2">Neutral hit</th>
            <th className="px-2 py-2">High hit</th>
            <th className="px-2 py-2">Bias medio (neutral)</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((mk) => {
            const row = macros[mk]
            return (
              <tr key={mk} className="border-b border-slate-100">
                <td className="px-2 py-2 font-medium">{mk.replace(/_avg$/, '')}</td>
                <td className="px-2 py-2">{fmtPct(row.low?.cautious_hit_rate)}</td>
                <td className="px-2 py-2">{fmtPct(row.neutral?.cautious_hit_rate)}</td>
                <td className="px-2 py-2">{fmtPct(row.high?.cautious_hit_rate)}</td>
                <td className="px-2 py-2">{fmtNum(row.neutral?.bias)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

const CATEGORY_LABELS: Record<string, string> = {
  overestimate_v21: 'Sovrastima v2.1',
  underestimate_v21: 'Sottostima v2.1',
  all_models_cautious_loss: 'Perse da tutti (cauta)',
  v11_cautious_win_v21_cautious_loss: 'v1.1 WIN · v2.1 LOSS (cauta)',
  v21_cautious_gioca_loss: 'v2.1 GIOCA cauta LOSS',
}

function CriticalTab({ diagnostics }: { diagnostics: RoundAnalysisDiagnostics }) {
  const [sortKey, setSortKey] = useState<'round_number' | 'error_delta'>('error_delta')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const sorted = useMemo(() => {
    const rows = [...diagnostics.critical_matches]
    rows.sort((a, b) => {
      const av = sortKey === 'error_delta' ? (a.error_delta ?? 0) : a.round_number
      const bv = sortKey === 'error_delta' ? (b.error_delta ?? 0) : b.round_number
      return sortDir === 'asc' ? av - bv : bv - av
    })
    return rows
  }, [diagnostics.critical_matches, sortKey, sortDir])

  const toggleSort = (key: typeof sortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-xs">
        <thead>
          <tr className="border-b border-slate-200 text-left text-slate-600">
            <th className="px-2 py-2">Categoria</th>
            <th className="cursor-pointer px-2 py-2" onClick={() => toggleSort('round_number')}>
              Giornata
            </th>
            <th className="px-2 py-2">Partita</th>
            <th className="px-2 py-2">Actual</th>
            <th className="px-2 py-2">v1.1 pred</th>
            <th className="px-2 py-2">v2.1 pred</th>
            <th className="cursor-pointer px-2 py-2" onClick={() => toggleSort('error_delta')}>
              Δ errore
            </th>
            <th className="px-2 py-2">Report</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={`${row.category}-${row.fixture_id}-${i}`} className="border-b border-slate-100">
              <td className="px-2 py-2">{CATEGORY_LABELS[row.category] ?? row.category}</td>
              <td className="px-2 py-2">{row.round_number}</td>
              <td className="px-2 py-2">{row.match}</td>
              <td className="px-2 py-2">{row.actual_total_sot}</td>
              <td className="px-2 py-2">{fmtNum(row.v1_1?.predicted_total_sot as number | undefined, 1)}</td>
              <td className="px-2 py-2">{fmtNum(row.v2_1?.predicted_total_sot as number | undefined, 1)}</td>
              <td className="px-2 py-2">{fmtNum(row.error_delta, 1)}</td>
              <td className="px-2 py-2">
                <a
                  className="text-blue-700 underline"
                  href={row.fixture_report_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  JSON
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function RoundAnalysisDiagnosticsSection({ competitionId, seasonYear, reloadToken }: Props) {
  const [diagnostics, setDiagnostics] = useState<RoundAnalysisDiagnostics | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabId>('overview')
  const [downloadingJson, setDownloadingJson] = useState(false)

  const load = useCallback(async () => {
    if (competitionId == null) return
    setLoading(true)
    setError(null)
    try {
      const data = await getRoundAnalysisDiagnostics(competitionId, seasonYear)
      setDiagnostics(data)
    } catch (e) {
      setDiagnostics(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [competitionId, seasonYear])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  if (competitionId == null) return null

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Diagnostica modelli</h2>
          <p className="text-xs text-slate-500">
            Analisi errori su dati salvati — preparazione calibrazione v3.0 (nessun ricalcolo predizioni)
          </p>
        </div>
        <button
          type="button"
          disabled={downloadingJson || !diagnostics?.metadata.analyzed_fixtures}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          onClick={async () => {
            if (competitionId == null) return
            setDownloadingJson(true)
            try {
              const payload = await getRoundAnalysisDiagnosticsReportJson(competitionId, seasonYear)
              const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `round-analysis-diagnostics-${competitionId}-${seasonYear}.json`
              a.click()
              URL.revokeObjectURL(url)
            } finally {
              setDownloadingJson(false)
            }
          }}
        >
          {downloadingJson ? 'Download…' : 'Scarica diagnostica JSON'}
        </button>
      </div>

      {loading ? <p className="text-sm text-slate-500">Caricamento diagnostica…</p> : null}
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}

      {diagnostics && diagnostics.metadata.analyzed_fixtures > 0 ? (
        <>
          <div className="flex flex-wrap gap-1 border-b border-slate-200 pb-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                  tab === t.id ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-slate-500">
            {diagnostics.metadata.analyzed_fixtures} partite · {diagnostics.metadata.analyzed_rounds} giornate (
            {diagnostics.metadata.season_label})
          </p>
          {tab === 'overview' ? <OverviewTab models={diagnostics.models} /> : null}
          {tab === 'sot' ? <SotBucketsTab models={diagnostics.models} /> : null}
          {tab === 'lines' ? <LinesTab models={diagnostics.models} /> : null}
          {tab === 'edge' ? <EdgeTab models={diagnostics.models} /> : null}
          {tab === 'advice' ? <AdviceTab models={diagnostics.models} /> : null}
          {tab === 'macro' ? <MacroTab diagnostics={diagnostics} /> : null}
          {tab === 'critical' ? <CriticalTab diagnostics={diagnostics} /> : null}
        </>
      ) : !loading && !error ? (
        <p className="text-sm text-slate-500">Nessun dato diagnostico per questa stagione.</p>
      ) : null}
    </section>
  )
}
