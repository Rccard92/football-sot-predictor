import { useCallback, useMemo, useState } from 'react'
import {
  DEFAULT_SEASON,
  postRefreshNextRoundSportApiLineups,
  type LineupRefreshImpactPayload,
  type SportApiRoundRefreshSummary,
  type UpcomingActiveMatchRow,
} from '../../lib/api'
import { V20_MODEL } from '../../lib/modelVersions'
import { formatImpactLine } from '../../utils/lineupRefreshImpactDisplay'
import {
  impactsFromRefreshResults,
  mergeMatchesWithImpacts,
  reportUsesV20Predictions,
} from './quickPlayImpactMerge'
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
  const [refreshBusy, setRefreshBusy] = useState(false)
  const [refreshResult, setRefreshResult] = useState<SportApiRoundRefreshSummary | null>(null)
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
      const out = await postRefreshNextRoundSportApiLineups(DEFAULT_SEASON, {
        regenerateV20,
        timeoutMs: 600_000,
      })
      setRefreshResult(out)
      const merged = impactsFromRefreshResults(out.results)
      if (Object.keys(merged).length) {
        setImpactOverrides((prev) => ({ ...prev, ...merged }))
      }
      await onRefreshComplete()
    } catch (e) {
      setRefreshError(e instanceof Error ? e.message : String(e))
    } finally {
      setRefreshBusy(false)
    }
  }, [matches, modelVersion, onRefreshComplete])

  if (!matches.length) return null

  const errors = (refreshResult?.results ?? []).filter(
    (r) => r.status === 'error' || r.status === 'lineups_failed' || r.status === 'mapping_failed',
  )

  const impactRows = (refreshResult?.results ?? []).filter((r) => r.direction_total)

  const formationsUpdated = refreshResult?.updated ?? 0

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
        {refreshError ? <p className="mt-2 text-[11px] text-rose-700">{refreshError}</p> : null}
        {refreshResult ? (
          <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50/80 px-3 py-2 text-[11px] text-emerald-950">
            <p className="font-semibold">Aggiornamento completato</p>
            <ul className="mt-1 list-inside list-disc">
              <li>{refreshResult.total_fixtures} partite controllate</li>
              <li>{formationsUpdated} formazioni aggiornate</li>
              {refreshResult.up_count != null ? (
                <li>
                  {refreshResult.up_count} pronostici saliti · {refreshResult.down_count ?? 0} scesi ·{' '}
                  {refreshResult.flat_count ?? 0} stabili
                </li>
              ) : null}
            </ul>
            {impactRows.length > 0 ? (
              <details className="mt-2 border-t border-emerald-200/80 pt-2">
                <summary className="cursor-pointer text-[10px] font-medium text-emerald-950">
                  Dettagli variazioni ({impactRows.length})
                </summary>
                <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-[10px]">
                  {impactRows.map((r) => (
                    <li key={r.fixture_id}>
                      <span className="font-medium">{r.match_name ?? `Fixture ${r.fixture_id}`}</span>:{' '}
                      {formatImpactLine(r.direction_total, r.delta_total_sot, r.main_reason)}
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
