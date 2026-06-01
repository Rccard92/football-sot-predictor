import { Fragment, useState } from 'react'
import type { RoundAnalysisFixtureRow } from '../../lib/api'
import { MODEL_KEYS, ndBadgeClass, pickCell } from './roundAnalysisUtils'
import { RoundAnalysisFixtureRowDetail } from './RoundAnalysisFixtureRowDetail'

type Props = {
  fixtures: RoundAnalysisFixtureRow[]
}

function PickTd({
  block,
  kind,
}: {
  block: Parameters<typeof pickCell>[0]
  kind: 'aggressive' | 'cautious'
}) {
  const cell = pickCell(block, kind)
  return (
    <td className="px-3 py-2 align-top">
      {cell.isNd ? (
        <div className="space-y-0.5">
          <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${ndBadgeClass()}`}>
            ND
          </span>
          {cell.sublabel ? <div className="text-[10px] text-slate-500">{cell.sublabel}</div> : null}
        </div>
      ) : (
        <span>{cell.label}</span>
      )}
    </td>
  )
}

export function RoundAnalysisFixtureTable({ fixtures }: Props) {
  const [expandedId, setExpandedId] = useState<number | null>(null)

  return (
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
          {fixtures.map((fx) => {
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
                      <RoundAnalysisFixtureRowDetail fixture={fx} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
