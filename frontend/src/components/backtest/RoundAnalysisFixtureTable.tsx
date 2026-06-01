import { Fragment, useMemo, useState } from 'react'
import type { RoundAnalysisDetail, RoundAnalysisFixtureRow, RoundAnalysisModelBlock } from '../../lib/api'
import { getRoundAnalysisFixtureReportJson } from '../../lib/api'
import { ModelSummaryBar } from './RoundAnalysisAccordion'
import { MODEL_KEYS, ndBadgeClass, pickCell } from './roundAnalysisUtils'
import { RoundAnalysisFixtureRowDetail } from './RoundAnalysisFixtureRowDetail'

type Props = {
  detail: RoundAnalysisDetail
  competitionName?: string | null
  fixtures: RoundAnalysisFixtureRow[]
}

type FilterKind =
  | 'all'
  | 'lost'
  | 'won'
  | 'advised'
  | 'not_advised'
  | 'cautious_loss'
  | 'aggressive_loss'

function adviceIsPlay(block: RoundAnalysisModelBlock | undefined, kind: 'aggressive' | 'cautious'): boolean {
  const field = kind === 'aggressive' ? 'aggressive_advice' : 'cautious_advice'
  return String(block?.[field] ?? '').trim().toUpperCase() === 'GIOCA'
}

function outcomeIs(block: RoundAnalysisModelBlock | undefined, kind: 'aggressive' | 'cautious', out: 'WIN' | 'LOSS'): boolean {
  const field = kind === 'aggressive' ? 'aggressive_outcome' : 'cautious_outcome'
  return block?.[field] === out
}

function anyCautiousLoss(fx: RoundAnalysisFixtureRow): boolean {
  for (const key of Object.values(MODEL_KEYS)) {
    if (outcomeIs(fx.models_json[key], 'cautious', 'LOSS')) return true
  }
  return false
}

function anyWin(fx: RoundAnalysisFixtureRow): boolean {
  for (const key of Object.values(MODEL_KEYS)) {
    if (
      outcomeIs(fx.models_json[key], 'cautious', 'WIN') ||
      outcomeIs(fx.models_json[key], 'aggressive', 'WIN')
    ) {
      return true
    }
  }
  return false
}

function anyAdvised(fx: RoundAnalysisFixtureRow): boolean {
  for (const key of Object.values(MODEL_KEYS)) {
    const b = fx.models_json[key]
    if (adviceIsPlay(b, 'aggressive') || adviceIsPlay(b, 'cautious')) return true
  }
  return false
}

function reviewScore(fx: RoundAnalysisFixtureRow): number {
  const v21 = fx.models_json[MODEL_KEYS.v21]
  let score = 0
  const pred = v21?.predicted_total_sot
  const actual = fx.actual_total_sot
  if (pred != null && actual != null) {
    score += Math.abs(Number(pred) - Number(actual)) * 10
  }
  let cautiousLosses = 0
  for (const key of Object.values(MODEL_KEYS)) {
    if (outcomeIs(fx.models_json[key], 'cautious', 'LOSS')) cautiousLosses += 1
  }
  if (cautiousLosses >= 2) score += 100
  return score
}

function PickTd({
  block,
  kind,
}: {
  block: Parameters<typeof pickCell>[0]
  kind: 'aggressive' | 'cautious'
}) {
  const cell = pickCell(block, kind)
  const badge = cell.label === 'ERR' ? 'ERR' : 'ND'
  return (
    <td className="px-3 py-2 align-top" title={cell.title}>
      {cell.isNd ? (
        <div className="space-y-0.5">
          <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${ndBadgeClass()}`}>
            {badge}
          </span>
          {cell.sublabel ? <div className="text-[10px] text-slate-500">{cell.sublabel}</div> : null}
        </div>
      ) : (
        <span>{cell.label}</span>
      )}
    </td>
  )
}

export function RoundAnalysisFixtureTable({ detail, competitionName, fixtures }: Props) {
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [filter, setFilter] = useState<FilterKind>('all')
  const [modelFilter, setModelFilter] = useState<string>('')

  const filtered = useMemo(() => {
    return fixtures.filter((fx) => {
      if (modelFilter) {
        const b = fx.models_json[modelFilter]
        if (!b || b.status === 'error' || b.status === 'no_prediction') return false
      }
      switch (filter) {
        case 'lost':
          return anyCautiousLoss(fx)
        case 'won':
          return anyWin(fx)
        case 'advised':
          return anyAdvised(fx)
        case 'not_advised':
          return !anyAdvised(fx)
        case 'cautious_loss':
          return Object.values(MODEL_KEYS).some((k) =>
            outcomeIs(fx.models_json[k], 'cautious', 'LOSS'),
          )
        case 'aggressive_loss':
          return Object.values(MODEL_KEYS).some((k) =>
            outcomeIs(fx.models_json[k], 'aggressive', 'LOSS'),
          )
        default:
          return true
      }
    })
  }, [fixtures, filter, modelFilter])

  const toReview = useMemo(() => {
    return [...fixtures]
      .filter((fx) => fx.status === 'ok')
      .sort((a, b) => reviewScore(b) - reviewScore(a))
      .slice(0, 3)
  }, [fixtures])

  const downloadFixtureJson = async (fixtureId: number) => {
    const payload = await getRoundAnalysisFixtureReportJson(detail.id, fixtureId)
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `round-${detail.round_number}-fixture-${fixtureId}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      <ModelSummaryBar summary={detail.model_summary_json} />

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-medium text-slate-700">Filtri:</span>
        {(
          [
            ['all', 'Tutte'],
            ['lost', 'Perse (cauta)'],
            ['won', 'Vinte'],
            ['advised', 'Consigliate'],
            ['not_advised', 'Non consigliate'],
            ['cautious_loss', 'Perdita cauta'],
            ['aggressive_loss', 'Perdita aggressiva'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`rounded-full px-2.5 py-1 ${
              filter === id ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
            onClick={() => setFilter(id)}
          >
            {label}
          </button>
        ))}
        <select
          className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs"
          value={modelFilter}
          onChange={(e) => setModelFilter(e.target.value)}
        >
          <option value="">Tutti i modelli</option>
          <option value={MODEL_KEYS.v11}>v1.1</option>
          <option value={MODEL_KEYS.v20}>v2.0</option>
          <option value={MODEL_KEYS.v21}>v2.1</option>
        </select>
      </div>

      {toReview.length > 0 ? (
        <section className="rounded-xl border border-amber-200 bg-amber-50/50 p-3">
          <h3 className="text-sm font-semibold text-amber-900">Partite da rivedere</h3>
          <ul className="mt-2 space-y-2 text-xs text-amber-950">
            {toReview.map((fx) => {
              const v21 = fx.models_json[MODEL_KEYS.v21]
              const err =
                v21?.predicted_total_sot != null && fx.actual_total_sot != null
                  ? Math.abs(Number(v21.predicted_total_sot) - Number(fx.actual_total_sot))
                  : null
              return (
                <li key={fx.id} className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    className="font-medium underline"
                    onClick={() => setExpandedId(fx.id)}
                  >
                    {fx.home_team_name} – {fx.away_team_name}
                  </button>
                  {err != null ? <span>Δ v2.1: {err.toFixed(1)} SOT</span> : null}
                  <button
                    type="button"
                    className="rounded border border-amber-300 px-2 py-0.5 hover:bg-amber-100"
                    onClick={() => void downloadFixtureJson(fx.fixture_id)}
                  >
                    Scarica JSON partita
                  </button>
                </li>
              )
            })}
          </ul>
        </section>
      ) : null}

      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="min-w-full text-left text-xs text-slate-700">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-3 py-2">Match</th>
              <th className="px-3 py-2">Actual</th>
              <th className="px-3 py-2">v1.1 Agg</th>
              <th className="px-3 py-2">v1.1 Cauta</th>
              <th className="px-3 py-2">v2.0 Agg</th>
              <th className="px-3 py-2">v2.0 Cauta</th>
              <th className="px-3 py-2">v2.1 Agg</th>
              <th className="px-3 py-2">v2.1 Cauta</th>
              <th className="px-3 py-2">Qualità</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((fx) => {
              const v11 = fx.models_json[MODEL_KEYS.v11]
              const v20 = fx.models_json[MODEL_KEYS.v20]
              const v21 = fx.models_json[MODEL_KEYS.v21]
              const dq = v21?.data_quality ?? v11?.data_quality
              const expanded = expandedId === fx.id
              return (
                <Fragment key={fx.id}>
                  <tr
                    className="cursor-pointer border-t border-slate-100 hover:bg-slate-50"
                    onClick={() => setExpandedId(expanded ? null : fx.id)}
                  >
                    <td className="px-3 py-2 font-medium text-slate-900">
                      {fx.home_team_name} – {fx.away_team_name}
                    </td>
                    <td className="px-3 py-2">{fx.actual_total_sot ?? '—'}</td>
                    <PickTd block={v11} kind="aggressive" />
                    <PickTd block={v11} kind="cautious" />
                    <PickTd block={v20} kind="aggressive" />
                    <PickTd block={v20} kind="cautious" />
                    <PickTd block={v21} kind="aggressive" />
                    <PickTd block={v21} kind="cautious" />
                    <td className="px-3 py-2">
                      {dq ? `${dq.lineup ?? '—'} / ${dq.mapping ?? '—'}` : '—'}
                    </td>
                  </tr>
                  {expanded ? (
                    <tr>
                      <td colSpan={9} className="bg-slate-50 px-3 py-3">
                        <RoundAnalysisFixtureRowDetail
                          detail={detail}
                          competitionName={competitionName}
                          fixture={fx}
                        />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              )
            })}
          </tbody>
        </table>
        {filtered.length === 0 ? (
          <p className="px-3 py-4 text-sm text-slate-500">Nessuna partita con i filtri selezionati.</p>
        ) : null}
      </div>
    </div>
  )
}
