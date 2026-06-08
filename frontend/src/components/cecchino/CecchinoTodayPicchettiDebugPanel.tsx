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

type TabId = '1' | 'X' | '2' | 'dc' | 'missing'

const TAB_MARKET: Record<Exclude<TabId, 'dc' | 'missing'>, string> = {
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

function MissingFormulasTab({
  items,
}: {
  items: CecchinoPicchettiDebugResponse['missing_formulas']
}) {
  const list = items ?? []
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

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: '1', label: '1' },
    { id: 'X', label: 'X' },
    { id: '2', label: '2' },
    { id: 'dc', label: '1X/X2/12' },
    { id: 'missing', label: 'Formule mancanti' },
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
