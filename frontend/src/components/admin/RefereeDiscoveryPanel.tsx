import { useCallback, useMemo, useState } from 'react'
import {
  AdminHttpError,
  DEFAULT_SEASON,
  postRefereeImportSeasonHistory,
  postRefereeMatchContext,
  postRefereeProfile,
  postRefereeRecentHistory,
  postRefereeSyncFixture,
  type RefereeContextBlock,
  type RefereeMatchContextResponse,
  type RefereeProfileResponse,
  type RefereeSyncFixtureResponse,
} from '../../lib/api'

const DEFAULT_LEAGUE_ID = 135

type ProfileRow = {
  key: string
  label: string
  matches_count?: number
  avg_yellow_cards?: number | null
  avg_red_cards?: number | null
  severity_label?: string | null
  sample_quality?: string | null
  data_source?: string
}

function formatRefereeError(e: unknown): string {
  if (e instanceof AdminHttpError) {
    if (e.status === 401) return 'Autenticazione Admin richiesta.'
    return e.message || `Errore HTTP ${e.status}`
  }
  return e instanceof Error ? e.message : String(e)
}

function rowFromProfile(p: RefereeProfileResponse, label: string, key: string): ProfileRow {
  return {
    key,
    label: p.profile_label ?? label,
    matches_count: p.matches_count ?? p.last_matches_count,
    avg_yellow_cards: p.avg_yellow_cards,
    avg_red_cards: p.avg_red_cards,
    severity_label: p.severity_label,
    sample_quality: p.sample_quality,
    data_source: p.data_source,
  }
}

function rowFromContext(c: RefereeContextBlock | undefined, key: string): ProfileRow {
  return {
    key,
    label: c?.label ?? key,
    matches_count: c?.matches_count,
    avg_yellow_cards: c?.avg_yellow_cards,
    avg_red_cards: c?.avg_red_cards,
    severity_label: c?.severity_label,
    sample_quality: c?.sample_quality,
    data_source: c?.data_source,
  }
}

export function RefereeDiscoveryPanel() {
  const [fixtureId, setFixtureId] = useState('')
  const [apiFixtureId, setApiFixtureId] = useState('')
  const [syncBusy, setSyncBusy] = useState(false)
  const [syncResult, setSyncResult] = useState<RefereeSyncFixtureResponse | null>(null)
  const [syncError, setSyncError] = useState<string | null>(null)

  const [refereeName, setRefereeName] = useState('')
  const [profileFixtureId, setProfileFixtureId] = useState('')
  const [leagueId, setLeagueId] = useState(String(DEFAULT_LEAGUE_ID))
  const [season, setSeason] = useState(String(DEFAULT_SEASON))

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [seasonProfile, setSeasonProfile] = useState<RefereeProfileResponse | null>(null)
  const [recentProfile, setRecentProfile] = useState<RefereeProfileResponse | null>(null)
  const [matchContext, setMatchContext] = useState<RefereeMatchContextResponse | null>(null)

  const resolvedReferee = syncResult?.referee ?? refereeName.trim()
  const resolvedFixtureId = syncResult?.fixture_id ?? (profileFixtureId.trim() ? Number(profileFixtureId) : null)

  const profileRows: ProfileRow[] = useMemo(() => {
    const rows: ProfileRow[] = []
    if (seasonProfile?.status === 'success' && (seasonProfile.matches_count ?? 0) > 0) {
      rows.push(rowFromProfile(seasonProfile, 'Serie A stagione corrente', 'season'))
    }
    if (recentProfile?.status === 'success' && (recentProfile.matches_count ?? 0) > 0) {
      rows.push(rowFromProfile(recentProfile, 'Ultime 20 disponibili', 'recent'))
    }
    if (matchContext?.status === 'success') {
      rows.push(rowFromContext(matchContext.home_team_context, 'home'))
      rows.push(rowFromContext(matchContext.away_team_context, 'away'))
      rows.push(rowFromContext(matchContext.direct_h2h_context, 'h2h'))
    }
    return rows
  }, [seasonProfile, recentProfile, matchContext])

  const runSync = async () => {
    const fid = fixtureId.trim() ? Number(fixtureId) : null
    const afid = apiFixtureId.trim() ? Number(apiFixtureId) : null
    if ((fid == null) === (afid == null)) {
      setSyncError('Indica fixture_id oppure api_fixture_id (uno solo).')
      return
    }
    setSyncBusy(true)
    setSyncError(null)
    setSyncResult(null)
    try {
      const out = await postRefereeSyncFixture(
        fid != null ? { fixture_id: fid } : { api_fixture_id: afid! },
      )
      setSyncResult(out)
      if (out.referee) setRefereeName(out.referee)
      if (out.fixture_id) setProfileFixtureId(String(out.fixture_id))
      if (!out.saved && out.reason === 'referee_not_available') {
        setSyncError('Arbitro non ancora disponibile su API-Sports per questa partita.')
      } else if (out.status === 'error') {
        setSyncError(out.message ?? 'Errore sync')
      }
    } catch (e) {
      setSyncError(formatRefereeError(e))
    } finally {
      setSyncBusy(false)
    }
  }

  const bodyBase = useCallback(() => {
    const name = resolvedReferee
    if (!name) return null
    return {
      referee_name: name,
      league_id: Number(leagueId) || DEFAULT_LEAGUE_ID,
      season: Number(season) || DEFAULT_SEASON,
    }
  }, [resolvedReferee, leagueId, season])

  const runSeasonProfile = async () => {
    const base = bodyBase()
    if (!base) {
      setError('Indica arbitro (sync fixture o nome).')
      return
    }
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      const out = await postRefereeProfile({
        ...base,
        fixture_id: resolvedFixtureId ?? undefined,
      })
      setSeasonProfile(out)
      if (out.coverage_note) setInfo(out.coverage_note)
      if (out.status === 'error') setError(out.message ?? 'Errore profilo')
      else if ((out.matches_count ?? 0) === 0) {
        setError('Nessun dato in cache: importa storico stagione.')
      }
    } catch (e) {
      setError(formatRefereeError(e))
    } finally {
      setBusy(false)
    }
  }

  const runImport = async () => {
    const base = bodyBase()
    if (!base) {
      setError('Indica arbitro prima dell\'import.')
      return
    }
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      const out = await postRefereeImportSeasonHistory(base)
      setInfo(
        out.message ??
          `Scansionate ${out.fixtures_scanned ?? 0} · match arbitro ${out.referee_matches_found ?? 0} · cartellini ${out.card_data_found ?? 0}`,
      )
      if (out.match_warning) setInfo((prev) => `${prev ?? ''} ${out.match_warning}`)
    } catch (e) {
      setError(formatRefereeError(e))
    } finally {
      setBusy(false)
    }
  }

  const runRecent = async () => {
    const base = bodyBase()
    if (!base) return
    setBusy(true)
    setError(null)
    try {
      const out = await postRefereeRecentHistory({ referee_name: base.referee_name, limit: 20 })
      setRecentProfile(out)
      if ((out.matches_count ?? 0) === 0 && out.message) setInfo(out.message)
    } catch (e) {
      setError(formatRefereeError(e))
    } finally {
      setBusy(false)
    }
  }

  const runMatchContext = async () => {
    const fid = resolvedFixtureId
    if (!fid || !Number.isFinite(fid)) {
      setError('Serve fixture_id (da sync o input).')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const out = await postRefereeMatchContext({ fixture_id: fid })
      setMatchContext(out)
      if (out.status === 'error') setError(out.message ?? 'Errore contesto match')
    } catch (e) {
      setError(formatRefereeError(e))
    } finally {
      setBusy(false)
    }
  }

  const runAll = async () => {
    await runSeasonProfile()
    await runRecent()
    await runMatchContext()
  }

  return (
    <section className="rounded-xl border border-amber-200 bg-amber-50/40 p-4">
      <h2 className="text-sm font-semibold text-amber-950">Arbitri (discovery API-Sports)</h2>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-600">
        Sync, import storico e analisi contesto. Non influenza il modello SOT v2.0.
      </p>

      <div className="mt-4 rounded-lg border border-slate-200 bg-white/80 p-3">
        <h3 className="text-xs font-semibold text-slate-900">1. Arbitro assegnato</h3>
        <div className="mt-2 flex flex-wrap gap-2">
          <input
            type="number"
            placeholder="fixture_id"
            value={fixtureId}
            onChange={(e) => {
              setFixtureId(e.target.value)
              if (e.target.value) setApiFixtureId('')
            }}
            className="w-32 rounded border border-slate-200 px-2 py-1 text-xs"
          />
          <input
            type="number"
            placeholder="api_fixture_id"
            value={apiFixtureId}
            onChange={(e) => {
              setApiFixtureId(e.target.value)
              if (e.target.value) setFixtureId('')
            }}
            className="w-36 rounded border border-slate-200 px-2 py-1 text-xs"
          />
          <button
            type="button"
            disabled={syncBusy}
            onClick={() => void runSync()}
            className="rounded border border-amber-400 bg-white px-3 py-1 text-[11px] font-medium text-amber-950 hover:bg-amber-100 disabled:opacity-50"
          >
            {syncBusy ? 'Sync…' : 'Sync arbitro fixture'}
          </button>
        </div>
        {syncError ? <p className="mt-2 text-[11px] text-rose-700">{syncError}</p> : null}
        {syncResult?.status === 'success' ? (
          <div className="mt-2 text-[11px] text-slate-800">
            <p>
              <span className="font-medium">{syncResult.match}</span>
              {syncResult.referee ? (
                <>
                  {' '}
                  · <span className="font-semibold">{syncResult.referee}</span>
                  {syncResult.saved ? ' · salvato' : ' · non salvato'}
                </>
              ) : (
                ' · arbitro non disponibile'
              )}
            </p>
          </div>
        ) : null}
        <div className="mt-2 flex flex-wrap gap-2">
          <input
            type="text"
            placeholder="Nome arbitro"
            value={refereeName}
            onChange={(e) => setRefereeName(e.target.value)}
            className="min-w-[140px] flex-1 rounded border border-slate-200 px-2 py-1 text-xs"
          />
          <input
            type="number"
            placeholder="fixture contesto"
            value={profileFixtureId}
            onChange={(e) => setProfileFixtureId(e.target.value)}
            className="w-28 rounded border border-slate-200 px-2 py-1 text-xs"
          />
          <input
            type="number"
            placeholder="league"
            value={leagueId}
            onChange={(e) => setLeagueId(e.target.value)}
            className="w-20 rounded border border-slate-200 px-2 py-1 text-xs"
          />
          <input
            type="number"
            placeholder="season"
            value={season}
            onChange={(e) => setSeason(e.target.value)}
            className="w-20 rounded border border-slate-200 px-2 py-1 text-xs"
          />
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-slate-200 bg-white/80 p-3">
        <h3 className="text-xs font-semibold text-slate-900">2. Profili severità</h3>
        <div className="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => void runSeasonProfile()}
            className="rounded border border-amber-400 bg-white px-2 py-1 text-[11px] font-medium hover:bg-amber-100 disabled:opacity-50"
          >
            Calcola profilo stagione
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void runImport()}
            className="rounded border border-amber-400 bg-white px-2 py-1 text-[11px] font-medium hover:bg-amber-100 disabled:opacity-50"
          >
            Importa storico stagione
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void runMatchContext()}
            className="rounded border border-amber-400 bg-white px-2 py-1 text-[11px] font-medium hover:bg-amber-100 disabled:opacity-50"
          >
            Analizza contesto match
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void runAll()}
            className="rounded border border-slate-300 bg-slate-50 px-2 py-1 text-[11px] disabled:opacity-50"
          >
            Aggiorna tutti
          </button>
        </div>
        {error ? <p className="mt-2 text-[11px] text-rose-700">{error}</p> : null}
        {info ? <p className="mt-2 text-[11px] text-slate-700">{info}</p> : null}
        {seasonProfile?.fixtures_scanned != null ? (
          <p className="mt-2 text-[10px] text-slate-500">
            Scansionate {seasonProfile.fixtures_scanned} FT · arbitro {seasonProfile.fixtures_with_same_referee} ·
            con cartellini {seasonProfile.fixtures_with_card_data} · fonte {seasonProfile.data_source}
          </p>
        ) : null}
        {profileRows.length > 0 ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[520px] border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-600">
                  <th className="py-1 pr-2 font-medium">Profilo</th>
                  <th className="py-1 pr-2">Partite</th>
                  <th className="py-1 pr-2">Gialli</th>
                  <th className="py-1 pr-2">Rossi</th>
                  <th className="py-1 pr-2">Severità</th>
                  <th className="py-1 pr-2">Campione</th>
                  <th className="py-1">Fonte</th>
                </tr>
              </thead>
              <tbody>
                {profileRows.map((r) => (
                  <tr key={r.key} className="border-b border-slate-100">
                    <td className="py-1 pr-2 font-medium text-slate-800">{r.label}</td>
                    <td className="py-1 pr-2 tabular-nums">{r.matches_count ?? '—'}</td>
                    <td className="py-1 pr-2 tabular-nums">{r.avg_yellow_cards?.toFixed(2) ?? '—'}</td>
                    <td className="py-1 pr-2 tabular-nums">{r.avg_red_cards?.toFixed(2) ?? '—'}</td>
                    <td className="py-1 pr-2 capitalize">{r.severity_label ?? '—'}</td>
                    <td className="py-1 pr-2">{r.sample_quality ?? '—'}</td>
                    <td className="py-1">{r.data_source ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-2 text-[11px] text-slate-500">
            Esegui sync, import storico e calcolo profilo per popolare la tabella.
          </p>
        )}
      </div>
    </section>
  )
}
