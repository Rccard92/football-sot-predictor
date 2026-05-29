import { Link } from 'react-router-dom'
import type { ModelComparisonResponse, ModelComparisonRow, ModelComparisonSide } from '../../lib/api'
import { buildMatchAuditUrl } from '../../lib/api'
import { V20_MODEL, V21_MODEL, labelForModelVersion } from '../../lib/modelVersions'
import { formatKickoffReport } from '../../utils/sportApiLineupMeta'
import {
  confidenceBadgeClass,
  pickShortLabel,
} from '../../utils/bettingAdviceDisplay'
import { deltaBadgeClass, deltaBadgeLabel, pickShortFromLabel } from '../../utils/modelComparisonDisplay'
import { FormationStatusBadge } from '../../utils/lineupStatusDisplay'
import { formatNum } from './format'

function TeamMatchRow({ row }: { row: ModelComparisonRow }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {row.home_team.logo_url ? (
        <img src={row.home_team.logo_url} alt="" className="h-5 w-5 shrink-0 object-contain" />
      ) : (
        <span className="inline-block h-5 w-5 shrink-0 rounded-full bg-slate-100" />
      )}
      <span className="font-medium text-slate-900">{row.home_team.name}</span>
      <span className="text-slate-400">–</span>
      {row.away_team.logo_url ? (
        <img src={row.away_team.logo_url} alt="" className="h-5 w-5 shrink-0 object-contain" />
      ) : (
        <span className="inline-block h-5 w-5 shrink-0 rounded-full bg-slate-100" />
      )}
      <span className="font-medium text-slate-900">{row.away_team.name}</span>
    </div>
  )
}

function SotCell({ side }: { side: ModelComparisonSide | null | undefined }) {
  if (side == null || side.predicted_total_sot == null) {
    return <span className="text-amber-800">Mancante</span>
  }
  return (
    <span className="font-semibold tabular-nums text-slate-900">{formatNum(side.predicted_total_sot)}</span>
  )
}

function PickCell({ side }: { side: ModelComparisonSide | null | undefined }) {
  if (!side?.statistical_pick) return <span className="text-slate-500">—</span>
  return <span className="font-medium text-slate-900">{pickShortFromLabel(side.statistical_pick)}</span>
}

function ComparisonRowDesktop({
  row,
  competitionId,
  baseLabel,
  compareLabel,
}: {
  row: ModelComparisonRow
  competitionId: number
  baseLabel: string
  compareLabel: string
}) {
  const delta = row.delta
  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50/50">
      <td className="whitespace-nowrap py-2 pr-3 align-top text-slate-700">
        {formatKickoffReport(row.kickoff_at)}
      </td>
      <td className="min-w-[12rem] py-2 pr-3 align-top">
        <TeamMatchRow row={row} />
      </td>
      <td className="py-2 pr-3 align-top tabular-nums">
        <SotCell side={row.v20} />
      </td>
      <td className="py-2 pr-3 align-top tabular-nums">
        <SotCell side={row.v21} />
      </td>
      <td className="py-2 pr-3 align-top">
        {delta ? (
          <span
            className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold tabular-nums ${deltaBadgeClass(delta.total_sot)}`}
          >
            {deltaBadgeLabel(delta.total_sot)}
          </span>
        ) : (
          <span className="text-slate-500">—</span>
        )}
        {delta?.pick_changed ? (
          <span className="ml-1 inline-block rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[10px] font-medium text-violet-900">
            Pick cambiata
          </span>
        ) : null}
      </td>
      <td className="py-2 pr-3 align-top text-[11px]">
        <PickCell side={row.v20} />
      </td>
      <td className="py-2 pr-3 align-top text-[11px]">
        <PickCell side={row.v21} />
      </td>
      <td className="py-2 pr-3 align-top">
        {row.v21?.confidence_label ? (
          <span
            className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium ${confidenceBadgeClass(row.v21.confidence_label)}`}
          >
            {row.v21.confidence_label}
          </span>
        ) : (
          <span className="text-slate-500">—</span>
        )}
      </td>
      <td className="py-2 pr-3 align-top">
        <FormationStatusBadge status={row.lineup_status} />
      </td>
      <td className="py-2 align-top">
        <div className="flex flex-wrap gap-1.5 text-[10px]">
          <Link
            to={buildMatchAuditUrl({
              competitionId,
              fixtureId: row.fixture_id,
              modelVersion: V20_MODEL,
            })}
            className="rounded border border-slate-200 bg-white px-2 py-1 font-medium text-slate-700 hover:bg-slate-50"
            title={baseLabel}
          >
            Audit v2.0
          </Link>
          <Link
            to={buildMatchAuditUrl({
              competitionId,
              fixtureId: row.fixture_id,
              modelVersion: V21_MODEL,
            })}
            className="rounded border border-indigo-200 bg-indigo-50 px-2 py-1 font-medium text-indigo-900 hover:bg-indigo-100"
            title={compareLabel}
          >
            Audit v2.1
          </Link>
        </div>
      </td>
    </tr>
  )
}

function ComparisonCardMobile({
  row,
  competitionId,
  baseLabel,
  compareLabel,
}: {
  row: ModelComparisonRow
  competitionId: number
  baseLabel: string
  compareLabel: string
}) {
  const delta = row.delta
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <p className="text-[11px] text-slate-600">{formatKickoffReport(row.kickoff_at)}</p>
      <div className="mt-2">
        <TeamMatchRow row={row} />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
        <div>
          <p className="text-slate-500">{baseLabel}</p>
          <p className="font-semibold tabular-nums">
            {row.v20 && row.v20.predicted_total_sot != null ? formatNum(row.v20.predicted_total_sot) : '—'}
          </p>
          <p className="text-slate-700">{pickShortLabel(row.v20?.statistical_pick)}</p>
        </div>
        <div>
          <p className="text-slate-500">{compareLabel}</p>
          <p className="font-semibold tabular-nums">
            {row.v21 && row.v21.predicted_total_sot != null ? formatNum(row.v21.predicted_total_sot) : '—'}
          </p>
          <p className="text-slate-700">{pickShortLabel(row.v21?.statistical_pick)}</p>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {delta ? (
          <span
            className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold ${deltaBadgeClass(delta.total_sot)}`}
          >
            {deltaBadgeLabel(delta.total_sot)}
          </span>
        ) : null}
        {delta?.pick_changed ? (
          <span className="rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[10px] text-violet-900">
            Pick cambiata
          </span>
        ) : null}
        {row.v21?.confidence_label ? (
          <span className={`rounded-full border px-2 py-0.5 text-[10px] ${confidenceBadgeClass(row.v21.confidence_label)}`}>
            {row.v21.confidence_label}
          </span>
        ) : null}
        <FormationStatusBadge status={row.lineup_status} />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Link
          to={buildMatchAuditUrl({ competitionId, fixtureId: row.fixture_id, modelVersion: V20_MODEL })}
          className="text-[10px] font-medium text-slate-700 underline"
        >
          Audit v2.0
        </Link>
        <Link
          to={buildMatchAuditUrl({ competitionId, fixtureId: row.fixture_id, modelVersion: V21_MODEL })}
          className="text-[10px] font-medium text-indigo-800 underline"
        >
          Audit v2.1
        </Link>
      </div>
    </div>
  )
}

export function ModelComparisonSection({
  data,
  competitionId,
  loading,
}: {
  data: ModelComparisonResponse | null
  competitionId: number
  loading?: boolean
}) {
  const baseLabel = data?.base_model?.label ?? labelForModelVersion(V20_MODEL)
  const compareLabel = data?.compare_model?.label ?? labelForModelVersion(V21_MODEL)

  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Confronto modelli v2.0 vs v2.1</h2>
        <p className="mt-2 text-sm text-slate-600">Caricamento confronto…</p>
      </div>
    )
  }

  if (!data || data.status === 'error') {
    return (
      <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-4 text-sm text-amber-950">
        <h2 className="font-semibold">Confronto modelli v2.0 vs v2.1</h2>
        <p className="mt-1">{data?.message ?? 'Confronto non disponibile.'}</p>
      </div>
    )
  }

  if (!data.rows?.length) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Confronto modelli v2.0 vs v2.1</h2>
        <p className="mt-2 text-sm text-slate-600">Nessuna partita nel prossimo turno per il confronto.</p>
      </div>
    )
  }

  return (
    <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900">Confronto modelli v2.0 vs v2.1</h2>
        <p className="text-xs text-slate-600">
          {data.round ? `${data.round} · ` : ''}
          {data.matches_count} partite
        </p>
      </div>

      {data.warnings?.length ? (
        <details className="rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2 text-xs text-amber-950">
          <summary className="cursor-pointer font-medium">Warning confronto ({data.warnings.length})</summary>
          <ul className="mt-2 list-inside list-disc space-y-1">
            {data.warnings.slice(0, 8).map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </details>
      ) : null}

      <div className="hidden md:block">
        <table className="w-full table-fixed text-left text-[11px]">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50/80 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              <th className="w-[8%] py-2 pr-2">Data</th>
              <th className="w-[22%] py-2 pr-2">Match</th>
              <th className="w-[7%] py-2 pr-2">SOT v2.0</th>
              <th className="w-[7%] py-2 pr-2">SOT v2.1</th>
              <th className="w-[12%] py-2 pr-2">Delta</th>
              <th className="w-[10%] py-2 pr-2">Pick v2.0</th>
              <th className="w-[10%] py-2 pr-2">Pick v2.1</th>
              <th className="w-[8%] py-2 pr-2">Conf. v2.1</th>
              <th className="w-[10%] py-2 pr-2">Formazione</th>
              <th className="w-[10%] py-2">Azioni</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <ComparisonRowDesktop
                key={row.fixture_id}
                row={row}
                competitionId={competitionId}
                baseLabel={baseLabel}
                compareLabel={compareLabel}
              />
            ))}
          </tbody>
        </table>
      </div>

      <div className="space-y-3 md:hidden">
        {data.rows.map((row) => (
          <ComparisonCardMobile
            key={row.fixture_id}
            row={row}
            competitionId={competitionId}
            baseLabel={baseLabel}
            compareLabel={compareLabel}
          />
        ))}
      </div>
    </section>
  )
}
