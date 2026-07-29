import type { CecchinoKpiExplanation } from '../../lib/cecchinoTodayApi'
import {
  formatPenaltyPointsNegative,
  formatV3Number,
  formatV3PctAlready,
  formatV3PctFromFraction,
} from './cecchinoKpiUiUtils'

type Props = {
  explanation: CecchinoKpiExplanation
}

type UnknownRecord = Record<string, unknown>

type FamilyMarketRow = {
  market_key?: string | null
  market_label?: string | null
  market_family?: string | null
  edge_pct?: number | null
  gate_status?: string | null
  gate_passed?: boolean | null
  is_selected?: boolean | null
  is_leader?: boolean | null
  is_second?: boolean | null
  rank_by_edge?: number | null
  included_in_family?: boolean | null
  included_in_gate_passed_comparison?: boolean | null
  score?: number | null
  edge_diff_from_leader?: number | null
}

function asRecord(v: unknown): UnknownRecord | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as UnknownRecord) : null
}

function asString(v: unknown): string | null {
  if (v == null) return null
  return String(v)
}

function asNumber(v: unknown): number | null {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isNaN(n) ? null : n
}

function asBool(v: unknown): boolean | null {
  if (typeof v === 'boolean') return v
  return null
}

function asStringList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.map((x) => String(x))
}

function yesNo(v: boolean | null | undefined): string {
  if (v === true) return 'Sì'
  if (v === false) return 'No'
  return '—'
}

const PENALTY_ORDER = [
  'probability_risk',
  'opposite_market_pressure',
  'extreme_divergence',
  'family_ambiguity',
  'quote_quality',
] as const

const PENALTY_TITLES: Record<string, string> = {
  probability_risk: 'Rischio di probabilità',
  opposite_market_pressure: 'Pressione del mercato opposto',
  extreme_divergence: 'Divergenza estrema e fragile',
  family_ambiguity: 'Ambiguità nella famiglia',
  quote_quality: 'Qualità della quota',
}

const MARKET_LABELS: Record<string, string> = {
  HOME: '1',
  DRAW: 'X',
  AWAY: '2',
  ONE_X: '1X',
  X_TWO: 'X2',
  ONE_TWO: '12',
  OVER_2_5: 'Over 2.5',
  UNDER_2_5: 'Under 2.5',
}

const HUMAN_CODE_LABELS: Record<string, string> = {
  normalized_1x2_market: 'Mercato 1X2 Betfair normalizzato',
  linked_double_chance_away_cover: 'X2 collegato al segno 2',
  linked_double_chance_home_cover: '1X collegato al segno 1',
  linked_double_chance_anti_draw: '12 collegato al pareggio',
  leader_clear: 'Leader netto',
  leader_close: 'Leader con margine ridotto',
  not_leader: 'Non leader della famiglia',
  insufficient_family_comparison: 'Confronto famiglia insufficiente',
  AWAY_to_X_TWO: '2 → X2 (contesto collegato)',
  HOME_to_ONE_X: '1 → 1X (contesto collegato)',
}

const EDGE_SCALE = [
  { edge: '0%', value: '0' },
  { edge: '10%', value: '20' },
  { edge: '20%', value: '40' },
  { edge: '25%', value: '50' },
  { edge: '40%', value: '80' },
  { edge: '50%+', value: '100' },
]

function marketLabel(key: string | null | undefined): string {
  if (!key) return '—'
  return MARKET_LABELS[key] || key
}

function humanizeCode(code: string | null | undefined): string {
  if (!code) return '—'
  return HUMAN_CODE_LABELS[code] || code
}

function DlRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
      <dt className="shrink-0 text-slate-500 sm:w-44">{label}</dt>
      <dd className="font-medium text-slate-900">{children}</dd>
    </div>
  )
}

function Section({
  title,
  children,
  testId,
}: {
  title: string
  children: React.ReactNode
  testId?: string
}) {
  return (
    <section
      className="rounded-lg border border-slate-200 px-3 py-3"
      data-testid={testId}
    >
      <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h4>
      <div className="mt-2 space-y-2 text-sm text-slate-800">{children}</div>
    </section>
  )
}

function gateStatusHuman(status: string | null): string {
  if (!status) return '—'
  if (status === 'passed') return 'passed'
  if (status === 'unsupported_market') return 'unsupported_market'
  if (status === 'unavailable_inputs') return 'unavailable_inputs'
  return status
}

export function CecchinoPurchasabilityV3AuditView({ explanation }: Props) {
  const explRec = explanation as UnknownRecord
  const gate = asRecord(explanation.gate) ?? {}
  const value = asRecord(explanation.value) ?? {}
  const quality = asRecord(explanation.quality) ?? {}
  const penalties = asRecord(explanation.penalties_table) ?? {}
  const family = asRecord(explanation.family_comparison) ?? {}
  const opposite = asRecord(explanation.opposite_market) ?? {}
  const linked = asRecord(explanation.linked_market_context)
  const finalCalc = asRecord(explanation.final_calculation) ?? {}
  const persisted = asRecord(explanation.persisted_result) ?? {}
  const dataOrigin = asRecord(explanation.data_origin) ?? {}
  const input = asRecord(explanation.input) ?? {}
  const dep = asRecord(explanation.dependency_meta) ?? {}

  const gateStatus = asString(gate.gate_status) ?? asString(persisted.gate_status)
  const gatePassed = gateStatus === 'passed'
  const gateFailed = Boolean(gateStatus && gateStatus !== 'passed')
  const gateReading = asString(gate.gate_reading)

  const score =
    asNumber(finalCalc.score) ??
    asNumber(persisted.score) ??
    (typeof explanation.stored_result === 'number' ? explanation.stored_result : null)
  const klass = asString(finalCalc.class) ?? asString(persisted.class)

  const marketFamilyLabel =
    asString(explRec.market_family_label) ?? asString(family.market_family_label)
  const marketFamilyCode =
    asString(explRec.market_family) ??
    asString(family.market_family) ??
    asString(input.market_family)

  const readingShort = asString(explanation.reading_short)
  const readingDetailed =
    asString(explanation.reading_detailed) ?? asString(explanation.simple_explanation)
  const readingsIdentical =
    Boolean(readingShort && readingDetailed && readingShort === readingDetailed)
  const showDetailedOutsideBox = Boolean(readingDetailed && !readingsIdentical)
  const howToReadText =
    readingDetailed ||
    readingShort ||
    'Il valore della quota viene ridotto dalle penalità di qualità rilevate.'

  const candidateVersion =
    asString(explRec.candidate_version) ?? asString(input.candidate_version)
  const formulaVersion = explanation.formula_version ?? null
  const auditVersion = asString(explRec.audit_version)
  const generatedAt =
    asString(explRec.generated_at) ?? asString(dataOrigin.generated_at)
  const sourceSnapshotAt =
    asString(explRec.source_snapshot_at) ?? asString(dataOrigin.source_snapshot_at)

  const derivedQuote =
    asBool(explRec.derived_quote) === true ||
    asString(input.performance_type) === 'derived' ||
    asBool(input.not_real_book_quote) === true ||
    asBool(input.diagnostic_only) === true
  const diagnosticOnly =
    asBool(explRec.diagnostic_only) === true ||
    asBool(input.diagnostic_only) === true ||
    derivedQuote

  const badges = [
    'V3 parallela',
    'Scale fisse',
    'Nessun profilo storico',
    'Pre-match',
    'Non validata storicamente',
    ...((explanation.audit_badges as string[] | undefined) ?? []).filter(
      (b) =>
        !['V3 parallela', 'Scale fisse', 'Nessun profilo storico', 'Pre-match'].includes(b),
    ),
  ]

  const formulaSteps = asStringList(finalCalc.formula_steps)
  const edgePct = asNumber(input.edge_pct)
  const vantPp = asNumber(input.probability_advantage_pp) ?? asNumber(input.vantaggio_prob)
  const vantFraction =
    vantPp != null && Math.abs(vantPp) <= 1 ? vantPp : vantPp != null ? vantPp / 100 : null

  const marketRowsRaw = family.market_rows
  const marketRows: FamilyMarketRow[] = Array.isArray(marketRowsRaw)
    ? (marketRowsRaw as FamilyMarketRow[])
    : []

  const familyReading = (() => {
    const selectedIsLeader = asBool(family.selected_is_family_edge_leader)
    const gap = asNumber(family.edge_gap_or_deficit)
    if (selectedIsLeader === true) {
      return `Il mercato analizzato ha l’Edge più alto della famiglia${
        gap != null ? ` con un distacco di ${formatV3Number(gap)} punti.` : '.'
      }`
    }
    if (selectedIsLeader === false) {
      return 'Un altro mercato della famiglia presenta Edge maggiore.'
    }
    return null
  })()

  const oppPenalty = asNumber(opposite.opposite_pressure_penalty)
  const totalPenalty = asNumber(quality.total_penalty)
  const qualityStart = asNumber(quality.quality_start) ?? 100
  const qualityScore = asNumber(quality.quality_score)
  const valueScore = asNumber(value.value_score)

  const sourcePaths = dataOrigin.source_paths
  const sourcePathList = Array.isArray(sourcePaths)
    ? sourcePaths.map(String)
    : sourcePaths && typeof sourcePaths === 'object'
      ? Object.entries(sourcePaths as UnknownRecord).map(([k, v]) => `${k}: ${String(v)}`)
      : []

  const quoteQualityPen = asRecord(penalties.quote_quality)

  return (
    <div className="space-y-4" data-testid="purchasability-v3-audit-view">
      <Section title="Risultato in parole semplici" testId="v3-section-result">
        <div className="flex flex-wrap gap-1.5" data-testid="v3-badges">
          {badges.map((b) => (
            <span
              key={b}
              className="rounded border border-sky-200 bg-sky-50 px-1.5 py-0.5 text-[10px] font-semibold text-sky-900"
            >
              {b}
            </span>
          ))}
          <span
            className="rounded border border-cyan-200 bg-cyan-50 px-1.5 py-0.5 text-[10px] font-semibold text-cyan-900"
            data-testid="v3-badge-candidate"
          >
            V3 candidato
          </span>
          {formulaVersion ? (
            <span
              className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-semibold text-slate-800"
              data-testid="v3-badge-formula"
            >
              Formula fixed discount v1
            </span>
          ) : null}
          {derivedQuote ? (
            <span
              className="rounded border border-violet-200 bg-violet-50 px-1.5 py-0.5 text-[10px] font-semibold text-violet-900"
              data-testid="v3-badge-derived"
            >
              Quota derivata
            </span>
          ) : null}
          {diagnosticOnly ? (
            <span
              className="rounded border border-violet-200 bg-violet-50 px-1.5 py-0.5 text-[10px] font-semibold text-violet-900"
              data-testid="v3-badge-diagnostic"
            >
              Solo diagnostico
            </span>
          ) : null}
        </div>
        <dl className="mt-2 space-y-1.5 text-sm">
          <DlRow label="Score finale">
            <span data-testid="v3-score-final">
              {gateFailed && score == null ? 'Indice non attivato' : score ?? '—'}
            </span>
          </DlRow>
          <DlRow label="Classe">{gateFailed && !klass ? '—' : klass ?? '—'}</DlRow>
          <DlRow label="Stato gate">{gateStatusHuman(gateStatus)}</DlRow>
          <DlRow label="Mercato">{explanation.market_label || explanation.market_key}</DlRow>
          <DlRow label="Famiglia">
            <span data-testid="v3-family-label">{marketFamilyLabel ?? '—'}</span>
          </DlRow>
        </dl>
        {readingShort ? (
          <p
            className="mt-2 rounded-md bg-slate-50 px-2.5 py-2 text-sm font-medium text-slate-900"
            data-testid="v3-reading-short"
          >
            {readingShort}
          </p>
        ) : null}
        {showDetailedOutsideBox ? (
          <p className="text-sm leading-relaxed text-slate-700" data-testid="v3-reading-detailed-inline">
            {readingDetailed}
          </p>
        ) : null}
        <div
          className="rounded-md border border-indigo-100 bg-indigo-50/60 px-2.5 py-2 text-sm text-indigo-950"
          data-testid="v3-how-to-read"
        >
          <p className="text-[10px] font-semibold uppercase tracking-wide text-indigo-700">
            Come leggere questo risultato
          </p>
          <p className="mt-1" data-testid="v3-reading-detailed">
            {howToReadText}
          </p>
        </div>
      </Section>

      <Section title="1. Esiste valore?" testId="v3-section-gate">
        <p className="text-xs text-slate-600">
          L’indice si attiva soltanto quando Edge e vantaggio probabilistico sono entrambi
          positivi.
        </p>
        {gateReading ? (
          <p
            className={`rounded-md border px-2.5 py-2 text-sm font-semibold ${
              gatePassed
                ? 'border-emerald-200 bg-emerald-50 text-emerald-950'
                : 'border-amber-200 bg-amber-50 text-amber-950'
            }`}
            data-testid="v3-gate-reading"
          >
            {gateReading}
          </p>
        ) : gateFailed ? (
          <p
            className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-2 text-sm font-semibold text-amber-950"
            data-testid="v3-gate-not-activated"
          >
            Indice non attivato
          </p>
        ) : null}
        <dl className="space-y-1.5">
          <DlRow label="Edge">{formatV3PctAlready(edgePct)}</DlRow>
          <DlRow label="Edge positivo">{yesNo(asBool(gate.edge_positive))}</DlRow>
          <DlRow label="Vantaggio probabilistico">
            {vantFraction != null
              ? `${vantFraction > 0 ? '+' : ''}${formatV3Number(vantFraction * 100)} pp`
              : '—'}
          </DlRow>
          <DlRow label="Vantaggio positivo">
            {yesNo(asBool(gate.probability_advantage_positive))}
          </DlRow>
          <DlRow label="Gate">{gateStatus ?? '—'}</DlRow>
          <DlRow label="Motivazione">{gateReading ?? '—'}</DlRow>
        </dl>
        {(Object.keys(input).length > 0 || gateFailed) && (
          <details className="rounded border border-slate-200" data-testid="v3-raw-inputs-details">
            <summary
              className="cursor-pointer px-2.5 py-2 text-xs font-semibold text-slate-700 outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
              data-testid="v3-raw-inputs-summary"
            >
              Mostra dati tecnici grezzi
            </summary>
            <div className="overflow-x-auto border-t border-slate-100 px-1 pb-2">
              <table className="w-full min-w-[320px] text-left text-xs">
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    <th className="px-2 py-1">Input grezzo</th>
                    <th className="px-2 py-1">Valore</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(input).map(([k, v]) => (
                    <tr key={k} className="border-t border-slate-100">
                      <td className="px-2 py-1 font-mono text-[10px]">{k}</td>
                      <td className="px-2 py-1 tabular-nums">{v == null ? '—' : String(v)}</td>
                    </tr>
                  ))}
                  <tr className="border-t border-slate-100">
                    <td className="px-2 py-1 font-mono text-[10px]">gate_reason_codes</td>
                    <td className="px-2 py-1">
                      {(asStringList(gate.gate_reason_codes) || []).join(', ') || '—'}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </details>
        )}
      </Section>

      {gatePassed ? (
        <Section title="2. Quanto è forte il valore?" testId="v3-section-value">
          <dl className="space-y-1.5">
            <DlRow label="Quota Book">{formatV3Number(asNumber(input.quota_book))}</DlRow>
            <DlRow label="Quota Cecchino">
              {formatV3Number(asNumber(input.quota_cecchino))}
            </DlRow>
            <DlRow label="Probabilità Book fair">
              {formatV3PctFromFraction(asNumber(input.fair_book_probability))}
            </DlRow>
            <DlRow label="Probabilità Book grezza">
              {formatV3PctFromFraction(asNumber(input.raw_book_probability))}
            </DlRow>
            <DlRow label="Probabilità Cecchino">
              {asNumber(input.probability_cecchino_pct) != null
                ? formatV3PctAlready(asNumber(input.probability_cecchino_pct))
                : formatV3PctFromFraction(asNumber(input.probability_cecchino))}
            </DlRow>
            <DlRow label="Edge">{formatV3PctAlready(edgePct)}</DlRow>
            <DlRow label="Vantaggio probabilistico">
              {vantFraction != null
                ? `${vantFraction > 0 ? '+' : ''}${formatV3Number(vantFraction * 100)} pp`
                : '—'}
            </DlRow>
            <DlRow label="Value score">{formatV3Number(valueScore)}</DlRow>
          </dl>
          <div data-testid="v3-edge-scale">
            <p className="text-[10px] font-semibold uppercase text-slate-500">Scala fissa Edge</p>
            <div className="mt-1 overflow-x-auto">
              <table className="w-full min-w-[280px] text-left text-xs">
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    <th className="px-2 py-1">Edge</th>
                    <th className="px-2 py-1">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {EDGE_SCALE.map((row) => (
                    <tr key={row.edge} className="border-t border-slate-100">
                      <td className="px-2 py-1">{row.edge}</td>
                      <td className="px-2 py-1 tabular-nums">{row.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <pre className="overflow-x-auto rounded-lg border border-slate-200 bg-[#0f2847] px-3 py-2 font-mono text-[11px] text-amber-100 whitespace-pre-wrap">
            {asString(value.value_formula) ||
              'value_score = clamp(edge_pct / 50 × 100, 0, 100)'}
          </pre>
          <ul className="list-disc space-y-1 pl-4 text-xs text-slate-600">
            <li>Rating non entra nel punteggio V3.</li>
            <li>
              Il vantaggio probabilistico serve al gate ma non viene pesato nuovamente.
            </li>
            <li>Nessun profilo storico modifica il valore.</li>
          </ul>
        </Section>
      ) : null}

      {gatePassed ? (
        <Section title="3. Quali rischi riducono il valore?" testId="v3-section-penalties">
          <div className="space-y-2">
            {PENALTY_ORDER.map((key) => {
              const pen = asRecord(penalties[key])
              if (!pen) return null
              const points = asNumber(pen.penalty_points)
              const raw = asRecord(pen.raw_inputs) ?? {}
              return (
                <div
                  key={key}
                  className="rounded-md border border-slate-200 bg-slate-50/80 px-2.5 py-2"
                  data-testid={`v3-penalty-${key}`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-900">
                      {asString(pen.label) || PENALTY_TITLES[key] || key}
                    </p>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                        pen.applied
                          ? 'bg-rose-100 text-rose-800'
                          : 'bg-slate-200 text-slate-600'
                      }`}
                    >
                      {pen.applied ? 'Applicata' : 'Non applicata'}
                    </span>
                  </div>
                  {asString(pen.explanation) ? (
                    <p className="mt-1 text-xs text-slate-700">{asString(pen.explanation)}</p>
                  ) : null}
                  {key === 'quote_quality' && derivedQuote ? (
                    <p
                      className="mt-2 rounded-md border border-violet-200 bg-violet-50 px-2 py-1.5 text-xs text-violet-950"
                      data-testid="v3-derived-quote-note"
                    >
                      Questa quota è derivata matematicamente e non rappresenta una quota Betfair
                      realmente rilevata. Il risultato serve soltanto per analisi.
                    </p>
                  ) : null}
                  <dl className="mt-2 grid grid-cols-1 gap-1 text-xs sm:grid-cols-2">
                    {Object.entries(raw).map(([rk, rv]) => (
                      <div key={rk}>
                        <span className="text-slate-500">{rk}: </span>
                        <span className="tabular-nums text-slate-900">
                          {rv == null ? '—' : String(rv)}
                        </span>
                      </div>
                    ))}
                    <div>
                      <span className="text-slate-500">Soglia iniziale: </span>
                      <span className="tabular-nums">
                        {formatV3Number(asNumber(pen.threshold_start))}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500">Soglia massima: </span>
                      <span className="tabular-nums">
                        {formatV3Number(asNumber(pen.threshold_full))}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500">Severità: </span>
                      <span className="tabular-nums">
                        {formatV3Number(asNumber(pen.severity))}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500">Penalità massima: </span>
                      <span className="tabular-nums">
                        {formatV3Number(asNumber(pen.max_points))}
                      </span>
                    </div>
                    <div className="sm:col-span-2">
                      <span className="text-slate-500">Punti sottratti: </span>
                      <span
                        className="font-semibold tabular-nums text-rose-700"
                        data-testid={`v3-penalty-points-${key}`}
                      >
                        {formatPenaltyPointsNegative(points)}
                      </span>
                    </div>
                  </dl>
                </div>
              )
            })}
          </div>
          {derivedQuote && !quoteQualityPen ? (
            <p
              className="rounded-md border border-violet-200 bg-violet-50 px-2.5 py-2 text-xs text-violet-950"
              data-testid="v3-derived-quote-note"
            >
              Questa quota è derivata matematicamente e non rappresenta una quota Betfair
              realmente rilevata. Il risultato serve soltanto per analisi.
            </p>
          ) : null}
          <dl className="mt-2 space-y-1 rounded-md border border-slate-200 px-2.5 py-2 text-sm">
            <DlRow label="Penalità totali">
              <span className="font-semibold text-rose-700" data-testid="v3-total-penalty">
                {formatPenaltyPointsNegative(totalPenalty)}
              </span>
            </DlRow>
            <DlRow label="Qualità iniziale">
              <span data-testid="v3-quality-start">{formatV3Number(qualityStart)}</span>
            </DlRow>
            <DlRow label="Qualità finale">
              <span data-testid="v3-quality-final">{formatV3Number(qualityScore)}</span>
            </DlRow>
          </dl>
        </Section>
      ) : null}

      {gatePassed ? (
        <Section
          title="4. È la scelta migliore nella sua famiglia?"
          testId="v3-section-family"
        >
          {marketRows.length > 0 ? (
            <div className="overflow-x-auto">
              <table
                className="w-full min-w-[520px] border-collapse text-left text-xs"
                data-testid="v3-family-table"
              >
                <thead className="bg-slate-100 text-slate-600">
                  <tr>
                    <th className="px-2 py-1.5">Mercato</th>
                    <th className="px-2 py-1.5">Edge</th>
                    <th className="px-2 py-1.5">Gate</th>
                    <th className="px-2 py-1.5">Posizione</th>
                    <th className="px-2 py-1.5">Leader</th>
                    <th className="px-2 py-1.5">Diff. dal leader</th>
                    <th className="px-2 py-1.5">Nel confronto</th>
                  </tr>
                </thead>
                <tbody>
                  {marketRows.map((row) => {
                    const mk = String(row.market_key || '')
                    const isSelected = Boolean(row.is_selected)
                    const isLeader = Boolean(row.is_leader)
                    const edge = asNumber(row.edge_pct)
                    const diff = asNumber(row.edge_diff_from_leader)
                    return (
                      <tr
                        key={mk}
                        className={`border-t border-slate-100 ${
                          isSelected ? 'bg-amber-50' : isLeader ? 'bg-emerald-50/70' : ''
                        }`}
                        data-testid={`v3-family-row-${mk}`}
                      >
                        <td className="px-2 py-1.5 font-medium">
                          {asString(row.market_label) || marketLabel(mk)}
                          {isSelected ? ' (analizzato)' : ''}
                          {isLeader ? (
                            <span
                              className="ml-1 rounded bg-emerald-100 px-1 py-px text-[9px] font-semibold text-emerald-800"
                              data-testid={`v3-family-leader-badge-${mk}`}
                            >
                              Leader
                            </span>
                          ) : null}
                        </td>
                        <td
                          className="px-2 py-1.5 tabular-nums"
                          data-testid={`v3-family-edge-${mk}`}
                        >
                          {edge != null ? formatV3PctAlready(edge) : '—'}
                        </td>
                        <td className="px-2 py-1.5">
                          {row.gate_passed
                            ? 'passed'
                            : asString(row.gate_status) || '—'}
                        </td>
                        <td className="px-2 py-1.5 tabular-nums">
                          {row.rank_by_edge != null ? String(row.rank_by_edge) : '—'}
                        </td>
                        <td className="px-2 py-1.5">{yesNo(isLeader)}</td>
                        <td
                          className="px-2 py-1.5 tabular-nums"
                          data-testid={`v3-family-diff-${mk}`}
                        >
                          {isLeader
                            ? '—'
                            : diff != null
                              ? formatV3Number(diff)
                              : '—'}
                        </td>
                        <td className="px-2 py-1.5">
                          {yesNo(asBool(row.included_in_gate_passed_comparison))}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-600" data-testid="v3-family-rows-missing">
              Confronto famiglia non disponibile nel payload audit.
            </p>
          )}
          {familyReading ? <p className="text-sm text-slate-700">{familyReading}</p> : null}
          <p className="text-xs text-slate-500">
            Ambiguità: {humanizeCode(asString(family.ambiguity_status))} · Penalità famiglia:{' '}
            {formatPenaltyPointsNegative(
              asNumber(asRecord(penalties.family_ambiguity)?.penalty_points),
            )}
          </p>
        </Section>
      ) : null}

      {gatePassed ? (
        <Section title="5. Quanto è forte il mercato opposto?" testId="v3-section-opposite">
          <dl className="space-y-1.5">
            <DlRow label="Mercato opposto">
              {marketLabel(asString(opposite.opposite_market_key))}
            </DlRow>
            <DlRow label="Probabilità Book fair opposta">
              {formatV3PctFromFraction(asNumber(opposite.opposite_fair_probability))}
            </DlRow>
            <DlRow label="Probabilità grezza opposta">
              {formatV3PctFromFraction(asNumber(opposite.opposite_raw_probability))}
            </DlRow>
            <DlRow label="Soglia inizio penalità">
              {formatV3Number(
                asNumber(
                  asRecord(penalties.opposite_market_pressure)?.threshold_start,
                ),
              )}
            </DlRow>
            <DlRow label="Soglia penalità massima">
              {formatV3Number(
                asNumber(asRecord(penalties.opposite_market_pressure)?.threshold_full),
              )}
            </DlRow>
            <DlRow label="Punti sottratti">
              <span className="font-semibold text-rose-700">
                {formatPenaltyPointsNegative(
                  oppPenalty ??
                    asNumber(
                      asRecord(penalties.opposite_market_pressure)?.penalty_points,
                    ),
                )}
              </span>
            </DlRow>
          </dl>
          {explanation.market_key === 'DRAW' ? (
            <p className="text-xs text-slate-600">
              Per il pareggio il sistema usa il lato più favorito fra HOME e AWAY come mercato
              opposto.
            </p>
          ) : null}
          <p className="rounded-md bg-rose-50 px-2.5 py-2 text-xs text-rose-900">
            La pressione del mercato opposto è una penalità reale: questi punti vengono sottratti
            dalla qualità.
          </p>
        </Section>
      ) : null}

      <Section title="Contesto collegato — non usato nello score" testId="v3-section-linked">
        {linked ? (
          <>
            <div className="flex flex-wrap gap-1.5">
              <span className="rounded border border-violet-200 bg-violet-50 px-1.5 py-0.5 text-[10px] font-semibold text-violet-900">
                Solo diagnostico
              </span>
              <span className="rounded border border-violet-200 bg-violet-50 px-1.5 py-0.5 text-[10px] font-semibold text-violet-900">
                Non modifica il punteggio
              </span>
            </div>
            <dl className="mt-2 space-y-1.5">
              <DlRow label="Mercato collegato">
                {marketLabel(asString(linked.linked_market_key))}
              </DlRow>
              <DlRow label="Relazione">
                {humanizeCode(asString(linked.relationship))}
              </DlRow>
              <DlRow label="Edge">{formatV3PctAlready(asNumber(linked.edge_pct))}</DlRow>
              <DlRow label="Vantaggio">
                {asNumber(linked.vantaggio_prob) != null
                  ? `${Number(linked.vantaggio_prob) > 0 ? '+' : ''}${formatV3Number(
                      Math.abs(Number(linked.vantaggio_prob)) <= 1
                        ? Number(linked.vantaggio_prob) * 100
                        : Number(linked.vantaggio_prob),
                    )} pp`
                  : '—'}
              </DlRow>
              <DlRow label="Rating">{formatV3Number(asNumber(linked.rating), 0)}</DlRow>
              <DlRow label="Gate">{asString(linked.gate_status) ?? '—'}</DlRow>
            </dl>
            {explanation.market_key === 'AWAY' &&
            asString(linked.linked_market_key) === 'X_TWO' ? (
              <p className="text-xs text-slate-600" data-testid="v3-x2-diagnostic-note">
                X2 è soltanto un contesto collegato diagnostico per il 2: non è un concorrente
                diretto nella famiglia MATCH_WINNER_FT.
              </p>
            ) : null}
            <p className="font-mono text-[10px] text-slate-400">
              {asString(linked.relationship)}
            </p>
          </>
        ) : (
          <p className="text-sm text-slate-600">Nessun contesto collegato per questo mercato.</p>
        )}
      </Section>

      {gatePassed ? (
        <Section title="6. Calcolo finale" testId="v3-section-final">
          <p className="text-sm font-medium text-slate-900">La qualità sconta il valore.</p>
          <ol className="list-decimal space-y-1 pl-5 font-mono text-[12px] leading-relaxed">
            {(formulaSteps.length
              ? formulaSteps
              : [
                  `Value score = ${formatV3Number(valueScore)}`,
                  `Qualità iniziale = ${formatV3Number(qualityStart)}`,
                  `Penalità probabilità = ${formatPenaltyPointsNegative(
                    asNumber(asRecord(penalties.probability_risk)?.penalty_points),
                  )}`,
                  `Penalità opposto = ${formatPenaltyPointsNegative(
                    asNumber(asRecord(penalties.opposite_market_pressure)?.penalty_points),
                  )}`,
                  `Penalità divergenza = ${formatPenaltyPointsNegative(
                    asNumber(asRecord(penalties.extreme_divergence)?.penalty_points),
                  )}`,
                  `Penalità famiglia = ${formatPenaltyPointsNegative(
                    asNumber(asRecord(penalties.family_ambiguity)?.penalty_points),
                  )}`,
                  `Penalità quota = ${formatPenaltyPointsNegative(
                    asNumber(asRecord(penalties.quote_quality)?.penalty_points),
                  )}`,
                  `Qualità finale = ${formatV3Number(qualityScore)}`,
                  `Raw score = Value × Qualità / 100`,
                  `Score finale = ROUND_HALF_UP(...)`,
                ]
            ).map((step, i) => (
              <li key={`${i}-${step}`}>{step}</li>
            ))}
          </ol>
          <p className="text-xs text-slate-500" data-testid="v3-no-geometric-mean">
            Formula V3: value × quality / 100 (nessuna media geometrica).
          </p>
        </Section>
      ) : null}

      <Section title="Diagnostica" testId="v3-section-diagnostics">
        <dl className="space-y-1.5 text-sm">
          <DlRow label="Risultato persistito">
            <span data-testid="v3-persisted-result">
              {asNumber(persisted.score) ??
                explanation.stored_result_display ??
                String(explanation.stored_result ?? '—')}
            </span>
          </DlRow>
          <DlRow label="Risultato audit">
            <span data-testid="v3-audit-result">
              {explanation.audit_result == null ? '—' : String(explanation.audit_result)}
            </span>
          </DlRow>
          <DlRow label="Delta">
            {explanation.consistency?.delta != null
              ? String(explanation.consistency.delta)
              : '—'}
          </DlRow>
          <DlRow label="Consistency">
            <span data-testid="v3-consistency">{explanation.consistency?.status ?? '—'}</span>
          </DlRow>
          <DlRow label="Arrotondamento">
            {explanation.rounding?.policy ?? '—'}
            {explanation.rounding?.precision != null
              ? ` · prec. ${explanation.rounding.precision}`
              : ''}
          </DlRow>
          <DlRow label="Famiglia (codice)">
            <span className="font-mono text-xs" data-testid="v3-family-code">
              {marketFamilyCode ?? '—'}
            </span>
          </DlRow>
          <DlRow label="candidate_version">
            <span data-testid="v3-candidate-version">{candidateVersion ?? '—'}</span>
          </DlRow>
          <DlRow label="formula_version">
            <span data-testid="v3-formula-version">{formulaVersion ?? '—'}</span>
          </DlRow>
          <DlRow label="audit_version">
            <span data-testid="v3-audit-version">{auditVersion ?? '—'}</span>
          </DlRow>
          <DlRow label="generated_at">
            <span data-testid="v3-generated-at">{generatedAt ?? '—'}</span>
          </DlRow>
          <DlRow label="source_snapshot_at">
            <span data-testid="v3-source-snapshot-at">{sourceSnapshotAt ?? '—'}</span>
          </DlRow>
          <DlRow label="pre_match_only">
            {yesNo(asBool(dataOrigin.pre_match_only) ?? true)}
          </DlRow>
          <DlRow label="historical_profile_used">
            {yesNo(
              asBool(dataOrigin.historical_profile_used) ??
                asBool(dep.historical_profile_used) ??
                false,
            )}
          </DlRow>
          <DlRow label="fixed_scales_used">
            {yesNo(asBool(dataOrigin.fixed_scales_used) ?? asBool(dep.fixed_scales_used) ?? true)}
          </DlRow>
          <DlRow label="current_operational_version">
            {yesNo(
              asBool(dataOrigin.current_operational_version) ??
                asBool(dep.current_operational_version) ??
                false,
            )}
          </DlRow>
          <DlRow label="parallel_candidate">
            {yesNo(asBool(dataOrigin.parallel_candidate) ?? true)}
          </DlRow>
        </dl>
        {sourcePathList.length > 0 ? (
          <ul className="mt-2 space-y-1 font-mono text-[10px] text-slate-500">
            {sourcePathList.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        ) : null}
        <p
          className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-2 text-xs text-amber-950"
          data-testid="v3-parallel-warning"
        >
          V3 è un candidato parallelo. Il punteggio non è ancora stato validato sullo storico e non
          sostituisce la V2.
        </p>
      </Section>
    </div>
  )
}
