import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  downloadPatternLabDiscoveryExport,
  fetchPatternLabBetBuilderReplay,
  fetchPatternLabFilterOptions,
  fetchPatternLabPresets,
  formatNum,
  formatPct,
  listPatternLabRuns,
  queryPatternLab,
  type PatternLabBetBuilderReplayResponse,
  type PatternLabFilterOptions,
  type PatternLabFilters,
  type PatternLabPreset,
  type PatternLabQueryResponse,
  type PatternLabRunItem,
} from '../../lib/patternLabApi'
import { PatternLabKpiRibbon } from './pattern-lab/PatternLabKpiRibbon'
import { PatternLabModuleInsights } from './pattern-lab/PatternLabModuleInsights'
import { PatternLabPresets } from './pattern-lab/PatternLabPresets'
import { PatternLabStabilityCharts } from './pattern-lab/PatternLabStabilityCharts'

type DetailTab = 'explore' | 'bet_builder'

const RATING_BANDS: Array<{ id: string; label: string; min?: number; max?: number }> = [
  { id: '', label: 'Tutti' },
  { id: '50-59', label: '50–59', min: 50, max: 59 },
  { id: '60-69', label: '60–69', min: 60, max: 69 },
  { id: '70-79', label: '70–79', min: 70, max: 79 },
  { id: '80-89', label: '80–89', min: 80, max: 89 },
  { id: '90-99', label: '90–99', min: 90, max: 99 },
  { id: '100', label: '100', min: 100, max: 100 },
]

const V36_PRESETS = [0, 20, 40, 50, 60, 70, 80, 90]

const EMPTY_OPTIONS: PatternLabFilterOptions = {
  competitions: [],
  markets: [],
  balance_classes: [],
  goal_final_classes: [],
  purchasability_v36_classes: [],
  purchasability_v36_statuses: [],
  purchasability_v36_gates: [],
  consensus_statuses: [],
  balance_pillars: [],
  goal_pillars: [],
  signal_columns: ['D', 'E', 'F', 'G'],
}

function parseRunIds(raw: string | null): number[] {
  if (!raw) return []
  return raw
    .split(',')
    .map((x) => Number(x.trim()))
    .filter((n) => Number.isFinite(n) && n > 0)
}

function Field({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
      {label}
      {children}
    </label>
  )
}

/** Normalizza filtri per confronto preset (ordine chiavi stabile). */
function normalizeFiltersForCompare(f: PatternLabFilters): string {
  const scrub = (obj: unknown): unknown => {
    if (obj == null) return undefined
    if (Array.isArray(obj)) return obj.map(scrub)
    if (typeof obj === 'object') {
      const out: Record<string, unknown> = {}
      for (const k of Object.keys(obj as Record<string, unknown>).sort()) {
        const v = scrub((obj as Record<string, unknown>)[k])
        if (v !== undefined && v !== null && v !== '') out[k] = v
      }
      return out
    }
    return obj
  }
  return JSON.stringify(scrub(f))
}

export function PatternLabTab() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [runs, setRuns] = useState<PatternLabRunItem[]>([])
  const [includeLegacy, setIncludeLegacy] = useState(false)
  const [selectedRunIds, setSelectedRunIds] = useState<number[]>(() =>
    parseRunIds(searchParams.get('run_ids')),
  )
  const [options, setOptions] = useState<PatternLabFilterOptions>(EMPTY_OPTIONS)
  const [detailTab, setDetailTab] = useState<DetailTab>('explore')
  const [loading, setLoading] = useState(false)
  const [exportBusy, setExportBusy] = useState(false)
  const [result, setResult] = useState<PatternLabQueryResponse | null>(null)
  const [bbResult, setBbResult] = useState<PatternLabBetBuilderReplayResponse | null>(null)

  const [competition, setCompetition] = useState('')
  const [marketKey, setMarketKey] = useState('')
  const [ratingBand, setRatingBand] = useState('')
  const [purchMin, setPurchMin] = useState('')
  const [purchCustom, setPurchCustom] = useState('')

  const [quoteMin, setQuoteMin] = useState('')
  const [quoteMax, setQuoteMax] = useState('')
  const [edgeMin, setEdgeMin] = useState('')
  const [edgeMax, setEdgeMax] = useState('')
  const [valueFilter, setValueFilter] = useState('')
  const [scoreAcqMin, setScoreAcqMin] = useState('')
  const [scoreAcqMax, setScoreAcqMax] = useState('')
  const [vantMin, setVantMin] = useState('')
  const [vantMax, setVantMax] = useState('')
  const [signalsMin, setSignalsMin] = useState('')
  const [signalsMax, setSignalsMax] = useState('')
  const [signalActive, setSignalActive] = useState('')
  const [signalCols, setSignalCols] = useState<Record<string, string>>({})
  const [consensusStatus, setConsensusStatus] = useState('')
  const [geometryMin, setGeometryMin] = useState('')
  const [geometryMax, setGeometryMax] = useState('')
  const [balanceClass, setBalanceClass] = useState('')
  const [goalMin, setGoalMin] = useState('')
  const [goalMax, setGoalMax] = useState('')
  const [goalClass, setGoalClass] = useState('')
  const [goalPillarFilters, setGoalPillarFilters] = useState<
    Record<string, { min?: number; max?: number; class?: string }>
  >({})
  const [purchMax, setPurchMax] = useState('')
  const [purchMaxExclusive, setPurchMaxExclusive] = useState(false)
  const [purchClass, setPurchClass] = useState('')
  const [purchStatus, setPurchStatus] = useState('')
  const [purchGate, setPurchGate] = useState('')
  const [bbActive, setBbActive] = useState('')
  const [bbRankMin, setBbRankMin] = useState('')
  const [bbRankMax, setBbRankMax] = useState('')
  const [outcome, setOutcome] = useState('')
  const [quoteType, setQuoteType] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  /** Toggle tecnico: ON = mostra anche mercati senza evidenza (market_informative=false). */
  const [showWithoutEvidence, setShowWithoutEvidence] = useState(false)

  const [presets, setPresets] = useState<PatternLabPreset[]>([])
  const [activePresetId, setActivePresetId] = useState<string | null>(null)
  const [presetBaseline, setPresetBaseline] = useState<string | null>(null)

  const effectivePurchMin = purchCustom !== '' ? purchCustom : purchMin

  const filters: PatternLabFilters = useMemo(() => {
    const f: PatternLabFilters = {
      eligibility: 'eligible_core',
      market_informative: !showWithoutEvidence,
    }
    if (competition) f.competitions = [competition]
    if (marketKey) f.market_keys = [marketKey]
    const band = RATING_BANDS.find((b) => b.id === ratingBand)
    if (band?.min != null) f.rating_min = band.min
    if (band?.max != null) f.rating_max = band.max
    if (effectivePurchMin !== '') f.purchasability_v36_min = Number(effectivePurchMin)
    if (quoteMin !== '') f.quote_min = Number(quoteMin)
    if (quoteMax !== '') f.quote_max = Number(quoteMax)
    if (edgeMin !== '') f.edge_min = Number(edgeMin)
    if (edgeMax !== '') f.edge_max = Number(edgeMax)
    if (valueFilter === 'yes') f.value = true
    if (valueFilter === 'no') f.value = false
    if (scoreAcqMin !== '') f.score_acquisto_min = Number(scoreAcqMin)
    if (scoreAcqMax !== '') f.score_acquisto_max = Number(scoreAcqMax)
    if (vantMin !== '') f.vantaggio_prob_min = Number(vantMin)
    if (vantMax !== '') f.vantaggio_prob_max = Number(vantMax)
    if (signalsMin !== '') f.signals_count_min = Number(signalsMin)
    if (signalsMax !== '') f.signals_count_max = Number(signalsMax)
    if (signalActive === 'yes') f.signal_active = true
    if (signalActive === 'no') f.signal_active = false
    if (Object.keys(signalCols).length) f.signal_columns = signalCols
    if (consensusStatus) f.consensus_status = consensusStatus
    if (geometryMin !== '') f.gap_coherence_score_min = Number(geometryMin)
    if (geometryMax !== '') f.gap_coherence_score_max = Number(geometryMax)
    if (balanceClass) f.balance_class = balanceClass
    if (goalMin !== '') f.goal_composite_min = Number(goalMin)
    if (goalMax !== '') f.goal_composite_max = Number(goalMax)
    if (goalClass) f.goal_final_class = goalClass
    if (Object.keys(goalPillarFilters).length) f.goal_pillar_filters = goalPillarFilters
    if (purchMax !== '') f.purchasability_v36_max = Number(purchMax)
    if (purchMaxExclusive) f.purchasability_v36_max_exclusive = true
    if (purchClass) f.purchasability_v36_class = purchClass
    if (purchStatus) f.purchasability_v36_status = purchStatus
    if (purchGate) f.purchasability_v36_gate_status = purchGate
    if (bbActive === 'yes') f.bet_builder_active = true
    if (bbActive === 'no') f.bet_builder_active = false
    if (bbRankMin !== '') f.bet_builder_rank_min = Number(bbRankMin)
    if (bbRankMax !== '') f.bet_builder_rank_max = Number(bbRankMax)
    if (outcome) f.outcome = outcome
    if (quoteType) f.quote_type = quoteType
    if (dateFrom) f.date_from = dateFrom
    if (dateTo) f.date_to = dateTo
    return f
  }, [
    competition,
    marketKey,
    ratingBand,
    effectivePurchMin,
    quoteMin,
    quoteMax,
    edgeMin,
    edgeMax,
    valueFilter,
    scoreAcqMin,
    scoreAcqMax,
    vantMin,
    vantMax,
    signalsMin,
    signalsMax,
    signalActive,
    signalCols,
    consensusStatus,
    geometryMin,
    geometryMax,
    balanceClass,
    goalMin,
    goalMax,
    goalClass,
    goalPillarFilters,
    purchMax,
    purchMaxExclusive,
    purchClass,
    purchStatus,
    purchGate,
    bbActive,
    bbRankMin,
    bbRankMax,
    outcome,
    quoteType,
    dateFrom,
    dateTo,
    showWithoutEvidence,
  ])

  const presetModified = Boolean(
    activePresetId && presetBaseline && normalizeFiltersForCompare(filters) !== presetBaseline,
  )

  const patternRecap = useMemo(() => {
    const parts: string[] = []
    if (!showWithoutEvidence) parts.push('Solo mercati con evidenza')
    else parts.push('Tutti i mercati storici')
    if (marketKey) {
      const lab = options.markets.find((m) => m.key === marketKey)?.label || marketKey
      parts.push(lab)
    }
    if (ratingBand) parts.push(`Rating ${ratingBand}`)
    if (effectivePurchMin !== '') parts.push(`V3.6 ≥${effectivePurchMin}`)
    if (signalsMin !== '') parts.push(`Signals ≥${signalsMin}`)
    if (competition) parts.push(competition)
    if (valueFilter === 'yes') parts.push('Value sì')
    if (geometryMin !== '') parts.push(`Geometry ≥${geometryMin}`)
    if (goalClass) parts.push(`Goal ${goalClass}`)
    if (bbActive === 'yes') parts.push('Bet Builder')
    return parts.join(' · ')
  }, [
    showWithoutEvidence,
    marketKey,
    options.markets,
    ratingBand,
    effectivePurchMin,
    signalsMin,
    competition,
    valueFilter,
    geometryMin,
    goalClass,
    bbActive,
  ])

  const loadRuns = useCallback(async () => {
    try {
      const res = await listPatternLabRuns({ include_legacy: includeLegacy })
      setRuns(res.items)
      if (!includeLegacy) {
        setSelectedRunIds((prev) => {
          const allowed = new Set(res.items.filter((r) => r.is_canonical).map((r) => r.run_id))
          const next = prev.filter((id) => allowed.has(id))
          return next.length === prev.length ? prev : next
        })
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Errore caricamento run')
    }
  }, [includeLegacy])

  useEffect(() => {
    void loadRuns()
  }, [loadRuns])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await fetchPatternLabPresets()
        if (!cancelled) setPresets(res.presets || [])
      } catch {
        if (!cancelled) setPresets([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const fromUrl = parseRunIds(searchParams.get('run_ids'))
    if (fromUrl.length && fromUrl.join(',') !== selectedRunIds.join(',')) {
      setSelectedRunIds(fromUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  useEffect(() => {
    if (!selectedRunIds.length) {
      setOptions(EMPTY_OPTIONS)
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const opts = await fetchPatternLabFilterOptions(selectedRunIds)
        if (!cancelled) setOptions(opts)
      } catch {
        if (!cancelled) setOptions(EMPTY_OPTIONS)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedRunIds])

  const syncUrl = (ids: number[]) => {
    const next = new URLSearchParams(searchParams)
    next.set('tab', 'pattern_lab')
    if (ids.length) next.set('run_ids', ids.join(','))
    else next.delete('run_ids')
    setSearchParams(next, { replace: true })
  }

  const toggleRun = (runId: number) => {
    setSelectedRunIds((prev) => {
      const next = prev.includes(runId) ? prev.filter((x) => x !== runId) : [...prev, runId]
      syncUrl(next)
      return next
    })
  }

  const selectAllCanonical = () => {
    const ids = runs.filter((r) => r.is_canonical).map((r) => r.run_id)
    setSelectedRunIds(ids)
    syncUrl(ids)
  }

  const resetFilters = () => {
    setCompetition('')
    setMarketKey('')
    setRatingBand('')
    setPurchMin('')
    setPurchCustom('')
    setQuoteMin('')
    setQuoteMax('')
    setEdgeMin('')
    setEdgeMax('')
    setValueFilter('')
    setScoreAcqMin('')
    setScoreAcqMax('')
    setVantMin('')
    setVantMax('')
    setSignalsMin('')
    setSignalsMax('')
    setSignalActive('')
    setSignalCols({})
    setConsensusStatus('')
    setGeometryMin('')
    setGeometryMax('')
    setBalanceClass('')
    setGoalMin('')
    setGoalMax('')
    setGoalClass('')
    setGoalPillarFilters({})
    setPurchMax('')
    setPurchMaxExclusive(false)
    setPurchClass('')
    setPurchStatus('')
    setPurchGate('')
    setBbActive('')
    setBbRankMin('')
    setBbRankMax('')
    setOutcome('')
    setQuoteType('')
    setDateFrom('')
    setDateTo('')
    setShowWithoutEvidence(false)
  }

  const clearPreset = () => {
    resetFilters()
    setActivePresetId(null)
    setPresetBaseline(null)
  }

  const applyPresetFiltersToState = (pf: PatternLabFilters) => {
    resetFilters()
    if (pf.competitions?.[0]) setCompetition(pf.competitions[0])
    if (pf.market_keys?.[0]) setMarketKey(pf.market_keys[0])
    if (pf.rating_min != null && pf.rating_max != null) {
      const band = RATING_BANDS.find((b) => b.min === pf.rating_min && b.max === pf.rating_max)
      if (band) setRatingBand(band.id)
    }
    if (pf.purchasability_v36_min != null) {
      const v = String(pf.purchasability_v36_min)
      if (V36_PRESETS.map(String).includes(v)) {
        setPurchMin(v)
        setPurchCustom('')
      } else {
        setPurchCustom(v)
        setPurchMin('')
      }
    }
    if (pf.purchasability_v36_max != null) setPurchMax(String(pf.purchasability_v36_max))
    if (pf.purchasability_v36_max_exclusive) setPurchMaxExclusive(true)
    if (pf.purchasability_v36_class) setPurchClass(String(pf.purchasability_v36_class))
    if (pf.purchasability_v36_status) setPurchStatus(String(pf.purchasability_v36_status))
    if (pf.purchasability_v36_gate_status) setPurchGate(String(pf.purchasability_v36_gate_status))
    if (pf.signal_active === true) setSignalActive('yes')
    if (pf.signal_active === false) setSignalActive('no')
    if (pf.goal_final_class) setGoalClass(String(pf.goal_final_class))
    if (pf.goal_pillar_filters) setGoalPillarFilters({ ...pf.goal_pillar_filters })
    if (pf.market_informative === false) setShowWithoutEvidence(true)
    if (pf.quote_min != null) setQuoteMin(String(pf.quote_min))
    if (pf.quote_max != null) setQuoteMax(String(pf.quote_max))
    if (pf.balance_class) setBalanceClass(String(pf.balance_class))
  }

  const runQuery = async (filtersOverride?: PatternLabFilters) => {
    if (!selectedRunIds.length) {
      toast.error('Seleziona almeno una run')
      return
    }
    const effective = filtersOverride ?? filters
    setLoading(true)
    try {
      const [queryRes, bbRes] = await Promise.all([
        queryPatternLab({
          run_ids: selectedRunIds,
          filters: effective,
          include_rows: true,
          page: 1,
          page_size: 80,
        }),
        fetchPatternLabBetBuilderReplay({
          run_ids: selectedRunIds,
          filters: effective,
        }),
      ])
      setResult(queryRes)
      setBbResult(bbRes)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Errore query Pattern Lab')
    } finally {
      setLoading(false)
    }
  }

  const applyPreset = (preset: PatternLabPreset) => {
    const pf = preset.filters || {}
    applyPresetFiltersToState(pf)
    const baseline = normalizeFiltersForCompare(pf)
    setActivePresetId(preset.id)
    setPresetBaseline(baseline)
    void runQuery(pf)
  }

  const onExport = async (mode: 'full_selected_runs' | 'current_filters') => {
    if (!selectedRunIds.length) {
      toast.error('Seleziona almeno una run')
      return
    }
    setExportBusy(true)
    try {
      const blob = await downloadPatternLabDiscoveryExport({
        run_ids: selectedRunIds,
        mode,
        filters: mode === 'current_filters' ? filters : { eligibility: 'eligible_core' },
        include_observational_only: true,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `pattern_lab_discovery_${selectedRunIds.join('-')}.zip`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Export Pattern Discovery avviato')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Export fallito')
    } finally {
      setExportBusy(false)
    }
  }

  const summary = result?.summary
  const insights = result?.module_insights
  const breakdown = result?.breakdown

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Pattern Lab</h2>
          <p className="mt-1 max-w-2xl text-sm" style={{ color: 'var(--lab-muted)' }}>
            Analisi multi-run MATCH+MARKET su snapshot V4 canonici. Goal Intensity V4-compat.
            Acquistabilità solo V3.6.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="lab-btn rounded-md px-3 py-2 text-sm"
            disabled={exportBusy}
            onClick={() => void onExport('full_selected_runs')}
          >
            Esporta dataset Pattern Discovery
          </button>
          <button
            type="button"
            className="lab-btn-ghost rounded-md border px-3 py-2 text-sm"
            style={{ borderColor: 'var(--lab-border)' }}
            disabled={exportBusy}
            onClick={() => void onExport('current_filters')}
          >
            Export filtri correnti
          </button>
        </div>
      </div>

      <section className="lab-card rounded-xl p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold">Run / Stagioni</h3>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <button type="button" className="underline" style={{ color: 'var(--lab-cyan)' }} onClick={selectAllCanonical}>
              Seleziona tutte
            </button>
          </div>
        </div>
        <div className="mt-3 grid max-h-48 gap-2 overflow-auto sm:grid-cols-2 lg:grid-cols-3">
          {runs.map((r) => (
            <label
              key={r.run_id}
              className="flex cursor-pointer items-start gap-2 rounded-md border p-2 text-sm"
              style={{ borderColor: 'var(--lab-border)' }}
            >
              <input
                type="checkbox"
                checked={selectedRunIds.includes(r.run_id)}
                onChange={() => toggleRun(r.run_id)}
              />
              <span>
                <span className="font-medium">#{r.run_id}</span> · {r.season_label}
                <span className="mt-0.5 block text-[11px]" style={{ color: 'var(--lab-muted)' }}>
                  {r.is_canonical ? 'canonica' : 'legacy'} · {r.run_scope} ·{' '}
                  {r.quote_policy_version || '—'} · eleggibili {r.matches_eligible_core ?? '—'}
                </span>
              </span>
            </label>
          ))}
          {!runs.length && (
            <div className="text-sm" style={{ color: 'var(--lab-muted)' }}>
              Nessuna run canonica disponibile.
            </div>
          )}
        </div>
        <details className="mt-3">
          <summary className="cursor-pointer text-sm" style={{ color: 'var(--lab-muted)' }}>
            Opzioni tecniche
          </summary>
          <label className="mt-2 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={includeLegacy}
              onChange={(e) => setIncludeLegacy(e.target.checked)}
            />
            Mostra pilot / legacy
          </label>
        </details>
      </section>

      <PatternLabPresets
        presets={presets}
        activePresetId={activePresetId}
        presetModified={presetModified}
        disabled={loading}
        onApply={applyPreset}
        onClear={clearPreset}
      />

      <section className="lab-card rounded-xl p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold">Filtri principali</h3>
          <label
            className="flex cursor-pointer items-center gap-2 text-xs"
            style={{ color: 'var(--lab-muted)' }}
            title="Di default solo mercati con evidenza KPI (rating≥30 + value+), Signals o V3.6"
          >
            <input
              type="checkbox"
              checked={showWithoutEvidence}
              onChange={(e) => setShowWithoutEvidence(e.target.checked)}
            />
            Mostra mercati senza evidenza
          </label>
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Campionato">
            <select
              className="lab-input"
              value={competition}
              onChange={(e) => setCompetition(e.target.value)}
            >
              <option value="">Tutti i campionati</option>
              {options.competitions.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Mercato">
            <select
              className="lab-input"
              value={marketKey}
              onChange={(e) => setMarketKey(e.target.value)}
            >
              <option value="">Tutti i mercati</option>
              {options.markets.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Rating">
            <select
              className="lab-input"
              value={ratingBand}
              onChange={(e) => setRatingBand(e.target.value)}
            >
              {RATING_BANDS.map((b) => (
                <option key={b.id || 'all'} value={b.id}>
                  {b.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Acquistabilità V3.6 minima">
            <div className="flex flex-wrap gap-1">
              {V36_PRESETS.map((v) => (
                <button
                  key={v}
                  type="button"
                  className={`rounded border px-2 py-1 text-xs ${purchMin === String(v) && purchCustom === '' ? 'lab-tab-active' : ''}`}
                  style={{ borderColor: 'var(--lab-border)' }}
                  onClick={() => {
                    setPurchMin(String(v))
                    setPurchCustom('')
                  }}
                >
                  {v}
                </button>
              ))}
              <input
                className="lab-input w-20"
                placeholder="custom"
                value={purchCustom}
                onChange={(e) => setPurchCustom(e.target.value)}
              />
            </div>
          </Field>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            className="lab-btn rounded-md px-4 py-2 text-sm"
            disabled={loading}
            onClick={() => void runQuery()}
          >
            {loading ? 'Analisi…' : 'Analizza'}
          </button>
          <button
            type="button"
            className="lab-btn-ghost rounded-md border px-4 py-2 text-sm"
            style={{ borderColor: 'var(--lab-border)' }}
            onClick={clearPreset}
          >
            Reset filtri
          </button>
        </div>

        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-medium">Filtri avanzati</summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Quota PRE min">
              <input className="lab-input" value={quoteMin} onChange={(e) => setQuoteMin(e.target.value)} />
            </Field>
            <Field label="Quota PRE max">
              <input className="lab-input" value={quoteMax} onChange={(e) => setQuoteMax(e.target.value)} />
            </Field>
            <Field label="Edge min">
              <input className="lab-input" value={edgeMin} onChange={(e) => setEdgeMin(e.target.value)} />
            </Field>
            <Field label="Edge max">
              <input className="lab-input" value={edgeMax} onChange={(e) => setEdgeMax(e.target.value)} />
            </Field>
            <Field label="Value">
              <select className="lab-input" value={valueFilter} onChange={(e) => setValueFilter(e.target.value)}>
                <option value="">Tutti</option>
                <option value="yes">Sì</option>
                <option value="no">No</option>
              </select>
            </Field>
            <Field label="Score acquisto min">
              <input className="lab-input" value={scoreAcqMin} onChange={(e) => setScoreAcqMin(e.target.value)} />
            </Field>
            <Field label="Score acquisto max">
              <input className="lab-input" value={scoreAcqMax} onChange={(e) => setScoreAcqMax(e.target.value)} />
            </Field>
            <Field label="Vantaggio prob. min">
              <input className="lab-input" value={vantMin} onChange={(e) => setVantMin(e.target.value)} />
            </Field>
            <Field label="Vantaggio prob. max">
              <input className="lab-input" value={vantMax} onChange={(e) => setVantMax(e.target.value)} />
            </Field>
            <Field label="Signals count min">
              <input className="lab-input" value={signalsMin} onChange={(e) => setSignalsMin(e.target.value)} />
            </Field>
            <Field label="Signals count max">
              <input className="lab-input" value={signalsMax} onChange={(e) => setSignalsMax(e.target.value)} />
            </Field>
            <Field label="Signal attivo">
              <select
                className="lab-input"
                value={signalActive}
                onChange={(e) => setSignalActive(e.target.value)}
              >
                <option value="">Tutti</option>
                <option value="yes">Attivo</option>
                <option value="no">Non attivo</option>
              </select>
            </Field>
            {(['D', 'E', 'F', 'G'] as const).map((col) => (
              <Field key={col} label={`Signal ${col}`}>
                <select
                  className="lab-input"
                  value={signalCols[col] || ''}
                  onChange={(e) => {
                    const v = e.target.value
                    setSignalCols((prev) => {
                      const next = { ...prev }
                      if (!v) delete next[col]
                      else next[col] = v
                      return next
                    })
                  }}
                >
                  <option value="">—</option>
                  <option value="on">ON</option>
                  <option value="off">OFF</option>
                </select>
              </Field>
            ))}
            <Field label="Consensus">
              <select
                className="lab-input"
                value={consensusStatus}
                onChange={(e) => setConsensusStatus(e.target.value)}
              >
                <option value="">Tutti</option>
                {options.consensus_statuses.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Geometry min">
              <input className="lab-input" value={geometryMin} onChange={(e) => setGeometryMin(e.target.value)} />
            </Field>
            <Field label="Geometry max">
              <input className="lab-input" value={geometryMax} onChange={(e) => setGeometryMax(e.target.value)} />
            </Field>
            <Field label="Balance class">
              <select className="lab-input" value={balanceClass} onChange={(e) => setBalanceClass(e.target.value)}>
                <option value="">Tutte</option>
                {options.balance_classes.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Goal composite min">
              <input className="lab-input" value={goalMin} onChange={(e) => setGoalMin(e.target.value)} />
            </Field>
            <Field label="Goal composite max">
              <input className="lab-input" value={goalMax} onChange={(e) => setGoalMax(e.target.value)} />
            </Field>
            <Field label="Goal class / direction">
              <select className="lab-input" value={goalClass} onChange={(e) => setGoalClass(e.target.value)}>
                <option value="">Tutte</option>
                {options.goal_final_classes.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="V3.6 max">
              <input className="lab-input" value={purchMax} onChange={(e) => setPurchMax(e.target.value)} />
            </Field>
            <Field label="V3.6 max esclusivo">
              <label className="flex items-center gap-2 pt-2 text-xs">
                <input
                  type="checkbox"
                  checked={purchMaxExclusive}
                  onChange={(e) => setPurchMaxExclusive(e.target.checked)}
                />
                score &lt; max (es. [40,60))
              </label>
            </Field>
            {(
              [
                ['offensive_stability', 'Goal · offensive_stability'],
                ['defensive_solidity', 'Goal · defensive_solidity'],
                ['offensive_production', 'Goal · offensive_production'],
                ['match_tempo', 'Goal · match_tempo'],
              ] as const
            ).map(([key, label]) => (
              <Field key={key} label={label}>
                <input
                  className="lab-input"
                  placeholder="class (es. high)"
                  value={goalPillarFilters[key]?.class || ''}
                  onChange={(e) => {
                    const v = e.target.value.trim()
                    setGoalPillarFilters((prev) => {
                      const next = { ...prev }
                      if (!v) delete next[key]
                      else next[key] = { ...next[key], class: v }
                      return next
                    })
                  }}
                />
              </Field>
            ))}
            <Field label="V3.6 class">
              <select className="lab-input" value={purchClass} onChange={(e) => setPurchClass(e.target.value)}>
                <option value="">Tutte</option>
                {options.purchasability_v36_classes.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="V3.6 status">
              <select className="lab-input" value={purchStatus} onChange={(e) => setPurchStatus(e.target.value)}>
                <option value="">Tutti</option>
                {options.purchasability_v36_statuses.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="V3.6 gate">
              <select className="lab-input" value={purchGate} onChange={(e) => setPurchGate(e.target.value)}>
                <option value="">Tutti</option>
                {options.purchasability_v36_gates.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Historical Bet Builder">
              <select className="lab-input" value={bbActive} onChange={(e) => setBbActive(e.target.value)}>
                <option value="">Tutti</option>
                <option value="yes">Active sì</option>
                <option value="no">Active no</option>
              </select>
            </Field>
            <Field label="BB rank min">
              <input className="lab-input" value={bbRankMin} onChange={(e) => setBbRankMin(e.target.value)} />
            </Field>
            <Field label="BB rank max">
              <input className="lab-input" value={bbRankMax} onChange={(e) => setBbRankMax(e.target.value)} />
            </Field>
            <Field label="Quote real/derived">
              <select className="lab-input" value={quoteType} onChange={(e) => setQuoteType(e.target.value)}>
                <option value="">Tutti</option>
                <option value="real">Real</option>
                <option value="derived">Derived</option>
              </select>
            </Field>
            <Field label="Esito">
              <select className="lab-input" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
                <option value="">Tutti</option>
                <option value="won">Won</option>
                <option value="lost">Lost</option>
                <option value="void">Void</option>
              </select>
            </Field>
            <Field label="Data da">
              <input type="date" className="lab-input" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </Field>
            <Field label="Data a">
              <input type="date" className="lab-input" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </Field>
          </div>
        </details>
      </section>

      {summary ? (
        <>
          <PatternLabKpiRibbon
            summary={summary}
            marketInformativeDefault={!showWithoutEvidence}
          />
          <div
            className="rounded-xl px-4 py-3 text-sm font-medium"
            style={{
              background: 'rgba(46,230,255,0.06)',
              border: '1px solid var(--lab-border)',
              color: 'var(--lab-text)',
            }}
          >
            {patternRecap}
          </div>
          {insights ? <PatternLabModuleInsights insights={insights} /> : null}
          {breakdown ? (
            <PatternLabStabilityCharts
              bySeason={breakdown.by_season}
              byCompetition={breakdown.by_competition}
              byMarket={breakdown.by_market}
            />
          ) : null}
        </>
      ) : null}

      <section className="lab-card rounded-xl p-4">
        <div className="flex gap-3 text-sm">
          <button
            type="button"
            className={`lab-tab rounded-t-lg px-3 py-1.5 ${detailTab === 'explore' ? 'lab-tab-active' : ''}`}
            onClick={() => setDetailTab('explore')}
          >
            Esplora giocate
          </button>
          <button
            type="button"
            className={`lab-tab rounded-t-lg px-3 py-1.5 ${detailTab === 'bet_builder' ? 'lab-tab-active' : ''}`}
            onClick={() => setDetailTab('bet_builder')}
          >
            Replay Bet Builder
          </button>
        </div>

        {detailTab === 'explore' && result?.rows?.length ? (
          <div className="mt-3 overflow-auto">
            <table className="lab-table w-full text-xs">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Kickoff</th>
                  <th>Match</th>
                  <th>Market</th>
                  <th>Quota</th>
                  <th>Rating</th>
                  <th>Signals</th>
                  <th>V3.6</th>
                  <th>Geom</th>
                  <th>Goal</th>
                  <th>Esito</th>
                  <th>P/L</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={`${r.run_id}-${r.snapshot_id}-${r.market_key}`}>
                    <td>{String(r.run_id)}</td>
                    <td>{String(r.kickoff_at ?? '').slice(0, 16)}</td>
                    <td>
                      {String(r.home_team)}–{String(r.away_team)}
                    </td>
                    <td>{String(r.market_label || r.market_key)}</td>
                    <td>{formatNum(r.pre_quota_bet365 as number | null)}</td>
                    <td>{String(r.pre_rating ?? '—')}</td>
                    <td>{String(r.pre_signal_count ?? 0)}</td>
                    <td>{formatNum(r.pre_purch_v36_score as number | null, 1)}</td>
                    <td>{formatNum(r.pre_balance_geometry as number | null, 1)}</td>
                    <td>{formatNum(r.pre_goal_v4_compat_composite as number | null, 1)}</td>
                    <td>
                      {r.target_won === true ? 'W' : r.target_lost === true ? 'L' : r.target_void ? 'V' : '—'}
                    </td>
                    <td>{formatNum(r.target_profit_1u as number | null)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {detailTab === 'explore' && result && !result.rows?.length ? (
          <p className="mt-3 text-sm" style={{ color: 'var(--lab-muted)' }}>
            Nessuna giocata per i filtri correnti. Premi Analizza dopo aver selezionato le run.
          </p>
        ) : null}

        {detailTab === 'bet_builder' && bbResult ? (
          <div className="mt-3 space-y-3">
            <p className="text-xs" style={{ color: 'var(--lab-muted)' }}>
              Sort policy storica: V3.6 al posto di V3.1 Evidence Sort. Selezioni BB:{' '}
              {bbResult.summary.selections} · ROI {formatPct(bbResult.summary.roi)}
            </p>
            <div className="overflow-auto">
              <table className="lab-table w-full text-sm">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>N</th>
                    <th>W</th>
                    <th>L</th>
                    <th>Profit</th>
                    <th>ROI</th>
                  </tr>
                </thead>
                <tbody>
                  {bbResult.timeline_by_day.map((d) => (
                    <tr key={d.date}>
                      <td>{d.date}</td>
                      <td>{d.selections}</td>
                      <td>{d.wins}</td>
                      <td>{d.losses}</td>
                      <td>{formatNum(d.profit_1u)}</td>
                      <td>{formatPct(d.roi)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  )
}
