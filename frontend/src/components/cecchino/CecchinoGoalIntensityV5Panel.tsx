import { useCallback, useState } from 'react'
import type {
  CecchinoGiV5ExplanationsResponse,
  CecchinoTodayDetailResponse,
} from '../../lib/cecchinoTodayApi'
import { getGoalIntensityV5Explanations } from '../../lib/cecchinoTodayApi'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

type GoalIntensityPayload = NonNullable<CecchinoTodayDetailResponse['goal_intensity_v5']>

type Props = {
  goalIntensity?: GoalIntensityPayload | null
  todayFixtureId?: number | null
  providerFixtureId?: number | null
}

function fmt(v: number | null | undefined, digits = 1): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return Number(v).toFixed(digits)
}

function fmtProb(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return `${(Number(v) * 100).toFixed(1)}%`
}

function Badge({
  children,
  tone = 'slate',
}: {
  children: React.ReactNode
  tone?: 'slate' | 'amber' | 'emerald' | 'sky'
}) {
  const tones = {
    slate: 'bg-slate-100 text-slate-700',
    amber: 'bg-amber-50 text-amber-800',
    emerald: 'bg-emerald-50 text-emerald-800',
    sky: 'bg-sky-50 text-sky-800',
  }
  return (
    <span className={`inline-flex rounded px-2 py-0.5 text-[11px] font-medium ${tones[tone]}`}>
      {children}
    </span>
  )
}

function ProbBlock({
  title,
  overLabel,
  underLabel,
  over,
  under,
}: {
  title: string
  overLabel: string
  underLabel: string
  over: number | null | undefined
  under: number | null | undefined
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2.5">
      <p className="text-xs font-semibold text-slate-800">{title}</p>
      <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
        <div>
          <p className="text-[11px] text-slate-500">{overLabel}</p>
          <p className="font-semibold text-slate-900">{fmtProb(over)}</p>
        </div>
        <div>
          <p className="text-[11px] text-slate-500">{underLabel}</p>
          <p className="font-semibold text-slate-900">{fmtProb(under)}</p>
        </div>
      </div>
    </div>
  )
}

function UnavailablePanel({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <section className={`${todayCard} ${todayCardPadding}`}>
      <h3 className={todaySectionTitle}>{title}</h3>
      <p className={todaySectionSubtitle}>{subtitle}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Badge>Non collegato ai Segnali</Badge>
      </div>
    </section>
  )
}

function readOutputProb(outputs: Record<string, unknown> | undefined, key: string): number | null {
  const block = outputs?.[key]
  if (block && typeof block === 'object' && 'probability' in block) {
    const v = (block as { probability?: unknown }).probability
    return v == null || Number.isNaN(Number(v)) ? null : Number(v)
  }
  return null
}

function readOutputValue(outputs: Record<string, unknown> | undefined, key: string): number | null {
  const block = outputs?.[key]
  if (block && typeof block === 'object' && 'value' in block) {
    const v = (block as { value?: unknown }).value
    return v == null || Number.isNaN(Number(v)) ? null : Number(v)
  }
  return null
}

function OfficialAuditCollapsible({
  explanations,
}: {
  explanations: CecchinoGiV5ExplanationsResponse & {
    index?: Record<string, unknown>
    target_heads?: Record<string, Record<string, unknown>>
  }
}) {
  const index = explanations.index || {}
  const heads = explanations.target_heads || {}
  return (
    <div className="mt-4 rounded-lg border border-slate-200 bg-white p-3" data-testid="gi-official-audit">
      <p className="text-xs font-semibold text-slate-800">Audit operativo</p>
      <p className="mt-1 text-[11px] text-slate-500">
        Indice unico e teste per mercato. Nessun candidato research.
      </p>
      <div className="mt-3 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
        <div className="rounded border border-slate-100 bg-slate-50 px-2 py-1.5">
          <p className="text-slate-500">Indice</p>
          <p className="font-medium text-slate-900">{String(index.id ?? 'GI_A_STRICT_CORE')}</p>
          <p className="font-mono">{fmt(index.score_audit as number | null | undefined, 2)}</p>
          <p className="text-slate-500">{String(index.formula ?? '')}</p>
        </div>
        {Object.entries(heads).map(([key, head]) => (
          <div key={key} className="rounded border border-slate-100 bg-slate-50 px-2 py-1.5">
            <p className="font-medium text-slate-800">{String(head.label_it ?? key)}</p>
            <p className="text-slate-500">source: {String(head.calibration_source ?? '—')}</p>
            <p className="font-mono">
              i={fmt(head.intercept as number | null | undefined, 4)} · c=
              {fmt(head.coefficient as number | null | undefined, 4)}
            </p>
            <p className="font-mono">
              {String(head.transform)} → {fmt(head.result_audit as number | null | undefined, 4)}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}

export function CecchinoGoalIntensityV5Panel({
  goalIntensity,
  todayFixtureId,
}: Props) {
  const [explanations, setExplanations] = useState<
    | (CecchinoGiV5ExplanationsResponse & {
        index?: Record<string, unknown>
        target_heads?: Record<string, Record<string, unknown>>
      })
    | null
  >(null)
  const [auditOpen, setAuditOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadExplanations = useCallback(async () => {
    if (todayFixtureId == null) return null
    setLoading(true)
    setError(null)
    try {
      const res = await getGoalIntensityV5Explanations(todayFixtureId)
      setExplanations(res as never)
      return res
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore audit')
      return null
    } finally {
      setLoading(false)
    }
  }, [todayFixtureId])

  const toggleAudit = async () => {
    if (auditOpen) {
      setAuditOpen(false)
      return
    }
    const res = explanations ?? (await loadExplanations())
    if (res) setAuditOpen(true)
  }

  if (!goalIntensity || goalIntensity.status === 'unavailable') {
    return (
      <UnavailablePanel title="Intensità Goal V5" subtitle="Modulo non disponibile per questa partita." />
    )
  }

  if (goalIntensity.status === 'error' && !(goalIntensity as { snapshot?: unknown }).snapshot) {
    return (
      <UnavailablePanel
        title="Intensità Goal V5"
        subtitle={goalIntensity.banner ?? 'Snapshot non disponibile.'}
      />
    )
  }

  const gi = goalIntensity as GoalIntensityPayload & {
    bundle_version?: string
    operational_status?: string
    operational_status_label_it?: string
    source?: string
    presentation?: string
    legacy_archive?: boolean
    index?: { id?: string; score?: number | null } | null
    outputs?: Record<string, unknown>
    data_quality?: { feature_status?: string; history_sample_size?: number | null }
    fallback?: { fallback_reason?: string; btts_unavailable?: boolean } | null
    calibrated_predictions?: Record<string, Record<string, number | null | string | boolean>>
    snapshot?: Record<string, unknown>
    primary_candidate_score?: number | null
  }

  const source = gi.source || (gi.legacy_archive ? 'v5_legacy_preview' : 'v5_official')
  const isFallback = source === 'v4_fallback'
  const isLegacy =
    Boolean(gi.legacy_archive) ||
    gi.presentation === 'legacy_archive' ||
    source === 'v5_legacy_preview'
  const isOfficial =
    !isFallback &&
    !isLegacy &&
    (gi.operational_status === 'official_support' || source === 'v5_official')

  const outputs = gi.outputs
  let indexScore = gi.index?.score ?? gi.primary_candidate_score ?? null
  let expected = readOutputValue(outputs, 'expected_total_goals')
  let over15 = readOutputProb(outputs, 'over_1_5')
  let under15 = readOutputProb(outputs, 'under_1_5')
  let over25 = readOutputProb(outputs, 'over_2_5')
  let under25 = readOutputProb(outputs, 'under_2_5')
  let bttsYes = readOutputProb(outputs, 'btts_yes')
  let bttsNo = readOutputProb(outputs, 'btts_no')

  if (expected == null || over15 == null) {
    const snap = (gi.snapshot || {}) as Record<string, unknown>
    const cal = (gi.calibrated_predictions ||
      snap.calibrated_predictions ||
      {}) as Record<string, Record<string, number | null>>
    const block = cal.OFFICIAL_SUPPORT || cal.GI_A_STRICT_CORE
    if (block) {
      if (indexScore == null) {
        const raw = Number(block.raw_score ?? gi.primary_candidate_score ?? NaN)
        indexScore = Number.isNaN(raw) ? null : raw
      }
      if (expected == null) expected = block.expected_total_goals ?? null
      if (over15 == null) over15 = block.probability_goals_ge_2 ?? null
      if (over25 == null) over25 = block.probability_goals_ge_3 ?? null
      if (bttsYes == null) bttsYes = block.probability_btts ?? null
      if (under15 == null && over15 != null) under15 = 1 - over15
      if (under25 == null && over25 != null) under25 = 1 - over25
      if (bttsNo == null && bttsYes != null) bttsNo = 1 - bttsYes
    }
  }

  const bttsUnavailable = isFallback || Boolean(gi.fallback?.btts_unavailable)
  const statusLabel =
    gi.operational_status_label_it ||
    (isOfficial
      ? 'Supporto ufficiale'
      : isLegacy
        ? 'Archivio preview'
        : isFallback
          ? 'Fallback V4'
          : 'Preview monitorata')

  return (
    <section className={`${todayCard} ${todayCardPadding}`} data-testid="goal-intensity-v5-official-card">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className={todaySectionTitle}>Intensità Goal V5</h3>
          <p className={todaySectionSubtitle}>
            Supporto analitico contestuale sui mercati goal. Non è un consiglio autonomo.
          </p>
          {error ? <p className="mt-2 text-xs text-amber-700">{error}</p> : null}
        </div>
        {todayFixtureId != null ? (
          <button
            type="button"
            onClick={() => void toggleAudit()}
            disabled={loading}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {loading ? 'Caricamento…' : auditOpen ? 'Chiudi audit' : 'Apri audit'}
          </button>
        ) : null}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <Badge tone={isOfficial ? 'emerald' : isFallback ? 'amber' : 'sky'}>{statusLabel}</Badge>
        <Badge>Non collegato ai Segnali</Badge>
        {isFallback ? <Badge tone="amber">Fallback V4</Badge> : null}
        {isLegacy ? <Badge tone="sky">Archivio preview</Badge> : null}
        {gi.bundle_version ? <Badge>{gi.bundle_version}</Badge> : null}
      </div>

      {isFallback && gi.fallback?.fallback_reason ? (
        <p className="mt-2 text-xs text-amber-800">
          Motivo fallback: {gi.fallback.fallback_reason}. BTTS / No Gol non disponibili.
        </p>
      ) : null}

      {!isLegacy ? (
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
            <p className="text-[11px] text-slate-500">Indice intensità (0–100)</p>
            <p className="text-2xl font-semibold text-slate-900" data-testid="gi-index-score">
              {fmt(indexScore, 1)}
            </p>
            <p className="mt-1 text-[11px] text-slate-500">GI_A_STRICT_CORE</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
            <p className="text-[11px] text-slate-500">Stima totale gol</p>
            <p className="text-2xl font-semibold text-slate-900" data-testid="gi-expected-total">
              {fmt(expected, 2)}
            </p>
            <p className="mt-1 text-[11px] text-slate-500">
              {isFallback ? 'Goal attesi Cecchino interni (V4)' : 'Stima calibrata del totale gol'}
            </p>
          </div>
          <ProbBlock title="Linea 1.5" overLabel="Over 1.5" underLabel="Under 1.5" over={over15} under={under15} />
          <ProbBlock title="Linea 2.5" overLabel="Over 2.5" underLabel="Under 2.5" over={over25} under={under25} />
          <div className="rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2.5 sm:col-span-2">
            <p className="text-xs font-semibold text-slate-800">Gol / No Gol</p>
            <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
              <div>
                <p className="text-[11px] text-slate-500">Gol</p>
                <p className="font-semibold text-slate-900">{bttsUnavailable ? 'N/D' : fmtProb(bttsYes)}</p>
              </div>
              <div>
                <p className="text-[11px] text-slate-500">No Gol</p>
                <p className="font-semibold text-slate-900">{bttsUnavailable ? 'N/D' : fmtProb(bttsNo)}</p>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-600">
          Snapshot di archivio preview. Non presentare come risultato ufficiale.
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-slate-500">
        <span>Fonte: {source}</span>
        {gi.data_quality?.feature_status ? <span>Qualità dati: {gi.data_quality.feature_status}</span> : null}
      </div>

      {auditOpen && explanations ? <OfficialAuditCollapsible explanations={explanations} /> : null}
    </section>
  )
}

export default CecchinoGoalIntensityV5Panel
