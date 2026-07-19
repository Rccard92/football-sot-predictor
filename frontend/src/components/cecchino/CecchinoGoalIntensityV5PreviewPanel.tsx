import type { CecchinoTodayDetailResponse } from '../../lib/cecchinoTodayApi'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

type PreviewPayload = NonNullable<CecchinoTodayDetailResponse['goal_intensity_v5_preview']>

type Props = {
  preview?: PreviewPayload | null
}

function fmt(v: number | null | undefined, digits = 1): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return Number(v).toFixed(digits)
}

function fmtProb(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return `${(Number(v) * 100).toFixed(1)}%`
}

const CANDIDATES = [
  { id: 'GI_A_STRICT_CORE', role: 'Primary', scoreKey: 'primary_candidate_score' },
  { id: 'GI_B_RECENCY', role: 'Challenger', scoreKey: 'challenger_candidate_score' },
  { id: 'MT1_LONG_TERM', role: 'Benchmark', scoreKey: 'benchmark_score' },
  {
    id: 'GI_A_without_volatility',
    role: 'Diagnostico',
    scoreKey: 'diagnostic_score',
  },
] as const

export function CecchinoGoalIntensityV5PreviewPanel({ preview }: Props) {
  if (!preview || preview.status === 'unavailable') {
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <h3 className={todaySectionTitle}>Intensità Goal Avanzata - v5 Preview research</h3>
        <p className={todaySectionSubtitle}>
          Snapshot prospettico non disponibile (bundle assente o partita fuori coorte).
        </p>
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          Preview research non produttiva. Nessun segnale betting attivato.
        </p>
      </section>
    )
  }

  if (preview.status === 'error' && !preview.snapshot) {
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <h3 className={todaySectionTitle}>Intensità Goal Avanzata - v5 Preview research</h3>
        <p className="mt-2 text-sm text-slate-600">{preview.banner ?? 'Preview non disponibile.'}</p>
      </section>
    )
  }

  const snap = (preview.snapshot || {}) as Record<string, unknown>
  const pillars = (snap.pillar_scores || {}) as Record<string, number | null>
  const calibrated = (snap.calibrated_predictions || {}) as Record<
    string,
    Record<string, number | null | string | boolean>
  >

  return (
    <section className={`${todayCard} ${todayCardPadding}`}>
      <h3 className={todaySectionTitle}>Intensità Goal Avanzata - v5 Preview research</h3>
      <p className={todaySectionSubtitle}>
        Separato da Intensità Goal v4. Score congelati da bundle Fase 2A.
      </p>
      <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-950">
        {preview.banner ??
          'Preview research non produttiva. Nessun segnale betting attivato.'}
      </p>

      <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
        <p>
          Bundle frozen at:{' '}
          <span className="font-medium">
            {String(snap.bundle_frozen_at ?? (preview.bundle as Record<string, unknown> | undefined)?.bundle_frozen_at ?? '—')}
          </span>
        </p>
        <p className="mt-1">
          Source snapshot at:{' '}
          <span className="font-medium">{String(snap.source_snapshot_at ?? '—')}</span>
        </p>
        <p className="mt-1">
          source_snapshot_at &gt; bundle_frozen_at:{' '}
          <span className="font-medium">
            {(() => {
              const check = snap.freeze_check as Record<string, boolean> | undefined
              const v = check?.source_snapshot_at_gt_bundle_frozen_at ?? snap.source_snapshot_after_freeze
              return v == null ? '—' : v ? 'sì' : 'no'
            })()}
          </span>
        </p>
        <p className="mt-1">
          source_snapshot_at &lt; kickoff:{' '}
          <span className="font-medium">
            {(() => {
              const check = snap.freeze_check as Record<string, boolean> | undefined
              const v = check?.source_snapshot_at_lt_kickoff ?? snap.source_snapshot_before_kickoff
              return v == null ? '—' : v ? 'sì' : 'no'
            })()}
          </span>
        </p>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <PillarBlock
          title="1. Produzione offensiva"
          rows={[
            ['OP1 long-term', pillars.OP1_HOME_LONG_TERM],
            ['OP2 recency', pillars.OP2_HOME_RECENCY],
          ]}
        />
        <PillarBlock
          title="2. Vulnerabilità / Solidità difensiva"
          rows={[
            ['Vulnerabilità DV1', pillars.DV1_MEAN_CONCEDED],
            ['Solidità (100 − vuln.)', pillars.defensive_solidity_display],
          ]}
        />
        <PillarBlock
          title="3. Ritmo partita"
          rows={[
            ['MT1 long-term', pillars.MT1_LONG_TERM],
            ['MT2 + recency', pillars.MT2_LONG_TERM_PLUS_RECENCY],
          ]}
        />
        <PillarBlock
          title="4. Volatilità / Stabilità offensiva"
          rows={[
            ['Volatilità OV1', pillars.OV1_STD],
            ['Stabilità (100 − vol.)', pillars.offensive_stability_display],
          ]}
        />
      </div>

      <div className="mt-5 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="border-b border-slate-200 text-slate-500">
            <tr>
              <th className="py-2 pr-3 font-medium">Candidato</th>
              <th className="py-2 pr-3 font-medium">Ruolo</th>
              <th className="py-2 pr-3 font-medium">Score</th>
              <th className="py-2 pr-3 font-medium">Exp. goals</th>
              <th className="py-2 pr-3 font-medium">P≥2</th>
              <th className="py-2 pr-3 font-medium">P≥3</th>
              <th className="py-2 font-medium">P BTTS</th>
            </tr>
          </thead>
          <tbody>
            {CANDIDATES.map((c) => {
              const cal = calibrated[c.id] || {}
              const score =
                (snap[c.scoreKey] as number | null | undefined) ??
                ((snap.candidate_scores as Record<string, number> | undefined)?.[c.id] ?? null)
              return (
                <tr key={c.id} className="border-b border-slate-100 text-slate-800">
                  <td className="py-2 pr-3 font-medium">{c.id}</td>
                  <td className="py-2 pr-3">{c.role}</td>
                  <td className="py-2 pr-3">{fmt(score)}</td>
                  <td className="py-2 pr-3">{fmt(cal.expected_total_goals as number | null, 2)}</td>
                  <td className="py-2 pr-3">{fmtProb(cal.probability_goals_ge_2 as number | null)}</td>
                  <td className="py-2 pr-3">{fmtProb(cal.probability_goals_ge_3 as number | null)}</td>
                  <td className="py-2">{fmtProb(cal.probability_btts as number | null)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="mt-2 text-[11px] text-slate-500">
          Probabilità etichettate come «Stima calibrata research». Nessun pick / Over / Under / GG /
          quota / value / ROI.
        </p>
      </div>
    </section>
  )
}

function PillarBlock({
  title,
  rows,
}: {
  title: string
  rows: Array<[string, number | null | undefined]>
}) {
  return (
    <div className="rounded-lg border border-slate-150 bg-slate-50/60 px-3 py-2">
      <p className="text-xs font-semibold text-slate-800">{title}</p>
      <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
        {rows.map(([label, value]) => (
          <li key={label} className="flex justify-between gap-2">
            <span>{label}</span>
            <span className="font-medium text-slate-900">{fmt(value)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
