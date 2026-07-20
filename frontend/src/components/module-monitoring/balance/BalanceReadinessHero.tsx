import type { BalanceReadinessOverview } from '../../../lib/cecchinoModuleMonitoringApi'
import {
  balanceDecisionLabelIt,
  collectionHealthLabelIt,
  HERO_BASE,
  operationalStatusLabelIt,
  scientificStatusLabelIt,
} from '../moduleMonitoringUi'

type Props = {
  overview: BalanceReadinessOverview | null
}

export function BalanceReadinessHero({ overview }: Props) {
  if (!overview) {
    return (
      <div className={`${HERO_BASE} p-6`}>
        <h3 className="text-lg font-semibold text-slate-800">Readiness Balance v5</h3>
        <p className="mt-1 text-sm text-slate-600">
          Dati readiness non disponibili per il periodo selezionato.
        </p>
      </div>
    )
  }

  const health = overview.prospective_collection_health
  const healthLabel =
    health?.label_it || collectionHealthLabelIt(health?.status) || '—'

  return (
    <div className={`${HERO_BASE} p-6`}>
      <h3 className="text-lg font-semibold text-slate-800">Readiness Balance v5</h3>
      <p className="mt-1 text-sm text-slate-600">
        {overview.banner_it ||
          'Stato operativo, maturità scientifica e decisione restano separati. Signals non si attiva automaticamente.'}
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Operativo</p>
          <p className="text-sm font-medium text-slate-800">
            {overview.operational_status_label_it ||
              operationalStatusLabelIt(overview.operational_status)}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Maturità scientifica</p>
          <p className="text-sm font-medium text-slate-800">
            {overview.scientific_maturity_label_it ||
              scientificStatusLabelIt(overview.scientific_maturity)}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Decisione corrente</p>
          <p className="text-sm font-medium text-slate-800">
            {overview.current_decision_label_it ||
              balanceDecisionLabelIt(overview.current_decision)}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Revisione manuale</p>
          <p className="text-sm font-medium text-slate-800">
            {overview.manual_review_status_label_it || overview.manual_review_status || '—'}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Integrazione Signals</p>
          <p className="text-sm font-medium text-slate-800">
            {overview.signals_integration_status_label_it ||
              overview.signals_integration_status ||
              '—'}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Salute raccolta</p>
          <p className="text-sm font-medium text-slate-800">{healthLabel}</p>
        </div>
      </div>

      <div className="mt-4 border-t border-slate-200/50 pt-3 text-xs text-slate-600">
        Revisione teorica più precoce:{' '}
        <span className="font-medium text-slate-800">
          {overview.earliest_theoretical_review_at || 'non calcolabile'}
        </span>
        {overview.coverage ? (
          <>
            {' '}
            · Storico diagnostico: {overview.coverage.historical_diagnostic ?? 0} · Prospettico:{' '}
            {overview.coverage.prospective_persisted ?? 0}
          </>
        ) : null}
      </div>
    </div>
  )
}
