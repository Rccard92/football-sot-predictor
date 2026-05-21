import type { BettingAdviceMarket, FixtureBettingAdvice } from '../../types/sotExplanation'

function fmtMargin(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}`
}

function fmtPredicted(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(2)
}

function MarketBlock({
  title,
  market,
}: {
  title: string
  market: BettingAdviceMarket
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">{title}</p>
      <p className="mt-2 text-sm text-slate-700">
        Previsti: <span className="font-bold tabular-nums text-slate-900">{fmtPredicted(market.predicted_value)}</span>{' '}
        SOT
      </p>

      <div className="mt-3 space-y-2 border-t border-slate-100 pt-3 text-[11px]">
        <div>
          <p className="font-medium text-slate-800">Giocata statistica</p>
          {market.statistical_pick ? (
            <>
              <p className="mt-0.5 font-semibold text-indigo-900">{market.statistical_pick}</p>
              <p className="text-slate-600">
                Margine: <span className="tabular-nums font-medium">{fmtMargin(market.statistical_margin)}</span>
              </p>
              {market.statistical_risk ? (
                <p className="text-slate-600">
                  Rischio: <span className="font-medium">{market.statistical_risk}</span>
                </p>
              ) : null}
            </>
          ) : (
            <p className="mt-0.5 text-amber-800">Nessuna giocata statistica suggerita</p>
          )}
        </div>

        <div>
          <p className="font-medium text-slate-800">Giocata cauta</p>
          {market.cautious_pick ? (
            <>
              <p className="mt-0.5 font-semibold text-emerald-900">{market.cautious_pick}</p>
              {market.cautious_note ? (
                <p className="text-[10px] text-slate-600">{market.cautious_note}</p>
              ) : null}
              <p className="text-slate-600">
                Margine cauta:{' '}
                <span className="tabular-nums font-medium">{fmtMargin(market.cautious_margin)}</span>
              </p>
            </>
          ) : (
            <p className="mt-0.5 text-amber-800">Nessuna giocata cauta con margine minimo sufficiente</p>
          )}
        </div>

        <p className="text-[10px] text-slate-500">
          Confidence consiglio: <span className="font-medium text-slate-700">{market.confidence_label}</span>
        </p>
      </div>
    </div>
  )
}

export function SotBettingAdviceCard({ advice }: { advice: FixtureBettingAdvice }) {
  const homeTitle = advice.home_team_name ? `Casa — ${advice.home_team_name}` : 'Casa'
  const awayTitle = advice.away_team_name ? `Trasferta — ${advice.away_team_name}` : 'Trasferta'

  return (
    <section className="overflow-hidden rounded-2xl border border-indigo-200/80 bg-indigo-50/20 shadow-sm">
      <div className="border-b border-indigo-100 bg-indigo-50/50 px-4 py-3">
        <h2 className="text-sm font-semibold tracking-tight text-indigo-950">Consiglio giocata SOT</h2>
        <p className="mt-1 text-[11px] text-indigo-900/90">
          Basato su modello: <span className="font-medium">{advice.model_label}</span>
        </p>
        <p className="mt-1 text-[10px] text-slate-600">
          Indicazione statistica basata sul modello, non garanzia di esito.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-3">
        <MarketBlock title="Totale match" market={advice.match_total} />
        <MarketBlock title={homeTitle} market={advice.home_team_sot} />
        <MarketBlock title={awayTitle} market={advice.away_team_sot} />
      </div>

      {(advice.match_total.reasons?.length ?? 0) > 0 ? (
        <ul className="border-t border-indigo-100/80 px-4 pb-4 list-inside list-disc text-[10px] leading-relaxed text-slate-700">
          {advice.match_total.reasons!.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
