import type { RoundAnalysisModelOverviewStats } from '../../lib/api'
import { MODEL_KEYS } from './roundAnalysisUtils'

const MODEL_ORDER = [
  { key: MODEL_KEYS.v11, short: 'v1.1' },
  { key: MODEL_KEYS.v20, short: 'v2.0' },
  { key: MODEL_KEYS.v21, short: 'v2.1' },
  { key: MODEL_KEYS.v30, short: 'v3.0' },
] as const

const V30_INFO_COPY =
  'NO BET non significa pronostico perdente: il modello ha scelto di non giocare. Solo i pick GIOCA con esito WIN/LOSS entrano nell\'hit rate.'

function reliabilityClass(score: number | null | undefined): string {
  if (score == null) return 'bg-slate-100 text-slate-600'
  if (score >= 75) return 'bg-emerald-100 text-emerald-900'
  if (score >= 60) return 'bg-amber-100 text-amber-900'
  return 'bg-rose-100 text-rose-900'
}

function sampleLabel(status: string): string {
  if (status === 'solido') return 'Solido'
  if (status === 'medio') return 'Medio'
  return 'Provvisorio'
}

function trendArrow(direction: string | undefined): string {
  if (direction === 'up') return '↑'
  if (direction === 'down') return '↓'
  return '→'
}

type Props = {
  models: Record<string, RoundAnalysisModelOverviewStats>
}

function ClassicScorecard({
  m,
  short,
}: {
  m: RoundAnalysisModelOverviewStats
  short: string
}) {
  const score = m.reliability_score
  const caut = m.cautious
  const cautHr = caut?.hit_rate
  const cautDisplay = caut?.display ?? '—'
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-semibold text-slate-900">{m.label ?? short}</span>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-700">
          {sampleLabel(m.sample_status)}
        </span>
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">
        <span className={`inline-block rounded-lg px-2 py-0.5 ${reliabilityClass(score)}`}>
          {score != null ? score.toFixed(1) : '—'}
        </span>
      </p>
      <p className="mt-1 text-xs text-slate-500">Affidabilità (peso sulla linea cauta)</p>
      <div className="mt-3 space-y-1 text-xs">
        <p>
          <span className="font-medium text-slate-800">Cauta (consigliate):</span>{' '}
          <span className="text-slate-700">{cautDisplay}</span>
        </p>
        <p className="text-slate-500">Aggressiva: {m.aggressive?.display ?? '—'}</p>
        <p className="text-slate-500">
          Partite analizzate: {m.fixtures_analyzed ?? 0} · Giornate: {m.rounds_count ?? 0}
        </p>
        {m.trend_last_5_rounds ? (
          <p className="text-slate-500">
            Trend ultime 5 giornate {trendArrow(m.trend_last_5_rounds.direction)}{' '}
            {m.trend_last_5_rounds.hit_rate != null
              ? `${m.trend_last_5_rounds.hit_rate}%`
              : '—'}
          </p>
        ) : null}
      </div>
      {cautHr != null ? (
        <p className="mt-2 text-[10px] text-slate-400">
          Errore medio {m.mae ?? '—'} · Bias {m.bias ?? '—'}
        </p>
      ) : null}
    </div>
  )
}

function V30Scorecard({ m }: { m: RoundAnalysisModelOverviewStats }) {
  const score = m.reliability_score
  const pickW = m.cautious?.wins ?? 0
  const pickL = m.cautious?.losses ?? 0
  const pickDisplay = m.cautious?.display ?? '—'
  return (
    <div className="rounded-xl border border-violet-200 bg-white p-4">
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-semibold text-slate-900">{m.label ?? 'v3.0'}</span>
        <div className="flex flex-col items-end gap-1">
          <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-medium text-violet-800">
            Sperimentale
          </span>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-700">
            {sampleLabel(m.sample_status)}
          </span>
        </div>
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">
        <span className={`inline-block rounded-lg px-2 py-0.5 ${reliabilityClass(score)}`}>
          {score != null ? score.toFixed(1) : '—'}
        </span>
      </p>
      <p className="mt-1 text-xs text-slate-500">Affidabilità sui pick selezionati</p>
      <div className="mt-3 space-y-1 text-xs">
        <p>
          <span className="font-medium text-slate-800">Pick selezionati:</span>{' '}
          <span className="text-slate-700">{pickDisplay}</span>
        </p>
        <p className="text-slate-500">NO BET: {m.no_bet_count ?? 0}</p>
        <p className="text-slate-500">Borderline: {m.borderline_count ?? 0}</p>
        {m.line_6_5?.display ? (
          <p className="text-slate-500">Linea 6.5: {m.line_6_5.display}</p>
        ) : null}
        {m.line_7_5?.display ? (
          <p className="text-slate-500">Linea 7.5: {m.line_7_5.display}</p>
        ) : null}
        <p className="text-slate-500">Aggressiva: N/A</p>
        <p className="text-slate-500">
          Partite analizzate: {m.fixtures_analyzed ?? 0} · Giornate: {m.rounds_count ?? 0}
        </p>
        {m.trend_last_5_rounds ? (
          <p className="text-slate-500">
            Trend ultime 5 giornate {trendArrow(m.trend_last_5_rounds.direction)}{' '}
            {m.trend_last_5_rounds.hit_rate != null
              ? `${m.trend_last_5_rounds.hit_rate}%`
              : '—'}
          </p>
        ) : null}
      </div>
      <p className="mt-3 text-[10px] leading-snug text-slate-500">{V30_INFO_COPY}</p>
      {pickW + pickL > 0 ? (
        <p className="mt-1 text-[10px] text-slate-400">
          Pick {pickW}W / {pickL}L su {pickW + pickL} giocati
        </p>
      ) : null}
    </div>
  )
}

export function ModelReliabilityScorecards({ models }: Props) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {MODEL_ORDER.map(({ key, short }) => {
        const m = models[key]
        if (!m) {
          return (
            <div key={key} className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
              {short}: nessun dato
            </div>
          )
        }
        if (key === MODEL_KEYS.v30) {
          return <V30Scorecard key={key} m={m} />
        }
        return <ClassicScorecard key={key} m={m} short={short} />
      })}
    </div>
  )
}
