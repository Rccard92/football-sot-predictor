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
  HOME_PT: '1 PT',
  DRAW_PT: 'X PT',
  AWAY_PT: '2 PT',
  ONE_X: '1X',
  X_TWO: 'X2',
  ONE_TWO: '12',
  OVER_1_5: 'Over 1.5',
  UNDER_1_5: 'Under 1.5',
  OVER_2_5: 'Over 2.5',
  UNDER_2_5: 'Under 2.5',
  OVER_3_5: 'Over 3.5',
  UNDER_3_5: 'Under 3.5',
  OVER_PT_0_5: 'Over PT 0.5',
  UNDER_PT_0_5: 'Under PT 0.5',
  OVER_PT_1_5: 'Over PT 1.5',
  UNDER_PT_1_5: 'Under PT 1.5',
}

const FAMILY_LABELS: Record<string, string> = {
  MATCH_WINNER_FT: 'Esito finale 1/X/2',
  GOALS_FT_2_5: 'Goal FT 2.5',
  DOUBLE_CHANCE: 'Doppia chance',
}

const HUMAN_CODE_LABELS: Record<string, string> = {
  passed: 'Attivato',
  failed_non_positive_edge: 'Edge non positivo',
  failed_non_positive_probability_advantage: 'Vantaggio non positivo',
  failed_multiple_non_positive_components: 'Nessun valore positivo',
  unsupported_market: 'Non supportato',
  unavailable_inputs: 'Input mancanti',
  normalized_1x2_market: 'Quota Betfair 1X2',
  linked_double_chance_away_cover: 'X2 collegato al segno 2',
  linked_double_chance_home_cover: '1X collegato al segno 1',
  linked_double_chance_anti_draw: '12 collegato al pareggio',
  linked_match_winner_away: 'Segno 2 collegato',
  direct_goals_competitor: 'Concorrente goal diretto',
  leader_clear: 'Leader netto',
  leader_close: 'Leader con margine ridotto',
  not_leader: 'Non leader della famiglia',
  insufficient_family_comparison: 'Confronto famiglia insufficiente',
  AWAY_to_X_TWO: '2 → X2 (contesto collegato)',
  HOME_to_ONE_X: '1 → 1X (contesto collegato)',
  MATCH_WINNER_FT: 'Esito finale 1/X/2',
  GOALS_FT_2_5: 'Goal FT 2.5',
  DOUBLE_CHANCE: 'Doppia chance',
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

function gateStatusHuman(status: string | null): string {
  if (!status) return '—'
  return humanizeCode(status)
}

function familyLabelHuman(code: string | null, label: string | null): string {
  if (label) return label
  if (!code) return '—'
  return FAMILY_LABELS[code] || humanizeCode(code)
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

function penaltyMainDatum(key: string, pen: UnknownRecord, opposite: UnknownRecord): string | null {
  const raw = asRecord(pen.raw_inputs) ?? {}
  if (key === 'opposite_market_pressure') {
    const oppKey = asString(opposite.opposite_market_key) ?? asString(raw.opposite_market_key)
    const fair =
      asNumber(opposite.opposite_fair_probability) ?? asNumber(raw.opposite_fair_probability)
    const parts: string[] = []
    if (oppKey) parts.push(`Mercato opposto: ${marketLabel(oppKey)}`)
    if (fair != null) parts.push(`Probabilità fair: ${formatV3PctFromFraction(fair)}`)
    return parts.length ? parts.join(' · ') : null
  }
  if (key === 'probability_risk') {
    const p =
      asNumber(raw.probability_cecchino_pct) ??
      (asNumber(raw.probability_cecchino) != null
        ? asNumber(raw.probability_cecchino)! * 100
        : null)
    if (p != null) return `Probabilità Cecchino: ${formatV3PctAlready(p)}`
  }
  if (key === 'extreme_divergence') {
    const edge = asNumber(raw.edge_pct)
    if (edge != null) return `Edge: ${formatV3PctAlready(edge)}`
  }
  if (key === 'family_ambiguity') {
    const gap = asNumber(raw.edge_gap_or_deficit) ?? asNumber(raw.edge_diff_from_leader)
    if (gap != null) return `Margine Edge: ${formatV3Number(gap)}`
  }
  if (key === 'quote_quality') {
    const pt = asString(raw.performance_type)
    if (pt) return `Tipo quota: ${pt}`
  }
  const first = Object.entries(raw).find(([, v]) => v != null)
  if (first) return `${first[0]}: ${String(first[1])}`
  return null
}

function thresholdHumanLines(key: string, pen: UnknownRecord): string[] {
  const start = asNumber(pen.threshold_start)
  const full = asNumber(pen.threshold_full)
  const asPct = (n: number) => formatV3Number(n <= 1 && n > 0 ? n * 100 : n)
  const lines: string[] = []
  if (key === 'opposite_market_pressure') {
    if (start != null) lines.push(`La penalità inizia sopra il ${asPct(start)}%`)
    if (full != null) lines.push(`La penalità massima si applica al ${asPct(full)}% o più`)
    return lines
  }
  if (start != null) lines.push(`La penalità inizia sotto il ${asPct(start)}%`)
  if (full != null) lines.push(`La penalità massima si applica al ${asPct(full)}% o meno`)
  return lines
}

function isPenaltyApplied(pen: UnknownRecord | null): boolean {
  if (!pen) return false
  if (pen.applied === true) return true
  const points = asNumber(pen.penalty_points)
  return points != null && points > 0
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

  const marketFamilyLabel = familyLabelHuman(
    asString(explRec.market_family) ??
      asString(family.market_family) ??
      asString(input.market_family),
    asString(explRec.market_family_label) ?? asString(family.market_family_label),
  )
  const marketFamilyCode =
    asString(explRec.market_family) ??
    asString(family.market_family) ??
    asString(input.market_family)

  const readingShort = asString(explanation.reading_short)
  const readingDetailed =
    asString(explanation.reading_detailed) ?? asString(explanation.simple_explanation)
  const readingsIdentical =
    Boolean(readingShort && readingDetailed && readingShort === readingDetailed)
  const primaryReading = readingsIdentical
    ? readingShort
    : readingDetailed || readingShort || null

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
    const leaderKey = asString(family.leader_market_key)
    const selectedLabel =
      marketLabel(explanation.market_key) || explanation.market_label || 'Il mercato analizzato'
    if (selectedIsLeader === true) {
      return `Il segno ${selectedLabel} ha l’Edge più alto della famiglia${
        gap != null ? ` con ${formatV3Number(gap)} punti di vantaggio.` : '.'
      }`
    }
    if (selectedIsLeader === false) {
      return `Un altro mercato${leaderKey ? ` (${marketLabel(leaderKey)})` : ''} della famiglia presenta Edge maggiore.`
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

  const appliedPenalties = PENALTY_ORDER.map((key) => {
    const pen = asRecord(penalties[key])
    return pen && isPenaltyApplied(pen) ? { key, pen } : null
  }).filter(Boolean) as { key: (typeof PENALTY_ORDER)[number]; pen: UnknownRecord }[]

  const nonAppliedPenalties = PENALTY_ORDER.map((key) => {
    const pen = asRecord(penalties[key])
    return pen && !isPenaltyApplied(pen) ? { key, pen } : null
  }).filter(Boolean) as { key: (typeof PENALTY_ORDER)[number]; pen: UnknownRecord }[]

  const compactFormula =
    valueScore != null && qualityScore != null
      ? `${formatV3Number(valueScore)} × ${formatV3Number(qualityScore)}% = ${formatV3Number(
          (valueScore * qualityScore) / 100,
        )} → ${score ?? '—'}`
      : null

  return (
    <div className="space-y-4" data-testid="purchasability-v3-audit-view">
      {/* A. Risultato */}
      <Section title="Risultato" testId="v3-section-result">
        {derivedQuote ? (
          <div
            className="rounded-md border border-violet-200 bg-violet-50 px-2.5 py-2 text-sm text-violet-950"
            data-testid="v3-derived-banner"
          >
            <p className="font-semibold" data-testid="v3-badge-derived">
              Quota derivata — solo analisi
            </p>
            <p className="mt-1 text-xs">
              Non rappresenta una quota Betfair realmente rilevata.
            </p>
          </div>
        ) : null}
        <dl className="space-y-1.5 text-sm">
          <DlRow label="Mercato">{explanation.market_label || explanation.market_key}</DlRow>
          <DlRow label="Famiglia">
            <span data-testid="v3-family-label">{marketFamilyLabel}</span>
          </DlRow>
          <DlRow label="Acquistabilità">
            <span data-testid="v3-score-final">
              {gateFailed && score == null
                ? 'Indice non attivato'
                : score != null && klass
                  ? `${score} — ${klass}`
                  : score ?? '—'}
            </span>
          </DlRow>
          {klass && !(gateFailed && score == null) ? (
            <DlRow label="Classe">{klass}</DlRow>
          ) : null}
        </dl>
        {primaryReading ? (
          <p
            className="mt-1 rounded-md bg-slate-50 px-2.5 py-2 text-sm leading-relaxed text-slate-800"
            data-testid="v3-reading-primary"
          >
            {primaryReading}
          </p>
        ) : null}
      </Section>

      {/* B. Esiste valore? */}
      <Section title="Esiste valore?" testId="v3-section-gate">
        <dl className="space-y-1.5">
          <DlRow label="Edge">{formatV3PctAlready(edgePct)}</DlRow>
          <DlRow label="Vantaggio probabilistico">
            {vantFraction != null
              ? `${vantFraction > 0 ? '+' : ''}${formatV3Number(vantFraction * 100)} pp`
              : '—'}
          </DlRow>
          <DlRow label="Indice">
            <span
              className={gatePassed ? 'text-emerald-800' : 'text-amber-900'}
              data-testid="v3-gate-status-human"
            >
              {gatePassed ? 'Attivato' : 'Indice non attivato'}
            </span>
          </DlRow>
        </dl>
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
            className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-2 text-sm text-amber-950"
            data-testid="v3-gate-not-activated"
          >
            Edge e vantaggio probabilistico non sono entrambi positivi.
          </p>
        ) : null}
      </Section>

      {/* C. Valore della quota */}
      {gatePassed ? (
        <Section title="Valore della quota" testId="v3-section-value">
          <dl className="space-y-1.5">
            <DlRow label="Quota Book">{formatV3Number(asNumber(input.quota_book))}</DlRow>
            <DlRow label="Quota Cecchino">
              {formatV3Number(asNumber(input.quota_cecchino))}
            </DlRow>
            <DlRow label="Probabilità Book fair">
              {formatV3PctFromFraction(asNumber(input.fair_book_probability))}
            </DlRow>
            <DlRow label="Probabilità Cecchino">
              {asNumber(input.probability_cecchino_pct) != null
                ? formatV3PctAlready(asNumber(input.probability_cecchino_pct))
                : formatV3PctFromFraction(asNumber(input.probability_cecchino))}
            </DlRow>
            <DlRow label="Value score">
              <span data-testid="v3-value-score">{formatV3Number(valueScore)}</span>
            </DlRow>
          </dl>
          <p className="text-xs text-slate-600" data-testid="v3-value-score-note">
            Il Value score misura soltanto la forza dell’Edge.
          </p>
        </Section>
      ) : null}

      {/* D. Cosa riduce il punteggio? */}
      {gatePassed ? (
        <Section title="Cosa riduce il punteggio?" testId="v3-section-penalties">
          {appliedPenalties.length === 0 ? (
            <p className="text-sm text-slate-600">Nessuna penalità applicata.</p>
          ) : (
            <div className="space-y-2">
              {appliedPenalties.map(({ key, pen }) => {
                const points =
                  key === 'opposite_market_pressure'
                    ? (oppPenalty ?? asNumber(pen.penalty_points))
                    : asNumber(pen.penalty_points)
                const mainDatum = penaltyMainDatum(key, pen, opposite)
                return (
                  <div
                    key={key}
                    className="rounded-md border border-slate-200 bg-slate-50/80 px-2.5 py-2"
                    data-testid={`v3-penalty-${key}`}
                  >
                    <p className="text-sm font-semibold text-slate-900">
                      {asString(pen.label) || PENALTY_TITLES[key] || key}
                    </p>
                    {asString(pen.explanation) ? (
                      <p className="mt-1 text-xs text-slate-700">{asString(pen.explanation)}</p>
                    ) : null}
                    {mainDatum ? (
                      <p className="mt-1 text-xs text-slate-600">{mainDatum}</p>
                    ) : null}
                    {key === 'opposite_market_pressure' ? (
                      <dl className="mt-2 space-y-1 text-xs" data-testid="v3-opposite-integrated">
                        <DlRow label="Mercato opposto">
                          {marketLabel(asString(opposite.opposite_market_key))}
                        </DlRow>
                        <DlRow label="Probabilità fair">
                          {formatV3PctFromFraction(asNumber(opposite.opposite_fair_probability))}
                        </DlRow>
                        <DlRow label="Penalità">
                          <span
                            className="font-semibold tabular-nums text-rose-700"
                            data-testid={`v3-penalty-points-${key}`}
                          >
                            {formatPenaltyPointsNegative(points)}
                          </span>
                        </DlRow>
                      </dl>
                    ) : (
                      <p className="mt-2 text-sm font-semibold tabular-nums text-rose-700">
                        <span data-testid={`v3-penalty-points-${key}`}>
                          {formatPenaltyPointsNegative(points)}
                        </span>{' '}
                        punti
                      </p>
                    )}
                    {key === 'quote_quality' && derivedQuote ? (
                      <p
                        className="mt-2 rounded-md border border-violet-200 bg-violet-50 px-2 py-1.5 text-xs text-violet-950"
                        data-testid="v3-derived-quote-note"
                      >
                        Non rappresenta una quota Betfair realmente rilevata.
                      </p>
                    ) : null}
                  </div>
                )
              })}
            </div>
          )}
          <dl className="mt-2 space-y-1 rounded-md border border-slate-200 px-2.5 py-2 text-sm">
            <DlRow label="Penalità totali">
              <span className="font-semibold text-rose-700" data-testid="v3-total-penalty">
                {formatPenaltyPointsNegative(totalPenalty)}
              </span>
            </DlRow>
            <DlRow label="Qualità finale">
              <span data-testid="v3-quality-final">{formatV3Number(qualityScore)}</span>
            </DlRow>
          </dl>
        </Section>
      ) : null}

      {/* E. Confronto nella famiglia */}
      {gatePassed ? (
        <Section title="Confronto nella famiglia" testId="v3-section-family">
          {marketRows.length > 0 ? (
            <div className="overflow-x-auto">
              <table
                className="w-full min-w-[360px] border-collapse text-left text-xs"
                data-testid="v3-family-table"
              >
                <thead className="bg-slate-100 text-slate-600">
                  <tr>
                    <th className="px-2 py-1.5">Mercato</th>
                    <th className="px-2 py-1.5">Edge</th>
                    <th className="px-2 py-1.5">Stato</th>
                    <th className="px-2 py-1.5">Posizione</th>
                  </tr>
                </thead>
                <tbody>
                  {marketRows.map((row) => {
                    const mk = String(row.market_key || '')
                    const isSelected = Boolean(row.is_selected)
                    const isLeader = Boolean(row.is_leader)
                    const edge = asNumber(row.edge_pct)
                    const statusLabel = isLeader
                      ? 'Leader'
                      : row.gate_passed
                        ? 'Attivato'
                        : gateStatusHuman(asString(row.gate_status))
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
                        </td>
                        <td
                          className="px-2 py-1.5 tabular-nums"
                          data-testid={`v3-family-edge-${mk}`}
                        >
                          {edge != null ? formatV3PctAlready(edge) : '—'}
                        </td>
                        <td className="px-2 py-1.5">
                          {isLeader ? (
                            <span data-testid={`v3-family-leader-badge-${mk}`}>{statusLabel}</span>
                          ) : (
                            statusLabel
                          )}
                        </td>
                        <td className="px-2 py-1.5 tabular-nums">
                          {row.rank_by_edge != null ? String(row.rank_by_edge) : '—'}
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
          {familyReading ? (
            <p className="text-sm text-slate-700" data-testid="v3-family-reading">
              {familyReading}
            </p>
          ) : null}
        </Section>
      ) : null}

      {/* F. Risultato finale */}
      {gatePassed ? (
        <Section title="Risultato finale" testId="v3-section-final">
          <dl className="space-y-1.5 text-sm">
            <DlRow label="Valore iniziale">
              <span data-testid="v3-quality-start">{formatV3Number(qualityStart)}</span>
            </DlRow>
            <DlRow label="Penalità totali">
              {formatPenaltyPointsNegative(totalPenalty)}
            </DlRow>
            <DlRow label="Qualità finale">{formatV3Number(qualityScore)}</DlRow>
            <DlRow label="Acquistabilità">{score ?? '—'}</DlRow>
          </dl>
          {compactFormula ? (
            <p
              className="rounded-md bg-slate-50 px-2.5 py-2 font-mono text-sm text-slate-900"
              data-testid="v3-final-formula-compact"
            >
              {compactFormula}
            </p>
          ) : null}
          <p className="text-xs text-slate-500" data-testid="v3-no-geometric-mean">
            Formula: value × quality / 100 (nessuna media geometrica).
          </p>
        </Section>
      ) : null}

      {/* Dettagli tecnici */}
      <details
        className="rounded-lg border border-slate-200"
        data-testid="v3-technical-details"
      >
        <summary
          className="cursor-pointer px-3 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500 outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
          data-testid="v3-technical-details-summary"
        >
          Dettagli tecnici e audit
        </summary>
        <div className="space-y-4 border-t border-slate-100 px-3 py-3" data-testid="v3-section-diagnostics">
          <p className="text-xs text-amber-800" data-testid="v3-validation-note">
            Validazione storica completa da eseguire.
          </p>
          <p className="text-xs text-slate-600" data-testid="v3-parallel-warning">
            Formula: {formulaVersion ?? '—'} — validazione storica completa da eseguire.
          </p>
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
            <DlRow label="Gate (codice)">
              <span className="font-mono text-xs">{gateStatus ?? '—'}</span>
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
              {yesNo(asBool(dataOrigin.parallel_candidate) ?? asBool(dep.parallel_candidate))}
            </DlRow>
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
            <p className="mt-1 font-mono text-[11px] text-slate-600">
              {asString(value.value_formula) ||
                'value_score = clamp(edge_pct / 50 × 100, 0, 100)'}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Probabilità Book grezza:{' '}
              {formatV3PctFromFraction(asNumber(input.raw_book_probability))}
            </p>
          </div>

          {nonAppliedPenalties.length > 0 ? (
            <div data-testid="v3-penalties-not-applied">
              <p className="text-[10px] font-semibold uppercase text-slate-500">
                Penalità non applicate
              </p>
              <div className="mt-2 space-y-2">
                {nonAppliedPenalties.map(({ key, pen }) => (
                  <div
                    key={key}
                    className="rounded-md border border-slate-100 bg-slate-50 px-2.5 py-2 text-xs"
                    data-testid={`v3-penalty-not-applied-${key}`}
                  >
                    <p className="font-semibold text-slate-800">
                      {asString(pen.label) || PENALTY_TITLES[key] || key}
                    </p>
                    {thresholdHumanLines(key, pen).map((line) => (
                      <p key={line} className="mt-0.5 text-slate-600">
                        {line}
                      </p>
                    ))}
                    <p className="mt-1 text-slate-500">
                      Severity: {formatV3Number(asNumber(pen.severity))} · Max:{' '}
                      {formatV3Number(asNumber(pen.max_points))}
                    </p>
                    <pre className="mt-1 overflow-x-auto font-mono text-[10px] text-slate-500">
                      {JSON.stringify(asRecord(pen.raw_inputs) ?? {}, null, 0)}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {appliedPenalties.length > 0 ? (
            <div data-testid="v3-penalties-tech-applied">
              <p className="text-[10px] font-semibold uppercase text-slate-500">
                Dettaglio tecnico penalità applicate
              </p>
              <div className="mt-2 space-y-2">
                {appliedPenalties.map(({ key, pen }) => (
                  <div key={key} className="rounded border border-slate-100 px-2 py-2 text-xs">
                    <p className="font-semibold">{PENALTY_TITLES[key] || key}</p>
                    {thresholdHumanLines(key, pen).map((line) => (
                      <p key={line} className="mt-0.5 text-slate-600">
                        {line}
                      </p>
                    ))}
                    <p className="mt-1 text-slate-500">
                      Severity: {formatV3Number(asNumber(pen.severity))} · Max:{' '}
                      {formatV3Number(asNumber(pen.max_points))}
                    </p>
                    <pre className="mt-1 overflow-x-auto font-mono text-[10px] text-slate-500">
                      {JSON.stringify(asRecord(pen.raw_inputs) ?? {}, null, 0)}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div data-testid="v3-raw-inputs-details">
            <p className="text-[10px] font-semibold uppercase text-slate-500">Input grezzi</p>
            <div className="mt-1 overflow-x-auto">
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
          </div>

          <div data-testid="v3-formula-steps-tech">
            <p className="text-[10px] font-semibold uppercase text-slate-500">Formula steps</p>
            <ol className="mt-1 list-decimal space-y-1 pl-5 font-mono text-[11px] leading-relaxed">
              {(formulaSteps.length
                ? formulaSteps
                : [
                    `Value score = ${formatV3Number(valueScore)}`,
                    `Qualità finale = ${formatV3Number(qualityScore)}`,
                    `Raw score = Value × Qualità / 100`,
                    `Score finale = ROUND_HALF_UP(...)`,
                  ]
              ).map((step, i) => (
                <li key={`${i}-${step}`}>{step}</li>
              ))}
            </ol>
          </div>

          <div data-testid="v3-section-linked">
            <p className="text-[10px] font-semibold uppercase text-slate-500">
              Contesto collegato
            </p>
            <p className="mt-1 text-xs text-slate-600" data-testid="v3-linked-no-score-note">
              Questo mercato non modifica il punteggio.
            </p>
            {linked ? (
              <dl className="mt-2 space-y-1.5 text-sm">
                <DlRow label="Mercato collegato">
                  {marketLabel(asString(linked.linked_market_key))}
                </DlRow>
                <DlRow label="Relazione">
                  {humanizeCode(asString(linked.relationship))}
                </DlRow>
                <DlRow label="Relazione (codice)">
                  <span className="font-mono text-[10px]">{asString(linked.relationship)}</span>
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
            ) : (
              <p className="mt-1 text-sm text-slate-600">
                Nessun contesto collegato per questo mercato.
              </p>
            )}
            {explanation.market_key === 'AWAY' &&
            linked &&
            asString(linked.linked_market_key) === 'X_TWO' ? (
              <p className="mt-2 text-xs text-slate-600" data-testid="v3-x2-diagnostic-note">
                X2 è soltanto un contesto collegato diagnostico per il 2: non è un concorrente
                diretto nella famiglia MATCH_WINNER_FT.
              </p>
            ) : null}
          </div>

          {sourcePathList.length > 0 ? (
            <div>
              <p className="text-[10px] font-semibold uppercase text-slate-500">Source paths</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 font-mono text-[10px] text-slate-600">
                {sourcePathList.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {derivedQuote ? (
            <dl className="space-y-1 text-xs text-slate-600">
              <DlRow label="performance_type">
                {asString(input.performance_type) ?? '—'}
              </DlRow>
              <DlRow label="quote_source">{asString(input.quote_source) ?? '—'}</DlRow>
              <DlRow label="not_real_book_quote">
                {yesNo(asBool(input.not_real_book_quote))}
              </DlRow>
              <DlRow label="diagnostic_only">{yesNo(asBool(input.diagnostic_only))}</DlRow>
            </dl>
          ) : null}

          {asNumber(opposite.opposite_raw_probability) != null ? (
            <p className="text-xs text-slate-500">
              Probabilità grezza opposta:{' '}
              {formatV3PctFromFraction(asNumber(opposite.opposite_raw_probability))}
            </p>
          ) : null}
        </div>
      </details>
    </div>
  )
}
