import { useCallback, useRef, useState } from 'react'
import type {
  CecchinoKpiV2Panel,
  CecchinoPicchettiDebugResponse,
  CecchinoPicchettiDebugSummary,
  CecchinoPicchettiMarketDebug,
  CecchinoPicchettoContribution,
} from '../../lib/cecchinoTodayApi'
import { getPicchettiDebugJson } from '../../lib/cecchinoTodayApi'
import { todayCard } from './cecchinoTodayStyles'

const PICCHETTO_LABELS: Record<string, string> = {
  totals: 'Totali',
  home_away: 'Casa/Trasferta',
  last6_totals: 'Ultime 6 totali',
  last5_home_away: 'Ultime 5 casa/fuori',
}

const WEIGHT_LABELS: Array<{ key: string; pct: string }> = [
  { key: 'totals', pct: '25%' },
  { key: 'home_away', pct: '20%' },
  { key: 'last6_totals', pct: '35%' },
  { key: 'last5_home_away', pct: '20%' },
]

type TabId = '1' | 'X' | '2' | 'dc' | 'over_ft' | 'under_ft' | 'pt' | 'missing'

const OU_FT_OVER_KEYS = ['OVER_1_5', 'OVER_2_5'] as const
const OU_FT_UNDER_KEYS = ['UNDER_2_5', 'UNDER_3_5'] as const
const OU_PT_KEYS = ['OVER_PT_0_5', 'OVER_PT_1_5', 'UNDER_PT_1_5'] as const

const TAB_MARKET: Record<'1' | 'X' | '2', string> = {
  '1': 'HOME',
  X: 'DRAW',
  '2': 'AWAY',
}

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(digits)
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v.toFixed(1)}%`
}

type Props = {
  todayFixtureId?: number
  providerFixtureId?: number
  summary?: CecchinoPicchettiDebugSummary
  kpiPanel?: CecchinoKpiV2Panel
}

function PicchettoCard({ row }: { row: CecchinoPicchettoContribution }) {
  const label = PICCHETTO_LABELS[row.name] ?? row.name
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-700">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="font-semibold text-slate-900">{label}</span>
        <span className="text-slate-500">Peso {(row.weight * 100).toFixed(0)}%</span>
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 tabular-nums sm:grid-cols-3">
        <dt className="text-slate-500">Campione casa</dt>
        <dd>{row.sample_home ?? '—'}</dd>
        <dt className="text-slate-500">Record casa</dt>
        <dd>{row.record_home ?? '—'}</dd>
        <dt className="text-slate-500">Campione trasferta</dt>
        <dd>{row.sample_away ?? '—'}</dd>
        <dt className="text-slate-500">Record trasferta</dt>
        <dd>{row.record_away ?? '—'}</dd>
        <dt className="text-slate-500">Probabilità</dt>
        <dd>{fmtPct(row.probability_pct)}</dd>
        <dt className="text-slate-500">Quota picchetto</dt>
        <dd className="font-medium">{fmtNum(row.odd)}</dd>
        <dt className="text-slate-500">Contributo</dt>
        <dd>{fmtNum(row.weighted_contribution, 3)}</dd>
      </dl>
    </article>
  )
}

function Market1X2Tab({ market }: { market: CecchinoPicchettiMarketDebug | undefined }) {
  if (!market?.picchetti?.length) {
    return <p className="text-sm text-slate-500">Dati picchetti non disponibili.</p>
  }
  return (
    <div className="space-y-3">
      {market.picchetti.map((p) => (
        <PicchettoCard key={p.name} row={p} />
      ))}
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm">
        <span className="font-semibold text-emerald-900">Quota Cecchino finale ({market.segno}): </span>
        <span className="tabular-nums font-bold text-emerald-900">{fmtNum(market.final_odd)}</span>
      </div>
    </div>
  )
}

function DcTab({ markets }: { markets: Record<string, CecchinoPicchettiMarketDebug> }) {
  const dcKeys = ['ONE_X', 'X_TWO', 'ONE_TWO'] as const
  const home = markets.HOME
  const draw = markets.DRAW
  const away = markets.AWAY

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-xs">
        <p className="mb-2 font-semibold text-slate-800">Input da quote finali 1/X/2</p>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 tabular-nums sm:grid-cols-3">
          <dt className="text-slate-500">Quota 1</dt>
          <dd>{fmtNum(home?.final_odd)}</dd>
          <dt className="text-slate-500">Quota X</dt>
          <dd>{fmtNum(draw?.final_odd)}</dd>
          <dt className="text-slate-500">Quota 2</dt>
          <dd>{fmtNum(away?.final_odd)}</dd>
        </dl>
      </div>
      {dcKeys.map((key) => {
        const m = markets[key]
        if (!m) return null
        return (
          <article key={key} className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
            <h4 className="font-semibold text-slate-900">{m.segno}</h4>
            <p className="mt-1 font-mono text-xs text-slate-600">{m.formula}</p>
            {m.inputs && (
              <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs tabular-nums">
                {Object.entries(m.inputs).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-slate-500">{k}</dt>
                    <dd>{v == null ? '—' : typeof v === 'number' && v < 1 ? v.toFixed(4) : fmtNum(v)}</dd>
                  </div>
                ))}
              </dl>
            )}
            <p className="mt-2">
              <span className="text-slate-600">Risultato: </span>
              <span className="font-bold tabular-nums text-slate-900">{fmtNum(m.final_odd)}</span>
            </p>
          </article>
        )
      })}
    </div>
  )
}

function OuBlockCard({
  title,
  block,
}: {
  title: string
  block?: Record<string, number | undefined>
}) {
  if (!block || typeof block !== 'object') return null
  const entries = Object.entries(block).filter(([, v]) => v != null)
  if (!entries.length) return null
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-3 text-xs">
      <h4 className="mb-2 font-semibold text-slate-900">{title}</h4>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 tabular-nums sm:grid-cols-3">
        {entries.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-slate-500">{k}</dt>
            <dd>{typeof v === 'number' ? fmtNum(v, 4) : String(v)}</dd>
          </div>
        ))}
      </dl>
    </article>
  )
}

function OuFullTimeTab({
  keys,
  markets,
}: {
  keys: readonly string[]
  markets: Record<string, CecchinoPicchettiMarketDebug>
}) {
  const primary = markets[keys[0]]
  if (!primary) {
    return <p className="text-sm text-slate-500">Dati goal full time non disponibili.</p>
  }
  return (
    <div className="space-y-3">
      {primary.formula_note && (
        <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
          {primary.formula_note}
        </p>
      )}
      {primary.formula_version && (
        <p className="text-xs text-slate-500">Versione: {primary.formula_version}</p>
      )}
      <OuBlockCard title="Blocco casa/fuori" block={primary.blocks?.home_away} />
      <OuBlockCard title="Blocco totals" block={primary.blocks?.totals} />
      <OuBlockCard title="Blocco mixed" block={primary.blocks?.mixed} />
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm">
        <span className="font-semibold text-emerald-900">Quota Cecchino finale: </span>
        <span className="tabular-nums font-bold text-emerald-900">{fmtNum(primary.final_odd)}</span>
        {keys.length > 1 && (
          <p className="mt-1 text-xs text-emerald-800">
            Stessa quota per {keys.map((k) => markets[k]?.segno ?? k).join(' e ')} (parità Excel).
          </p>
        )}
      </div>
    </div>
  )
}

function OuFirstHalfTab({ markets }: { markets: Record<string, CecchinoPicchettiMarketDebug> }) {
  return (
    <div className="space-y-4">
      {OU_PT_KEYS.map((key) => {
        const m = markets[key]
        if (!m) return null
        return (
          <article key={key} className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
            <h4 className="font-semibold text-slate-900">{m.segno}</h4>
            {m.formula_version && (
              <p className="mt-1 text-xs text-slate-500">Versione: {m.formula_version}</p>
            )}
            {m.event && <p className="mt-1 font-mono text-xs text-slate-600">Evento: {m.event}</p>}
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs tabular-nums sm:grid-cols-4">
              <dt className="text-slate-500">Campione casa</dt>
              <dd>{m.home?.sample ?? '—'}</dd>
              <dt className="text-slate-500">Hit casa</dt>
              <dd>{m.home?.hits ?? '—'}</dd>
              <dt className="text-slate-500">Rate casa</dt>
              <dd>{m.home?.rate != null ? fmtPct(m.home.rate * 100) : '—'}</dd>
              <dt className="text-slate-500">Campione trasferta</dt>
              <dd>{m.away?.sample ?? '—'}</dd>
              <dt className="text-slate-500">Hit trasferta</dt>
              <dd>{m.away?.hits ?? '—'}</dd>
              <dt className="text-slate-500">Rate trasferta</dt>
              <dd>{m.away?.rate != null ? fmtPct(m.away.rate * 100) : '—'}</dd>
              <dt className="text-slate-500">Probabilità</dt>
              <dd>{m.probability != null ? fmtPct(m.probability * 100) : '—'}</dd>
            </dl>
            <p className="mt-2">
              <span className="text-slate-600">Quota Cecchino: </span>
              <span className="font-bold tabular-nums text-slate-900">{fmtNum(m.final_odd)}</span>
            </p>
            {m.skipped_missing_halftime_score != null && m.skipped_missing_halftime_score > 0 && (
              <p className="mt-1 text-xs text-amber-700">
                Escluse {m.skipped_missing_halftime_score} partite senza score primo tempo.
              </p>
            )}
          </article>
        )
      })}
    </div>
  )
}

function MissingFormulasTab({
  items,
}: {
  items: CecchinoPicchettiDebugResponse['missing_formulas']
}) {
  const list = items ?? []
  if (!list.length) {
    return (
      <p className="text-sm text-emerald-800">
        Tutte le formule Quota Cecchino goal sono calcolate per questa partita.
      </p>
    )
  }
  return (
    <div className="space-y-3 text-sm text-slate-700">
      <p className="font-semibold text-slate-900">Formule ancora mancanti:</p>
      <ul className="list-inside list-disc space-y-1">
        {list.map((m) => (
          <li key={m.market_key}>{m.label}</li>
        ))}
      </ul>
      <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
        Questi mercati hanno Quota Book Betfair, ma non hanno ancora una Quota Cecchino perché manca la
        formula matematica. Non vengono calcolati Edge, Score e Rating.
      </p>
    </div>
  )
}

export function CecchinoTodayPicchettiDebugPanel({
  todayFixtureId,
  providerFixtureId,
  summary,
}: Props) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<TabId>('1')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<CecchinoPicchettiDebugResponse | null>(null)
  const fetchedRef = useRef(false)

  const loadDebug = useCallback(async () => {
    if (!todayFixtureId || fetchedRef.current) return
    setLoading(true)
    setError(null)
    try {
      const res = await getPicchettiDebugJson(todayFixtureId)
      if (res.status !== 'ok') {
        setError(res.message ?? 'Debug non disponibile')
        return
      }
      setData(res)
      fetchedRef.current = true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore caricamento debug')
    } finally {
      setLoading(false)
    }
  }, [todayFixtureId])

  const handleToggle = (e: React.SyntheticEvent<HTMLDetailsElement>) => {
    const isOpen = e.currentTarget.open
    setOpen(isOpen)
    if (isOpen) void loadDebug()
  }

  const handleDownload = () => {
    if (!data || !providerFixtureId) return
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `cecchino-picchetti-debug-${providerFixtureId}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const weights = data?.weights ?? summary?.weights
  const markets = data?.markets ?? {}

  const missingCount = data?.missing_formulas?.length ?? summary?.missing_formulas_count ?? 0

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: '1', label: '1' },
    { id: 'X', label: 'X' },
    { id: '2', label: '2' },
    { id: 'dc', label: '1X/X2/12' },
    { id: 'over_ft', label: 'Over FT' },
    { id: 'under_ft', label: 'Under FT' },
    { id: 'pt', label: 'Primo tempo' },
    ...(missingCount > 0 ? [{ id: 'missing' as TabId, label: 'Formule mancanti' }] : []),
  ]

  return (
    <details className={`${todayCard} overflow-hidden`} onToggle={handleToggle}>
      <summary className="cursor-pointer px-4 py-3 hover:bg-slate-50">
        <span className="text-sm font-semibold text-slate-900">Debug Picchetti Cecchino</span>
        <p className="mt-0.5 text-xs text-slate-500">
          Breakdown dei picchetti usati per calcolare la Quota Cecchino.
        </p>
      </summary>

      <div className="border-t border-slate-200 px-4 py-4">
        {weights && (
          <div className="mb-4 flex flex-wrap gap-2">
            {WEIGHT_LABELS.map(({ key, pct }) => (
              <span
                key={key}
                className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700"
              >
                {PICCHETTO_LABELS[key] ?? key} {pct}
              </span>
            ))}
          </div>
        )}

        {open && loading && (
          <p className="text-sm text-slate-500" aria-busy="true">
            Caricamento debug…
          </p>
        )}
        {error && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </p>
        )}

        {data && !loading && (
          <>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap gap-1">
                {tabs.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTab(t.id)}
                    className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                      tab === t.id
                        ? 'bg-slate-800 text-white'
                        : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              {providerFixtureId != null && (
                <button
                  type="button"
                  onClick={handleDownload}
                  className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Scarica debug picchetti JSON
                </button>
              )}
            </div>

            {tab === '1' && <Market1X2Tab market={markets[TAB_MARKET['1']]} />}
            {tab === 'X' && <Market1X2Tab market={markets[TAB_MARKET.X]} />}
            {tab === '2' && <Market1X2Tab market={markets[TAB_MARKET['2']]} />}
            {tab === 'dc' && <DcTab markets={markets} />}
            {tab === 'over_ft' && <OuFullTimeTab keys={OU_FT_OVER_KEYS} markets={markets} />}
            {tab === 'under_ft' && <OuFullTimeTab keys={OU_FT_UNDER_KEYS} markets={markets} />}
            {tab === 'pt' && <OuFirstHalfTab markets={markets} />}
            {tab === 'missing' && <MissingFormulasTab items={data.missing_formulas} />}

            {(data.warnings ?? []).length > 0 && (
              <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                <p className="font-semibold">Avvisi</p>
                <ul className="mt-1 list-inside list-disc">
                  {(data.warnings ?? []).map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </details>
  )
}
