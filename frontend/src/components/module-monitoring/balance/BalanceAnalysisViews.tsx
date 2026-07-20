import { BalanceEmpiricalAnalysisJobPanel } from './BalanceEmpiricalAnalysisJobPanel'
import { BalancePillarAnalysisShell } from './BalancePillarAnalysisShell'

type Props = {
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  cohortFilter?: string
}

export function BalanceEmpiricalOverview(props: Props) {
  return (
    <BalancePillarAnalysisShell
      key={`overview-${props.dateFrom}-${props.dateTo}-${props.cohortFilter}`}
      {...props}
      pillar="overview"
      title="Overview analisi empirica"
      roleLabel="Quattro pilastri analizzati separatamente — nessuno score aggregato."
      beforeFilters={
        <BalanceEmpiricalAnalysisJobPanel
          dateFrom={props.dateFrom}
          dateTo={props.dateTo}
          competitionId={props.competitionId}
          cohortFilter={props.cohortFilter}
        />
      }
    />
  )
}

export function BalanceF36AnalysisView(props: Props) {
  return (
    <BalancePillarAnalysisShell
      key={`f36-${props.dateFrom}-${props.dateTo}-${props.cohortFilter}`}
      {...props}
      pillar="f36"
      title="Geometria F36"
      roleLabel="Descrive la geometria delle quote laterali"
    />
  )
}

export function BalanceDominanceAnalysisView(props: Props) {
  return (
    <BalancePillarAnalysisShell
      key={`dom-${props.dateFrom}-${props.dateTo}-${props.cohortFilter}`}
      {...props}
      pillar="dominance"
      title="Dominanza"
      roleLabel="Preferenza di scenario — hit rate non equivale a ROI"
    />
  )
}

export function BalanceDrawCredibilityAnalysisView(props: Props) {
  return (
    <BalancePillarAnalysisShell
      key={`draw-${props.dateFrom}-${props.dateTo}-${props.cohortFilter}`}
      {...props}
      pillar="draw-credibility"
      title="Credibilità X"
      roleLabel="Plausibilità empirica del pareggio — metriche ROC diagnostiche"
      extra={
        <p className="text-xs text-slate-500">
          Il laboratorio storico Ricerca Credibilità X resta disponibile come strumento
          legacy; il dataset empirico Balance è la fonte canonica settled.
        </p>
      }
    />
  )
}

export function BalanceGapAnalysisView(props: Props) {
  return (
    <BalancePillarAnalysisShell
      key={`gap-${props.dateFrom}-${props.dateTo}-${props.cohortFilter}`}
      {...props}
      pillar="gap"
      title="Coerenza Gap"
      roleLabel="Coerenza matematica — non un segnale autonomo"
    />
  )
}

export function BalanceStabilityView(props: Props) {
  return (
    <BalancePillarAnalysisShell
      key={`stab-${props.dateFrom}-${props.dateTo}-${props.cohortFilter}`}
      {...props}
      pillar="stability"
      title="Stabilità temporale"
      roleLabel="Drift mensile e confronti per competizione con campione sufficiente"
    />
  )
}

export function BalanceDataHealthView(props: Props) {
  return (
    <BalancePillarAnalysisShell
      key={`health-${props.dateFrom}-${props.dateTo}-${props.cohortFilter}`}
      {...props}
      pillar="data-health"
      title="Data health"
      roleLabel="Missingness, coorti, probabilità e classi sconosciute"
    />
  )
}
