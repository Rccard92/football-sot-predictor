import { useCallback, useMemo, useState } from 'react'
import {
  DEFAULT_SEASON,
  postCompetitionSportApiLineupsIngest,
  postRefreshNextRoundSportApiLineups,
  type LineupRefreshImpactPayload,
  type UpcomingActiveMatchRow,
} from '../../lib/api'
import { useCompetition } from '../../contexts/CompetitionContext'
import { V20_MODEL } from '../../lib/modelVersions'
import { formatImpactLine } from '../../utils/lineupRefreshImpactDisplay'
import {
  impactsFromRefreshResults,
  mergeMatchesWithImpacts,
  reportUsesV20Predictions,
} from './quickPlayImpactMerge'
import {
  getRowDelta,
  getRowDirection,
  getRowMatchName,
  getRowReason,
  isCompetitionLineupsSummary,
  isRoundRefreshRow,
  isRoundRefreshSummary,
  type RefreshSummary,
} from './quickPlayRefreshTypes'
import { QuickPlayReportMobile } from './QuickPlayReportMobile'
import { QuickPlayReportTable } from './QuickPlayReportTable'

export function QuickPlayReportSection({
  matches,
  modelVersion,
  onRefreshComplete,
  onOpenDetail,
  selectedFixtureId,
}: {
  matches: UpcomingActiveMatchRow[]
  modelVersion: string | null
  onRefreshComplete: () => void | Promise<void>
  onOpenDetail?: (fixtureId: number) => void
  selectedFixtureId?: number | null
}) {
  const { selectedCompetitionId } = useCompetition()
  const [refreshBusy, setRefreshBusy] = useState(false)
  const [refreshResult, setRefreshResult] = useState<RefreshSummary | null>(null)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [impactOverrides, setImpactOverrides] = useState<Record<number, LineupRefreshImpactPayload>>({})

  const displayMatches = useMemo(
    () => mergeMatchesWithImpacts(matches, impactOverrides),
    [matches, impactOverrides],
  )

  const runRefresh = useCallback(async () => {
    const n = matches.length
    const est = n
    const msg = `Aggiornare le formazioni SportAPI per ${n} partite del turno?\n\nChiamate SportAPI stimate: circa ${est} (mapping + lineups dove necessario).\n\nLe partite aggiornate di recente (<10 min) verranno saltate.`
    if (!window.confirm(msg)) return

    setRefreshBusy(true)
    setRefreshError(null)
    setRefreshResult(null)
    try {
      const regenerateV20 = reportUsesV20Predictions(matches, modelVersion, V20_MODEL)
      const out =
        selectedCompetitionId != null
          ? await postCompetitionSportApiLineupsIngest(selectedCompetitionId, {
              scope: 'next_round',
              dryRun: false,
              regenerateV20,
              timeoutMs: 600_000,
            })
          : await postRefreshNextRoundSportApiLineups(DEFAULT_SEASON, {
              regenerateV20,
              timeoutMs: 600_000,
            })
      setRefreshResult(out)
      if (isRoundRefreshSummary(out)) {
        const merged = impactsFromRefreshResults(out.results)
        if (Object.keys(merged).length) {
          setImpactOverrides((prev) => ({ ...prev, ...merged }))
        }
      }
      await onRefreshComplete()
    } catch (e) {
      setRefreshError(e instanceof Error ? e.message : String(e))
    } finally {
      setRefreshBusy(false)
    }
  }, [matches, modelVersion, onRefreshComplete, selectedCompetitionId])

  const lineupStatusCounts = useMemo(() => {
    let withLineup = 0
    let withoutLineup = 0
    for (const m of matches) {
      if (m.lineup_status?.has_lineup) withLineup += 1
      else withoutLineup += 1
    }
    return { withLineup, withoutLineup }
  }, [matches])

  if (!matches.length) return null

  const roundSummary = isRoundRefreshSummary(refreshResult) ? refreshResult : null
  const ingestSummary = isCompetitionLineupsSummary(refreshResult) ? refreshResult : null

  const errors = (refreshResult?.results ?? []).filter(
    (r) => r.status === 'error' || r.status === 'lineups_failed' || r.status === 'mapping_failed',
  )

  const impactRows = roundSummary
    ? (roundSummary.results ?? []).filter(isRoundRefreshRow).filter((r) => r.direction_total)
    : []

  const ingestRows = ingestSummary?.results ?? []

  const fixturesChecked = roundSummary
    ? roundSummary.total_fixtures
    : (ingestSummary?.fixtures_checked ?? 0)

  const formationsUpdated = roundSummary
    ? roundSummary.updated
    : (ingestSummary?.lineups_imported ?? 0)

  const partialLineupWarning =
    lineupStatusCounts.withLineup > 0 && lineupStatusCounts.withoutLineup > 0
      ? `Formazioni parziali: ${lineupStatusCounts.withLineup} partite con lineup, ${lineupStatusCounts.withoutLineup} senza.`
      : null

  return (
    <section className="overflow-hidden rounded-2xl border border-indigo-200/80 bg-white shadow-sm">
      <div className="border-b border-indigo-100 bg-indigo-50/40 px-4 py-3">
        <h2 className="text-sm font-semibold tracking-tight text-indigo-950">Report rapido giocate</h2>
        <p className="mt-1 text-[11px] leading-relaxed text-slate-600">
          Vista sintetica delle indicazioni SOT del prossimo turno. Apri il dettaglio per vedere il ragionamento
          completo.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={refreshBusy}
            onClick={() => void runRefresh()}
            className="rounded-md border border-violet-300 bg-white px-3 py-1.5 text-[11px] font-medium text-violet-900 hover:bg-violet-50 disabled:opacity-50"
          >
            {refreshBusy ? 'Aggiornamento in corso…' : 'Aggiorna formazioni SportAPI del turno'}
          </button>
        </div>
        <p className="mt-1 text-[10px] text-slate-500">
          Richiama le probabili formazioni e gli indisponibili per tutte le partite del prossimo turno.
        </p>
        {partialLineupWarning ? (
          <p className="mt-2 text-[11px] text-amber-800">{partialLineupWarning}</p>
        ) : null}
        {refreshError ? <p className="mt-2 text-[11px] text-rose-700">{refreshError}</p> : null}
        {refreshResult ? (
          <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50/80 px-3 py-2 text-[11px] text-emerald-950">
            <p className="font-semibold">
              {ingestSummary ? 'Import lineups completato' : 'Aggiornamento completato'}
            </p>
            <ul className="mt-1 list-inside list-disc">
              <li>{fixturesChecked} partite controllate</li>
              <li>{formationsUpdated} formazioni aggiornate</li>
              {roundSummary && roundSummary.up_count != null ? (
                <li>
                  {roundSummary.up_count} pronostici saliti · {roundSummary.down_count ?? 0} scesi ·{' '}
                  {roundSummary.flat_count ?? 0} stabili
                </li>
              ) : null}
              {ingestSummary ? (
                <>
                  <li>{ingestSummary.mappings_found} mapping trovati</li>
                  <li>{ingestSummary.mappings_uncertain} mapping incerti</li>
                  <li>{ingestSummary.missing_players_imported} indisponibili importati</li>
                  <li>{ingestSummary.predictions_regenerated} prediction ricalcolate</li>
                </>
              ) : null}
            </ul>
            {ingestSummary?.warnings?.length ? (
              <ul className="mt-2 list-inside list-disc text-amber-900">
                {ingestSummary.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            ) : null}
            {impactRows.length > 0 ? (
              <details className="mt-2 border-t border-emerald-200/80 pt-2">
                <summary className="cursor-pointer text-[10px] font-medium text-emerald-950">
                  Dettagli variazioni ({impactRows.length})
                </summary>
                <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-[10px]">
                  {impactRows.map((r) => (
                    <li key={r.fixture_id}>
                      <span className="font-medium">{getRowMatchName(r)}</span>:{' '}
                      {formatImpactLine(getRowDirection(r), getRowDelta(r), getRowReason(r))}
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
            {ingestSummary && ingestRows.length > 0 ? (
              <details className="mt-2 border-t border-emerald-200/80 pt-2">
                <summary className="cursor-pointer text-[10px] font-medium text-emerald-950">
                  Dettagli fixture ({ingestRows.length})
                </summary>
                <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-[10px]">
                  {ingestRows.map((r) => (
                    <li key={r.fixture_id}>
                      <span className="font-medium">{getRowMatchName(r)}</span>
                      {r.status ? ` — ${r.status}` : ''}
                      {r.confidence != null ? ` (conf. ${r.confidence})` : ''}
                      {getRowReason(r) ? ` — ${getRowReason(r)}` : ''}
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </div>
        ) : null}
        {errors.length > 0 ? (
          <details className="mt-2 rounded-lg border border-amber-200 bg-amber-50/60 px-2 py-1">
            <summary className="cursor-pointer px-1 py-1 text-[11px] font-medium text-amber-950">
              Dettagli aggiornamento ({errors.length})
            </summary>
            <ul className="mb-2 list-inside list-disc px-2 text-[10px] text-amber-900">
              {errors.map((r) => (
                <li key={r.fixture_id}>
                  Fixture {r.fixture_id}: {r.status}
                  {r.error ? ` — ${r.error}` : ''}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>

      <div className="p-2 md:p-4">
        <QuickPlayReportTable
          matches={displayMatches}
          onOpenDetail={onOpenDetail}
          selectedFixtureId={selectedFixtureId}
        />
        <QuickPlayReportMobile
          matches={displayMatches}
          onOpenDetail={onOpenDetail}
          selectedFixtureId={selectedFixtureId}
        />
      </div>
    </section>
  )
}
