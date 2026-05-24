import { useState } from 'react'
import {
  AdminHttpError,
  DEFAULT_SEASON,
  postRefereeProfile,
  postRefereeSyncFixture,
  type RefereeProfileResponse,
  type RefereeSyncFixtureResponse,
} from '../../lib/api'

const DEFAULT_LEAGUE_ID = 135

function formatRefereeError(e: unknown): string {
  if (e instanceof AdminHttpError) {
    if (e.status === 401) return 'Autenticazione Admin richiesta.'
    return e.message || `Errore HTTP ${e.status}`
  }
  return e instanceof Error ? e.message : String(e)
}

export function RefereeDiscoveryPanel() {
  const [fixtureId, setFixtureId] = useState('')
  const [apiFixtureId, setApiFixtureId] = useState('')
  const [syncBusy, setSyncBusy] = useState(false)
  const [syncResult, setSyncResult] = useState<RefereeSyncFixtureResponse | null>(null)
  const [syncError, setSyncError] = useState<string | null>(null)

  const [refereeName, setRefereeName] = useState('')
  const [useFixtureReferee, setUseFixtureReferee] = useState(false)
  const [profileFixtureId, setProfileFixtureId] = useState('')
  const [leagueId, setLeagueId] = useState(String(DEFAULT_LEAGUE_ID))
  const [season, setSeason] = useState(String(DEFAULT_SEASON))
  const [profileBusy, setProfileBusy] = useState(false)
  const [profileResult, setProfileResult] = useState<RefereeProfileResponse | null>(null)
  const [profileError, setProfileError] = useState<string | null>(null)

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

  const runProfile = async () => {
    setProfileBusy(true)
    setProfileError(null)
    setProfileResult(null)
    try {
      const body: {
        referee_name?: string
        league_id?: number
        season?: number
        fixture_id?: number
      } = {
        league_id: Number(leagueId) || DEFAULT_LEAGUE_ID,
        season: Number(season) || DEFAULT_SEASON,
      }
      if (useFixtureReferee) {
        const pfid = Number(profileFixtureId)
        if (!Number.isFinite(pfid)) {
          setProfileError('Indica fixture_id per derivare arbitro e stagione.')
          setProfileBusy(false)
          return
        }
        body.fixture_id = pfid
      } else if (refereeName.trim()) {
        body.referee_name = refereeName.trim()
      } else {
        setProfileError('Indica il nome arbitro oppure usa arbitro da fixture.')
        setProfileBusy(false)
        return
      }
      const out = await postRefereeProfile(body)
      setProfileResult(out)
      if (out.status === 'error') {
        setProfileError(out.message ?? 'Errore calcolo profilo')
      } else if (out.matches_count === 0) {
        setProfileError('Campione insufficiente: nessuna partita con cartellini.')
      } else if (out.sample_quality === 'low') {
        setProfileError(null)
      }
    } catch (e) {
      setProfileError(formatRefereeError(e))
    } finally {
      setProfileBusy(false)
    }
  }

  return (
    <section className="rounded-xl border border-amber-200 bg-amber-50/40 p-4">
      <h2 className="text-sm font-semibold text-amber-950">Arbitri (discovery API-Sports)</h2>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-600">
        Sincronizza l&apos;arbitro assegnato e calcola il profilo severità (media cartellini). Non influenza il
        modello SOT v2.0.
      </p>

      <div className="mt-4 rounded-lg border border-slate-200 bg-white/80 p-3">
        <h3 className="text-xs font-semibold text-slate-900">1. Sync arbitro fixture</h3>
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
            {syncBusy ? 'Sync…' : 'Sync arbitro'}
          </button>
        </div>
        {syncError ? <p className="mt-2 text-[11px] text-rose-700">{syncError}</p> : null}
        {syncResult?.status === 'success' && !syncError ? (
          <div className="mt-2 rounded border border-emerald-200 bg-emerald-50/80 px-2 py-1.5 text-[11px] text-emerald-950">
            <p>
              <span className="font-medium">{syncResult.match}</span>
              {syncResult.referee ? (
                <>
                  {' '}
                  · Arbitro: <span className="font-semibold">{syncResult.referee}</span>
                  {syncResult.saved ? ' (salvato)' : ''}
                </>
              ) : (
                ' · Arbitro non disponibile'
              )}
            </p>
          </div>
        ) : null}
      </div>

      <div className="mt-4 rounded-lg border border-slate-200 bg-white/80 p-3">
        <h3 className="text-xs font-semibold text-slate-900">2. Profilo severità</h3>
        <div className="mt-2 space-y-2">
          <label className="flex items-center gap-2 text-[11px] text-slate-700">
            <input
              type="checkbox"
              checked={useFixtureReferee}
              onChange={(e) => setUseFixtureReferee(e.target.checked)}
            />
            Usa arbitro da fixture
          </label>
          {useFixtureReferee ? (
            <input
              type="number"
              placeholder="fixture_id"
              value={profileFixtureId}
              onChange={(e) => setProfileFixtureId(e.target.value)}
              className="w-32 rounded border border-slate-200 px-2 py-1 text-xs"
            />
          ) : (
            <input
              type="text"
              placeholder="Nome arbitro"
              value={refereeName}
              onChange={(e) => setRefereeName(e.target.value)}
              className="w-full max-w-xs rounded border border-slate-200 px-2 py-1 text-xs"
            />
          )}
          <div className="flex flex-wrap gap-2">
            <input
              type="number"
              placeholder="league_id"
              value={leagueId}
              onChange={(e) => setLeagueId(e.target.value)}
              className="w-24 rounded border border-slate-200 px-2 py-1 text-xs"
            />
            <input
              type="number"
              placeholder="season"
              value={season}
              onChange={(e) => setSeason(e.target.value)}
              className="w-24 rounded border border-slate-200 px-2 py-1 text-xs"
            />
            <button
              type="button"
              disabled={profileBusy}
              onClick={() => void runProfile()}
              className="rounded border border-amber-400 bg-white px-3 py-1 text-[11px] font-medium text-amber-950 hover:bg-amber-100 disabled:opacity-50"
            >
              {profileBusy ? 'Calcolo…' : 'Calcola profilo'}
            </button>
          </div>
        </div>
        {profileError ? <p className="mt-2 text-[11px] text-rose-700">{profileError}</p> : null}
        {profileResult?.status === 'success' && profileResult.matches_count ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[320px] border-collapse text-[11px]">
              <tbody>
                <tr className="border-b border-slate-100">
                  <td className="py-1 pr-2 font-medium text-slate-600">Arbitro</td>
                  <td>{profileResult.referee_name}</td>
                </tr>
                <tr className="border-b border-slate-100">
                  <td className="py-1 pr-2 font-medium text-slate-600">Partite</td>
                  <td>{profileResult.matches_count}</td>
                </tr>
                <tr className="border-b border-slate-100">
                  <td className="py-1 pr-2 font-medium text-slate-600">Media gialli</td>
                  <td>{profileResult.avg_yellow_cards?.toFixed(2)}</td>
                </tr>
                <tr className="border-b border-slate-100">
                  <td className="py-1 pr-2 font-medium text-slate-600">Media rossi</td>
                  <td>{profileResult.avg_red_cards?.toFixed(2)}</td>
                </tr>
                <tr className="border-b border-slate-100">
                  <td className="py-1 pr-2 font-medium text-slate-600">Severità</td>
                  <td className="font-semibold capitalize">{profileResult.severity_label}</td>
                </tr>
                <tr>
                  <td className="py-1 pr-2 font-medium text-slate-600">Campione</td>
                  <td>{profileResult.sample_quality}</td>
                </tr>
              </tbody>
            </table>
            {profileResult.sample_quality === 'low' ? (
              <p className="mt-2 text-[10px] text-amber-800">Campione basso: interpretare con cautela.</p>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  )
}
