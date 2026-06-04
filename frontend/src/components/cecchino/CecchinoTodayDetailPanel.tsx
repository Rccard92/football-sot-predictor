import type { CecchinoSignalsMatrix } from '../../lib/cecchinoApi'
import type { CecchinoTodayDetailResponse } from '../../lib/cecchinoTodayApi'
import { CecchinoKpiPanel } from './CecchinoKpiPanel'
import { CecchinoSignalsMatrixPanel } from './CecchinoSignalsMatrixPanel'

type Props = {
  detail: CecchinoTodayDetailResponse
}

export function CecchinoTodayDetailPanel({ detail }: Props) {
  if (detail.status !== 'ok') {
    return (
      <div className="rounded-lg border border-red-500/40 bg-red-950/30 p-4 text-sm text-red-200">
        {detail.message ?? 'Dettaglio non disponibile.'}
      </div>
    )
  }

  const output = detail.cecchino_output
  const finalOdds = (output?.final as Record<string, unknown>) || {}
  const signals = (detail.signals_matrix ?? output?.signals_matrix) as CecchinoSignalsMatrix | undefined

  return (
    <div className="space-y-4">
      <header className="rounded-lg border border-slate-600 bg-slate-900/60 p-4">
        <p className="text-xs uppercase tracking-wide text-slate-400">
          {detail.country_name} — {detail.league_name}
        </p>
        <h2 className="mt-1 text-lg font-semibold text-white">
          {detail.home_team_name} vs {detail.away_team_name}
        </h2>
        {detail.kickoff && (
          <p className="mt-1 text-sm text-slate-300">
            Kickoff: {new Date(detail.kickoff).toLocaleString('it-IT', { timeZone: 'Europe/Rome' })}
          </p>
        )}
        {detail.cecchino_link && (
          <a
            href={detail.cecchino_link}
            className="mt-3 inline-block text-sm text-sky-300 underline hover:text-sky-200"
          >
            Apri analisi Cecchino classica
          </a>
        )}
      </header>

      {detail.kpi_panel && (
        <CecchinoKpiPanel panel={detail.kpi_panel} bookmakerStatus={detail.kpi_panel.bookmaker_status} />
      )}

      {signals && (
        <CecchinoSignalsMatrixPanel matrix={signals} />
      )}

      {output?.final != null && (
        <section className="rounded-lg border border-slate-600 bg-slate-900/40 p-4 text-sm text-slate-200">
          <h3 className="mb-2 font-semibold text-white">Quote finali Cecchino</h3>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <span className="text-slate-400">1</span>
              <p className="font-mono">{String(finalOdds.quota_1 ?? '—')}</p>
            </div>
            <div>
              <span className="text-slate-400">X</span>
              <p className="font-mono">{String(finalOdds.quota_x ?? '—')}</p>
            </div>
            <div>
              <span className="text-slate-400">2</span>
              <p className="font-mono">{String(finalOdds.quota_2 ?? '—')}</p>
            </div>
          </div>
        </section>
      )}

      {(detail.warnings?.length ?? 0) > 0 && (
        <ul className="list-inside list-disc text-xs text-amber-200">
          {detail.warnings!.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
