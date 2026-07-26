import { useCallback, useState, type KeyboardEvent } from 'react'
import type {
  CecchinoGiV5CandidateExplanation,
  CecchinoGiV5DimensionExplanation,
  CecchinoGiV5ExplanationsResponse,
  CecchinoTodayDetailResponse,
} from '../../lib/cecchinoTodayApi'
import { getGoalIntensityV5Explanations } from '../../lib/cecchinoTodayApi'
import { CecchinoGoalIntensityV5AuditModal } from './CecchinoGoalIntensityV5AuditModal'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

type GoalIntensityPayload = NonNullable<CecchinoTodayDetailResponse['goal_intensity_v5']>

type Props = {
  goalIntensity?: GoalIntensityPayload | null
  todayFixtureId?: number | null
  providerFixtureId?: number | null
}

type SelectedAudit =
  | { type: 'dimension'; explanation: CecchinoGiV5DimensionExplanation }
  | { type: 'candidate'; explanation: CecchinoGiV5CandidateExplanation }

type DimensionKey =
  | 'offensive_production'
  | 'defensive_solidity'
  | 'match_tempo'
  | 'offensive_stability'

const CANDIDATES = [
  { id: 'GI_A_STRICT_CORE', role: 'Primary', scoreKey: 'primary_candidate_score' },
  { id: 'GI_B_RECENCY', role: 'Challenger', scoreKey: 'challenger_candidate_score' },
  { id: 'MT1_LONG_TERM', role: 'Benchmark', scoreKey: 'benchmark_score' },
  {
    id: 'GI_A_without_volatility',
    role: 'Diagnostico',
    scoreKey: 'diagnostic_score',
  },
] as const

function fmt(v: number | null | undefined, digits = 1): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return Number(v).toFixed(digits)
}

function fmtProb(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return `${(Number(v) * 100).toFixed(1)}%`
}

function downloadAuditJson(
  payload: CecchinoGiV5ExplanationsResponse,
  providerFixtureId: number | null | undefined,
) {
  const id = providerFixtureId ?? payload.fixture?.provider_fixture_id ?? 'unknown'
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `cecchino-goal-intensity-v5-audit-${id}.json`
  a.click()
  URL.revokeObjectURL(url)
}

function DimensionBlock({
  title,
  rows,
  analysisActive,
  onOpenAnalysis,
}: {
  title: string
  rows: Array<[string, number | null | undefined]>
  analysisActive: boolean
  onOpenAnalysis?: () => void
}) {
  const interactiveClass = analysisActive
    ? 'cursor-pointer transition-shadow hover:shadow-md hover:ring-1 hover:ring-violet-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400'
    : ''

  const openAnalysis = () => {
    if (analysisActive && onOpenAnalysis) onOpenAnalysis()
  }

  const onKeyDown = (e: KeyboardEvent) => {
    if (!analysisActive) return
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      openAnalysis()
    }
  }

  return (
    <div
      className={`rounded-lg border border-slate-150 bg-slate-50/60 px-3 py-2 ${interactiveClass}`}
      role={analysisActive ? 'button' : undefined}
      tabIndex={analysisActive ? 0 : undefined}
      aria-label={analysisActive ? `Apri analisi ${title.replace(/^\d+\.\s*/, '')}` : undefined}
      onClick={analysisActive ? openAnalysis : undefined}
      onKeyDown={analysisActive ? onKeyDown : undefined}
    >
      <p className="text-xs font-semibold text-slate-800">{title}</p>
      <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
        {rows.map(([label, value]) => (
          <li key={label} className="flex justify-between gap-2">
            <span>{label}</span>
            <span className="font-medium text-slate-900">{fmt(value)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function UnavailablePanel({
  title,
  subtitle,
  showBadges,
}: {
  title: string
  subtitle: string
  showBadges?: boolean
}) {
  return (
    <section className={`${todayCard} ${todayCardPadding}`}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className={todaySectionTitle}>{title}</h3>
          <p className={todaySectionSubtitle}>{subtitle}</p>
        </div>
        <span className="self-start rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-400">
          Audit non disponibile
        </span>
      </div>
      {showBadges ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <span className="inline-block rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-medium text-violet-900">
            Preview monitorata
          </span>
          <span className="inline-block rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-600">
            Non collegato ai Segnali
          </span>
        </div>
      ) : null}
    </section>
  )
}

export function CecchinoGoalIntensityV5Panel({
  goalIntensity,
  todayFixtureId,
  providerFixtureId,
}: Props) {
  const [analysisMode, setAnalysisMode] = useState(false)
  const [explanations, setExplanations] = useState<CecchinoGiV5ExplanationsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<SelectedAudit | null>(null)
  const [analysisFixtureId, setAnalysisFixtureId] = useState(todayFixtureId)

  if (analysisFixtureId !== todayFixtureId) {
    setAnalysisFixtureId(todayFixtureId)
    setAnalysisMode(false)
    setExplanations(null)
    setError(null)
    setLoading(false)
    setSelected(null)
  }

  const loadExplanations = useCallback(async (): Promise<CecchinoGiV5ExplanationsResponse | null> => {
    if (explanations) return explanations
    if (todayFixtureId == null) return null
    setLoading(true)
    setError(null)
    try {
      const res = await getGoalIntensityV5Explanations(todayFixtureId)
      if (res.status === 'error') {
        setError(res.message || res.code || 'Errore caricamento audit Goal Intensity')
        return null
      }
      setExplanations(res)
      return res
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore caricamento audit Goal Intensity')
      return null
    } finally {
      setLoading(false)
    }
  }, [explanations, todayFixtureId])

  const toggleAnalysis = async () => {
    if (analysisMode) {
      setAnalysisMode(false)
      setSelected(null)
      return
    }
    const res = await loadExplanations()
    if (res) setAnalysisMode(true)
  }

  const handleDownload = async () => {
    const res = await loadExplanations()
    if (res) downloadAuditJson(res, providerFixtureId)
  }

  const openDimension = (key: DimensionKey) => {
    const expl = explanations?.dimensions?.[key]
    if (expl) setSelected({ type: 'dimension', explanation: expl })
  }

  const openCandidate = (id: string) => {
    const expl = explanations?.candidates?.[id]
    if (expl) setSelected({ type: 'candidate', explanation: expl })
  }

  if (!goalIntensity || goalIntensity.status === 'unavailable') {
    return (
      <UnavailablePanel
        title="Intensità Goal Avanzata v5"
        subtitle="Snapshot prospettico non disponibile (bundle assente o partita fuori coorte)."
        showBadges
      />
    )
  }

  if (goalIntensity.status === 'error' && !goalIntensity.snapshot) {
    return (
      <UnavailablePanel
        title="Intensità Goal Avanzata v5"
        subtitle={goalIntensity.banner ?? 'Snapshot non disponibile.'}
      />
    )
  }

  const snap = (goalIntensity.snapshot || {}) as Record<string, unknown>
  const pillars = (snap.pillar_scores || {}) as Record<string, number | null>
  const calibrated = (snap.calibrated_predictions || {}) as Record<
    string,
    Record<string, number | null | string | boolean>
  >

  const dimensionDefs: Array<{
    key: DimensionKey
    title: string
    rows: Array<[string, number | null | undefined]>
  }> = [
    {
      key: 'offensive_production',
      title: '1. Produzione offensiva',
      rows: [
        ['OP1 long-term', pillars.OP1_HOME_LONG_TERM],
        ['OP2 recency', pillars.OP2_HOME_RECENCY],
      ],
    },
    {
      key: 'defensive_solidity',
      title: '2. Solidità difensiva',
      rows: [
        ['Vulnerabilità DV1', pillars.DV1_MEAN_CONCEDED],
        ['Solidità (100 − vuln.)', pillars.defensive_solidity_display],
      ],
    },
    {
      key: 'match_tempo',
      title: '3. Ritmo partita',
      rows: [
        ['MT1 long-term', pillars.MT1_LONG_TERM],
        ['MT2 + recency', pillars.MT2_LONG_TERM_PLUS_RECENCY],
      ],
    },
    {
      key: 'offensive_stability',
      title: '4. Stabilità offensiva',
      rows: [
        ['Volatilità OV1', pillars.OV1_STD],
        ['Stabilità (100 − vol.)', pillars.offensive_stability_display],
      ],
    },
  ]

  return (
    <section className={`${todayCard} ${todayCardPadding}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className={todaySectionTitle}>Intensità Goal Avanzata v5</h3>
          <p className={todaySectionSubtitle}>
            Analisi su quattro dimensioni distinte con candidati calibrati.
          </p>
          {error ? <p className="mt-2 text-xs text-amber-700">{error}</p> : null}
          {analysisMode ? (
            <p className="mt-2 text-xs text-slate-500">
              Modalità analisi: clicca una dimensione o un candidato
            </p>
          ) : null}
        </div>
        {todayFixtureId != null ? (
          <div className="flex flex-wrap items-center gap-2 sm:justify-end">
            <button
              type="button"
              onClick={() => void toggleAnalysis()}
              disabled={loading}
              className={`rounded-md border px-2.5 py-1 text-[11px] font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/60 disabled:opacity-60 ${
                analysisMode
                  ? 'border-amber-300 bg-amber-50 text-amber-900'
                  : 'border-slate-300 bg-slate-50 text-slate-700 hover:bg-slate-100'
              }`}
            >
              {loading ? 'Caricamento…' : analysisMode ? 'Analisi attiva' : 'ƒx Analisi intensità'}
            </button>
            <button
              type="button"
              onClick={() => void handleDownload()}
              disabled={loading}
              className="rounded-md border border-slate-300 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/60 disabled:opacity-60"
            >
              Scarica audit Goal Intensity
            </button>
          </div>
        ) : null}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <span className="inline-block rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-medium text-violet-900">
          Preview monitorata
        </span>
        <span className="inline-block rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-600">
          Non collegato ai Segnali
        </span>
      </div>
      {goalIntensity.banner && (
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-950">
          {goalIntensity.banner}
        </p>
      )}

      <details
        className="mt-3 rounded-lg border border-slate-200 bg-white"
        onClick={(e) => e.stopPropagation()}
      >
        <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50">
          Qualità snapshot
        </summary>
        <div className="border-t border-slate-200 px-3 py-2 text-xs text-slate-700">
          <p>
            Bundle frozen at:{' '}
            <span className="font-medium">
              {String(
                snap.bundle_frozen_at ??
                  (goalIntensity.bundle as Record<string, unknown> | undefined)?.bundle_frozen_at ??
                  '—',
              )}
            </span>
          </p>
          <p className="mt-1">
            Source snapshot at:{' '}
            <span className="font-medium">{String(snap.source_snapshot_at ?? '—')}</span>
          </p>
          <p className="mt-1">
            source_snapshot_at &gt; bundle_frozen_at:{' '}
            <span className="font-medium">
              {(() => {
                const check = snap.freeze_check as Record<string, boolean> | undefined
                const v = check?.source_snapshot_at_gt_bundle_frozen_at ?? snap.source_snapshot_after_freeze
                return v == null ? '—' : v ? 'sì' : 'no'
              })()}
            </span>
          </p>
          <p className="mt-1">
            source_snapshot_at &lt; kickoff:{' '}
            <span className="font-medium">
              {(() => {
                const check = snap.freeze_check as Record<string, boolean> | undefined
                const v = check?.source_snapshot_at_lt_kickoff ?? snap.source_snapshot_before_kickoff
                return v == null ? '—' : v ? 'sì' : 'no'
              })()}
            </span>
          </p>
        </div>
      </details>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {dimensionDefs.map((d) => (
          <DimensionBlock
            key={d.key}
            title={d.title}
            rows={d.rows}
            analysisActive={analysisMode}
            onOpenAnalysis={() => openDimension(d.key)}
          />
        ))}
      </div>

      <div className="mt-5 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="border-b border-slate-200 text-slate-500">
            <tr>
              <th className="py-2 pr-3 font-medium">Candidato</th>
              <th className="py-2 pr-3 font-medium">Ruolo</th>
              <th className="py-2 pr-3 font-medium">Score</th>
              <th className="py-2 pr-3 font-medium">xG totali</th>
              <th className="py-2 pr-3 font-medium">P(≥2)</th>
              <th className="py-2 pr-3 font-medium">P(≥3)</th>
              <th className="py-2 font-medium">P(BTTS)</th>
            </tr>
          </thead>
          <tbody>
            {CANDIDATES.map((c) => {
              const cal = calibrated[c.id] || {}
              const score =
                (snap[c.scoreKey] as number | null | undefined) ??
                ((snap.candidate_scores as Record<string, number> | undefined)?.[c.id] ?? null)
              const isPrimary = c.role === 'Primary'
              const rowInteractive = analysisMode
                ? 'cursor-pointer transition-shadow hover:shadow-sm hover:ring-1 hover:ring-violet-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400'
                : ''

              const openRow = () => openCandidate(c.id)
              const onKeyDown = (e: KeyboardEvent) => {
                if (!analysisMode) return
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  openRow()
                }
              }

              return (
                <tr
                  key={c.id}
                  className={`border-b border-slate-100 ${isPrimary ? 'bg-violet-50 font-medium text-slate-900' : 'text-slate-800'} ${rowInteractive}`}
                  role={analysisMode ? 'button' : undefined}
                  tabIndex={analysisMode ? 0 : undefined}
                  aria-label={analysisMode ? `Apri analisi candidato ${c.id}` : undefined}
                  onClick={analysisMode ? openRow : undefined}
                  onKeyDown={analysisMode ? onKeyDown : undefined}
                >
                  <td className="py-2 pr-3 font-medium">{c.id}</td>
                  <td className="py-2 pr-3">{c.role}</td>
                  <td className="py-2 pr-3">{fmt(score)}</td>
                  <td className="py-2 pr-3">{fmt(cal.expected_total_goals as number | null, 2)}</td>
                  <td className="py-2 pr-3">{fmtProb(cal.probability_goals_ge_2 as number | null)}</td>
                  <td className="py-2 pr-3">{fmtProb(cal.probability_goals_ge_3 as number | null)}</td>
                  <td className="py-2">{fmtProb(cal.probability_btts as number | null)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="mt-2 text-[11px] text-slate-500">
          Stima calibrata research. Candidato Primary evidenziato. Non collegato ai segnali produttivi.
        </p>
      </div>

      {selected ? (
        <CecchinoGoalIntensityV5AuditModal
          type={selected.type}
          explanation={selected.explanation}
          sourceMode={explanations?.source_mode}
          onClose={() => setSelected(null)}
        />
      ) : null}
    </section>
  )
}
