import type {
  ModelLimitations,
  UpcomingActiveMatchRow,
} from '../../lib/api'
import { formatKickoff, formatNum, formatSignedNum } from './format'
import { Link } from 'react-router-dom'

export function MatchCard({
  match,
}: {
  match: UpcomingActiveMatchRow
  limitations: ModelLimitations
}) {
  const home = match.home_prediction
  const away = match.away_prediction
  const mainHome = home?.expected_sot ?? null
  const mainAway = away?.expected_sot ?? null
  const mainTotal = match.total_expected_sot ?? null
  const homeB01 = home?.baseline_v01_expected_sot ?? null
  const awayB01 = away?.baseline_v01_expected_sot ?? null
  const homeDiff = home?.difference_from_v01 ?? null
  const awayDiff = away?.difference_from_v01 ?? null

  return (
    <article className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-gradient-to-b from-slate-50/80 to-white px-5 py-5 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {match.round ?? 'Giornata'}
          </p>
          <span className="rounded-full bg-emerald-50 px-3 py-0.5 text-xs font-medium text-emerald-800 ring-1 ring-emerald-100">
            Pre-partita
          </span>
        </div>
        <p className="mt-2 text-sm text-slate-600">{formatKickoff(match.kickoff_at)}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            {match.home_team.logo_url ? (
              <img src={match.home_team.logo_url} alt="" className="h-8 w-8 shrink-0 object-contain" />
            ) : null}
            <span className="text-sm font-semibold text-slate-900">{match.home_team.name}</span>
          </div>
          <span className="text-slate-400">vs</span>
          <div className="flex items-center gap-2">
            {match.away_team.logo_url ? (
              <img src={match.away_team.logo_url} alt="" className="h-8 w-8 shrink-0 object-contain" />
            ) : null}
            <span className="text-sm font-semibold text-slate-900">{match.away_team.name}</span>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-600">
          <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-800 ring-1 ring-slate-200">
            Modello: {match.model_version_used}
          </span>
        </div>
      </div>

      <div className="border-b border-slate-100 px-5 py-5 sm:px-6">
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{match.home_team.name}</p>
            <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-slate-900">
              {mainHome != null ? formatNum(mainHome) : '—'}
            </p>
            {homeB01 != null && homeDiff != null ? (
              homeDiff === 0 ? (
                <p className="mt-1 text-xs text-slate-600">Nessuna differenza rispetto alla baseline v0.1.</p>
              ) : (
                <p className="mt-1 text-xs text-slate-600">
                  Baseline v0.1: {formatNum(homeB01)} <span className="text-slate-500">· Δ {formatSignedNum(homeDiff)}</span>
                </p>
              )
            ) : null}
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Totale match</p>
            <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-slate-900">
              {mainTotal != null ? formatNum(mainTotal) : '—'}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{match.away_team.name}</p>
            <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-slate-900">
              {mainAway != null ? formatNum(mainAway) : '—'}
            </p>
            {awayB01 != null && awayDiff != null ? (
              awayDiff === 0 ? (
                <p className="mt-1 text-xs text-slate-600">Nessuna differenza rispetto alla baseline v0.1.</p>
              ) : (
                <p className="mt-1 text-xs text-slate-600">
                  Baseline v0.1: {formatNum(awayB01)} <span className="text-slate-500">· Δ {formatSignedNum(awayDiff)}</span>
                </p>
              )
            ) : null}
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-600">
          <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1">
            <Link
              to={`/match-variable-audit?fixture_id=${match.fixture_id}`}
              className="font-medium text-slate-700 underline"
            >
              Apri audit variabili
            </Link>
            {match.api_fixture_id ? (
              <Link
                to={`/admin?sportapi_fixture=${match.api_fixture_id}`}
                className="font-medium text-slate-700 underline"
              >
                Debug SportAPI
              </Link>
            ) : null}
          </span>
        </p>
      </div>

      <div className="border-t border-slate-100 px-5 py-4 sm:px-6">
        <details className="group rounded-2xl border border-slate-200 bg-slate-50/50">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-slate-800 marker:hidden [&::-webkit-details-marker]:hidden">
            <span className="flex items-center justify-between gap-2">
              Perché cambia rispetto alla v0.1?
              <span className="text-xs font-normal text-slate-500 group-open:hidden">Apri</span>
              <span className="hidden text-xs font-normal text-slate-500 group-open:inline">Chiudi</span>
            </span>
          </summary>
          <div className="space-y-3 border-t border-slate-200 px-4 py-4 text-sm text-slate-700">
            <p>
              {match.home_team.name}: v0.1 {homeB01 != null ? formatNum(homeB01) : '—'} · attivo{' '}
              {mainHome != null ? formatNum(mainHome) : '—'} · Δ {homeDiff != null ? formatSignedNum(homeDiff) : '—'}
            </p>
            <p>
              {match.away_team.name}: v0.1 {awayB01 != null ? formatNum(awayB01) : '—'} · attivo{' '}
              {mainAway != null ? formatNum(mainAway) : '—'} · Δ {awayDiff != null ? formatSignedNum(awayDiff) : '—'}
            </p>
            <p className="text-xs text-slate-600">
              Dettagli tecnici (variabili, pesi, contributi e formule) sono disponibili nella pagina <strong>Audit Variabili</strong>.
            </p>
          </div>
        </details>
      </div>
    </article>
  )
}

