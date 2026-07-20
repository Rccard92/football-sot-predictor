import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import {
  downloadBalanceReadinessDossier,
  getBalanceReadinessDecisionContract,
  getBalanceReadinessGates,
  getBalanceReadinessHistory,
  getBalanceReadinessOverview,
  getBalanceReadinessPillars,
  getBalanceReadinessProspectiveProgress,
  type BalanceProspectiveProgress,
  type BalanceReadinessDecisionContract,
  type BalanceReadinessGatesPayload,
  type BalanceReadinessHistory,
  type BalanceReadinessOverview,
  type BalanceReadinessPillars,
} from '../../../lib/cecchinoModuleMonitoringApi'
import { MonitoringEmptyState } from '../MonitoringEmptyState'
import { BalanceGovernanceDecisionPanel } from './BalanceGovernanceDecisionPanel'
import { BalancePillarDecisionCard } from './BalancePillarDecisionCard'
import { BalanceProspectiveProgressView } from './BalanceProspectiveProgress'
import { BalanceReadinessGateMatrix } from './BalanceReadinessGateMatrix'
import { BalanceReadinessHero } from './BalanceReadinessHero'
import { BalanceReadinessHistoryChart } from './BalanceReadinessHistoryChart'
import { BalanceReadinessTimeline } from './BalanceReadinessTimeline'

type Props = {
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  cohortFilter?: string
}

const PILLAR_ORDER = ['f36', 'dominance', 'draw_credibility', 'gap'] as const

const PILLAR_TITLES: Record<string, string> = {
  f36: 'Geometria F36',
  dominance: 'Dominanza',
  draw_credibility: 'Credibilità X',
  gap: 'Gap',
}

export function BalanceReadinessView({ dateFrom, dateTo, competitionId }: Props) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)

  const [overview, setOverview] = useState<BalanceReadinessOverview | null>(null)
  const [gates, setGates] = useState<BalanceReadinessGatesPayload | null>(null)
  const [pillars, setPillars] = useState<BalanceReadinessPillars | null>(null)
  const [progress, setProgress] = useState<BalanceProspectiveProgress | null>(null)
  const [history, setHistory] = useState<BalanceReadinessHistory | null>(null)
  const [contract, setContract] = useState<BalanceReadinessDecisionContract | null>(null)

  useEffect(() => {
    let mounted = true
    setLoading(true)
    setError(null)

    const filters = {
      date_from: dateFrom,
      date_to: dateTo,
      competition_id: competitionId ?? undefined,
    }

    Promise.all([
      getBalanceReadinessOverview(filters),
      getBalanceReadinessGates(filters),
      getBalanceReadinessPillars(filters),
      getBalanceReadinessProspectiveProgress(filters),
      getBalanceReadinessHistory(filters),
      getBalanceReadinessDecisionContract(),
    ])
      .then(([ov, gt, pl, pr, hs, ct]) => {
        if (!mounted) return
        setOverview(ov)
        setGates(gt)
        setPillars(pl)
        setProgress(pr)
        setHistory(hs)
        setContract(ct)
        setLoading(false)
      })
      .catch((err: Error) => {
        if (!mounted) return
        setError(err?.message || 'Errore nel caricamento della readiness')
        setLoading(false)
      })

    return () => {
      mounted = false
    }
  }, [dateFrom, dateTo, competitionId])

  const handleDownloadDossier = async () => {
    if (downloading) return
    setDownloading(true)
    try {
      await downloadBalanceReadinessDossier({
        date_from: dateFrom,
        date_to: dateTo,
        competition_id: competitionId ?? undefined,
      })
    } catch {
      toast.error('Download dossier readiness non riuscito')
    } finally {
      setDownloading(false)
    }
  }

  if (loading) {
    return (
      <div className="py-8 text-center text-sm text-slate-500">
        Caricamento readiness Balance v5…
      </div>
    )
  }

  if (error) {
    return <MonitoringEmptyState title="Errore caricamento readiness" reason={error} />
  }

  const pillarMap = pillars?.pillars || {}

  return (
    <div className="space-y-6">
      <BalanceReadinessHero overview={overview} />

      <div className="flex justify-end">
        <button
          type="button"
          onClick={handleDownloadDossier}
          disabled={downloading}
          className="rounded-lg border border-violet-200 bg-violet-50 px-4 py-2 text-sm font-medium text-violet-800 hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {downloading ? 'Download in corso…' : 'Scarica dossier readiness'}
        </button>
      </div>

      <BalanceReadinessGateMatrix gates={gates} />

      <div className="grid gap-4 md:grid-cols-2">
        {PILLAR_ORDER.map((key) => {
          const pillar = pillarMap[key]
          if (!pillar) return null
          return (
            <BalancePillarDecisionCard
              key={key}
              title={PILLAR_TITLES[key] || key}
              pillar={pillar}
            />
          )
        })}
      </div>

      <BalanceProspectiveProgressView progress={progress} />

      <BalanceReadinessTimeline items={progress?.timeline || []} />

      <BalanceGovernanceDecisionPanel contract={contract} />

      <BalanceReadinessHistoryChart history={history} />
    </div>
  )
}
