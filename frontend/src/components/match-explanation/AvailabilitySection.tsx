import { useEffect, useState } from 'react'
import { DEFAULT_SEASON, getFixtureAvailability } from '../../lib/api'
import type {
  AvailabilityAuditMeta,
  AvailabilityTeamSide,
  FixtureAvailabilityResponse,
} from '../../types/fixtureAvailability'
import { formatFetchError } from '../../utils/formatFetchError'
import { AvailabilityDebugPanel } from './AvailabilityDebugPanel'

const SUBTITLE =
  'Mostra solo i record collegati alla fixture selezionata o override manuali validi per la data.'

const EMPTY_MSG =
  'Nessun indisponibile applicabile a questa partita trovato nel DB.'

const DEBUG_HINT =
  'Apri «Debug indisponibili» sotto per vedere request audit, conteggi DB, record esclusi e diagnosi.'

const GENERIC_NOTE =
  'Questi record esistono nel DB, ma non hanno fixture/date sufficienti per considerarli validi per questa partita.'

function fmtNum(v: number | null | undefined, d: number): string {
  if (v == null) return '—'
  return v.toFixed(d)
}

function sourceBadgeLabel(r: Row): string | null {
  if (r.source_label) return r.source_label
  if (r.source === 'api_football_sidelined') return 'Sidelined API'
  if (r.source === 'api_football_injuries') return 'Injuries API'
  return null
}

type Row = import('../../types/fixtureAvailability').AvailabilityPlayerRow

function AvailabilityTable({ rows }: { rows: Row[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full text-left text-[11px]">
        <thead className="bg-slate-50 text-slate-600">
          <tr>
            <th className="px-2 py-1.5 font-medium">Giocatore</th>
            <th className="px-2 py-1.5 font-medium">Fonte</th>
            <th className="px-2 py-1.5 font-medium">Status</th>
            <th className="px-2 py-1.5 font-medium">Tipo</th>
            <th className="px-2 py-1.5 font-medium">Motivo</th>
            <th className="px-2 py-1.5 font-medium">Scope</th>
            <th className="px-2 py-1.5 font-medium">SOT/90</th>
            <th className="px-2 py-1.5 font-medium">Impact</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.api_player_id ?? r.player_name}-${i}`} className="border-t border-slate-100">
              <td className="px-2 py-1.5 font-medium text-slate-900">
                <span className="inline-flex flex-wrap items-center gap-1">
                  {r.player_name}
                  {r.is_top_shooter ? (
                    <span className="rounded border border-violet-200 bg-violet-50 px-1 py-px text-[9px] font-medium text-violet-800">
                      Top shooter
                    </span>
                  ) : null}
                  {r.high_impact ? (
                    <span className="rounded border border-amber-200 bg-amber-50 px-1 py-px text-[9px] font-medium text-amber-900">
                      Impatto alto
                    </span>
                  ) : null}
                </span>
              </td>
              <td className="px-2 py-1.5">
                {sourceBadgeLabel(r) ? (
                  <span
                    className={
                      r.source === 'api_football_sidelined'
                        ? 'rounded border border-indigo-200 bg-indigo-50 px-1 py-px text-[9px] font-medium text-indigo-900'
                        : 'rounded border border-sky-200 bg-sky-50 px-1 py-px text-[9px] font-medium text-sky-900'
                    }
                  >
                    {sourceBadgeLabel(r)}
                  </span>
                ) : (
                  <span className="text-slate-400">—</span>
                )}
              </td>
              <td className="px-2 py-1.5 text-slate-700">{r.availability_status}</td>
              <td className="px-2 py-1.5 text-slate-600">{r.availability_type ?? '—'}</td>
              <td className="px-2 py-1.5 text-slate-600">{r.reason ?? '—'}</td>
              <td className="px-2 py-1.5 text-slate-500">{r.record_scope ?? '—'}</td>
              <td className="px-2 py-1.5 tabular-nums">{fmtNum(r.shots_on_per90, 2)}</td>
              <td className="px-2 py-1.5 tabular-nums">{fmtNum(r.shooting_impact_score, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TeamAvailabilityCard({ side }: { side: AvailabilityTeamSide }) {
  const applicable = side.applicable_records ?? side.players ?? []
  const generic = side.generic_records_not_applied ?? []

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/40 p-3">
      <div className="mb-3 flex flex-wrap items-baseline gap-2">
        <h3 className="text-sm font-semibold text-slate-900">{side.team_name}</h3>
        <span className="text-[11px] text-slate-500">
          {applicable.length} indisponibili applicabili
        </span>
      </div>
      {applicable.length === 0 ? (
        <p className="text-[11px] text-slate-500">Nessun indisponibile applicabile per questa squadra.</p>
      ) : (
        <AvailabilityTable rows={applicable} />
      )}
      {generic.length > 0 ? (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50/60 p-2">
          <p className="text-[11px] font-semibold text-amber-950">Record generici non applicati</p>
          <p className="mt-1 text-[10px] text-amber-900">{GENERIC_NOTE}</p>
          <div className="mt-2">
            <AvailabilityTable rows={generic} />
          </div>
        </div>
      ) : null}
    </div>
  )
}

export function AvailabilitySection({
  fixtureId,
  season = DEFAULT_SEASON,
}: {
  fixtureId: number
  season?: number
}) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [emptyApplicable, setEmptyApplicable] = useState(false)
  const [emptyMessage, setEmptyMessage] = useState(EMPTY_MSG)
  const [home, setHome] = useState<AvailabilityTeamSide | null>(null)
  const [away, setAway] = useState<AvailabilityTeamSide | null>(null)
  const [qualityNote, setQualityNote] = useState<string | null>(null)
  const [fixtureLabel, setFixtureLabel] = useState<string | null>(null)
  const [auditResponse, setAuditResponse] = useState<FixtureAvailabilityResponse | null>(null)
  const [auditMeta, setAuditMeta] = useState<AvailabilityAuditMeta | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      setEmptyApplicable(false)
      const auditUrl = `/api/debug/sot/fixture/${fixtureId}/availability`
      const t0 = performance.now()
      try {
        const data = await getFixtureAvailability(fixtureId)
        const durationMs = Math.round(performance.now() - t0)
        if (cancelled) return

        setAuditResponse(data)
        setAuditMeta({
          url: auditUrl,
          httpStatus: 200,
          durationMs,
        })

        if (data.status === 'error') {
          setError(data.message || 'Impossibile caricare le indisponibilità.')
          return
        }
        setFixtureLabel(data.fixture_label ?? null)
        setQualityNote(data.quality?.note ?? null)
        const homeApplicable =
          (data.home?.applicable_records ?? data.home?.players ?? []).length
        const awayApplicable =
          (data.away?.applicable_records ?? data.away?.players ?? []).length
        if (homeApplicable + awayApplicable === 0) {
          setEmptyApplicable(true)
          setEmptyMessage(data.message || EMPTY_MSG)
          setHome(data.home ?? null)
          setAway(data.away ?? null)
          return
        }
        if (!data.home || !data.away) {
          setError('Risposta availability incompleta.')
          return
        }
        setHome(data.home)
        setAway(data.away)
      } catch (e) {
        if (!cancelled) {
          setError(formatFetchError(e, `GET .../fixture/${fixtureId}/availability`))
          setAuditMeta({
            url: auditUrl,
            httpStatus: 0,
            durationMs: Math.round(performance.now() - t0),
            error: formatFetchError(e, auditUrl),
          })
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [fixtureId])

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-slate-50/80 px-4 py-2.5">
        <h2 className="text-sm font-semibold tracking-tight text-slate-900">
          Indisponibili per questa partita
        </h2>
        {fixtureLabel ? (
          <p className="mt-0.5 text-[11px] font-medium text-slate-700">{fixtureLabel}</p>
        ) : null}
        <p className="mt-1 text-[11px] leading-relaxed text-slate-600">{SUBTITLE}</p>
      </div>
      <div className="p-4">
        {loading ? (
          <p className="text-xs text-slate-500">Caricamento indisponibilità…</p>
        ) : error ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">{error}</p>
        ) : emptyApplicable ? (
          <div className="space-y-4">
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">
              {emptyMessage}
            </p>
            <p className="text-[10px] text-slate-500">{DEBUG_HINT}</p>
            {home || away ? (
              <div className="flex flex-col gap-4">
                {home ? <TeamAvailabilityCard side={home} /> : null}
                {away ? <TeamAvailabilityCard side={away} /> : null}
              </div>
            ) : null}
          </div>
        ) : home && away ? (
          <div className="flex flex-col gap-4">
            <TeamAvailabilityCard side={home} />
            <TeamAvailabilityCard side={away} />
            {qualityNote ? <p className="text-[10px] text-slate-500">{qualityNote}</p> : null}
          </div>
        ) : null}

        {!loading ? (
          <AvailabilityDebugPanel
            fixtureId={fixtureId}
            season={season}
            auditResponse={auditResponse}
            auditMeta={auditMeta}
          />
        ) : null}
      </div>
    </section>
  )
}
