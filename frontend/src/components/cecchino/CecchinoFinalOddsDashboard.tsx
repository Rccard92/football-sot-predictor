import type { CecchinoFinalOdds } from '../../lib/cecchinoApi'
import type { CecchinoSide } from '../../lib/cecchinoUtils'
import {
  canShowFinalOdds,
  computeBestSideFromFinal,
  fmtNum,
  fmtPct,
  statusLabel,
} from '../../lib/cecchinoUtils'

type Props = {
  final: CecchinoFinalOdds
  variant?: 'default' | 'embedded'
}

function sideCard(
  label: CecchinoSide,
  quota: number | null,
  probPct: number | null,
  highlighted: boolean,
  showNumbers: boolean,
) {
  const ring = highlighted ? 'ring-2 ring-indigo-500 border-indigo-300' : 'border-slate-200'
  return (
    <div className={`rounded-lg border bg-slate-50 p-3 text-center ${ring}`}>
      <p className="text-[11px] font-semibold uppercase text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-slate-900 tabular-nums">
        {showNumbers ? fmtNum(quota) : '—'}
      </p>
      <p className="text-xs text-slate-600 tabular-nums">
        {showNumbers ? fmtPct(probPct) : '—'}
      </p>
    </div>
  )
}

export function CecchinoFinalOddsDashboard({ final, variant = 'default' }: Props) {
  const embedded = variant === 'embedded'
  const showNumbers = canShowFinalOdds(final.status)
  const best = computeBestSideFromFinal(final)

  const outerClass = embedded
    ? 'space-y-3'
    : 'rounded-xl border border-indigo-200 bg-indigo-50/40 p-4 shadow-sm'

  return (
    <div className={outerClass}>
      {!embedded && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-indigo-900">Quota matematica finale Cecchino</h3>
          <span className="text-[10px] uppercase text-indigo-700">{statusLabel(final.status)}</span>
        </div>
      )}
      {embedded && (
        <span className="inline-block rounded-full bg-indigo-100 px-2.5 py-0.5 text-[10px] font-semibold uppercase text-indigo-800">
          {statusLabel(final.status)}
        </span>
      )}
      <div className="grid grid-cols-3 gap-3">
        {sideCard('1', final.quota_1, final.prob_1_pct, best === '1', showNumbers)}
        {sideCard('X', final.quota_x, final.prob_x_pct, best === 'X', showNumbers)}
        {sideCard('2', final.quota_2, final.prob_2_pct, best === '2', showNumbers)}
      </div>
      {best && showNumbers && (
        <p className="mt-2 text-xs text-indigo-800">
          Best side (quota minima): <span className="font-bold">{best}</span>
        </p>
      )}
      <p className="mt-3 text-[11px] text-slate-600">
        Pesi picchetti:{' '}
        {Object.entries(final.weights ?? {})
          .map(([k, v]) => `${k} ${(v * 100).toFixed(0)}%`)
          .join(' · ') || 'casa/trasferta 20% · totali 25% · ultime 5 20% · ultime 6 35%'}
      </p>
      {(final.warnings?.length ?? 0) > 0 && (
        <ul className="mt-2 list-inside list-disc text-[11px] text-amber-800">
          {final.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
