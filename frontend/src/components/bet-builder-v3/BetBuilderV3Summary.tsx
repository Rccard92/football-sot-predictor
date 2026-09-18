import { bbCard, bbCardPadding } from '../bet-builder/betBuilderStyles'
import { formatProfitUnits, formatRoiPct, signedMetricTone } from '../bet-builder/betBuilderResultsUtils'
import { sampleLabel, type BbV3Source, type BbV3Tally } from './bbV3Utils'

/** Riepilogo pre-match: stessa striscia del Bet Builder. */
export function BetBuilderV3PrematchSummary({
  source = 'index',
  fixtures,
  fixturesWithOpportunity,
  tally,
  confirmed,
}: {
  source?: BbV3Source
  fixtures: number
  fixturesWithOpportunity: number
  tally: BbV3Tally
  confirmed: number
}) {
  const items = [
    { key: 'fixtures', label: 'Partite analizzate', value: fixtures },
    { key: 'with', label: source === 'pattern' ? 'Con pattern accesi' : 'Con opportunità', value: fixturesWithOpportunity },
    { key: 'opps', label: source === 'pattern' ? 'Mercati con pattern' : 'Opportunità', value: tally.opportunities },
    { key: 'playable', label: 'Giocabili', value: tally.playable },
    {
      key: 'confirmed',
      label: source === 'pattern' ? 'Confermati dall’indice' : 'Confermate dal pattern',
      value: confirmed,
    },
    { key: 'pending', label: 'Da giocare', value: tally.pending },
  ]
  return (
    <section aria-label="Riepilogo giornata" data-testid="bb-v3-summary">
      <div
        className={`${bbCard} -mx-1 grid grid-cols-3 gap-0 overflow-hidden sm:mx-0 sm:flex sm:overflow-x-auto lg:grid lg:grid-cols-6 lg:overflow-visible`}
      >
        {items.map((item, i) => (
          <div
            key={item.key}
            className={`min-w-0 px-2.5 py-2 sm:min-w-[6.5rem] sm:shrink-0 sm:px-3 sm:py-2.5 ${i > 0 ? 'border-l border-slate-100' : ''}`}
          >
            <p className="text-base font-semibold tabular-nums text-slate-900 sm:text-lg">{item.value}</p>
            <p className="mt-0.5 text-[10px] font-medium leading-tight text-slate-500 sm:text-[11px]">{item.label}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

function toneClass(tone: 'positive' | 'negative' | 'neutral'): string {
  if (tone === 'positive') return 'text-emerald-700'
  if (tone === 'negative') return 'text-rose-700'
  return 'text-slate-900'
}

function Kpi({ label, value, tone = 'neutral' }: { label: string; value: string | number; tone?: 'positive' | 'negative' | 'neutral' }) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-100 bg-slate-50/80 px-2.5 py-2.5 text-left">
      <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500 lg:text-[11px]">{label}</p>
      <p className={`mt-0.5 text-lg font-semibold tabular-nums lg:text-xl ${toneClass(tone)}`}>{value}</p>
    </div>
  )
}

/** Riepilogo risultati: stessi KPI del Bet Builder, sulle opportunita' filtrate. */
export function BetBuilderV3ResultsSummary({ tally }: { tally: BbV3Tally }) {
  return (
    <section className={`${bbCard} ${bbCardPadding}`} data-testid="bb-v3-results-summary" aria-label="Risultati">
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-8">
        <Kpi label="Opportunità" value={tally.opportunities} />
        <Kpi label="Concluse" value={tally.closed} />
        <Kpi label="Vinte" value={tally.won} />
        <Kpi label="Perse" value={tally.lost} />
        <Kpi label="Win Rate" value={tally.winPct == null ? '—' : `${tally.winPct.toFixed(1)}%`} />
        <Kpi label="Profitto" value={formatProfitUnits(tally.priced ? tally.profit : null)} tone={signedMetricTone(tally.priced ? tally.profit : null)} />
        <Kpi label="ROI" value={formatRoiPct(tally.roiPct)} tone={signedMetricTone(tally.roiPct)} />
        <Kpi label="In attesa" value={tally.pending} />
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Campione: <span className="font-semibold text-slate-700">{sampleLabel(tally.closed)}</span> ({tally.closed} concluse;
        indicativo da 100, affidabile da 300).
      </p>
      <p className="mt-0.5 text-xs text-slate-500">
        Profitto e ROI: 1 unità per giocata alla quota Bet365 registrata prima della partita, sulle opportunità mostrate
        con i filtri attuali.
      </p>
    </section>
  )
}
