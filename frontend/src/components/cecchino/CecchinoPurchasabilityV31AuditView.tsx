import type { CecchinoKpiExplanation } from '../../lib/cecchinoTodayApi'
import type { CecchinoPurchasabilityV31ExplanationSection } from '../../lib/cecchinoTodayApi'
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

function yesNo(v: boolean | null | undefined): string {
  if (v === true) return 'Sì'
  if (v === false) return 'No'
  return '—'
}

const SECTION_TITLES: Record<string, string> = {
  final_state: 'Stato finale',
  gate: 'Verifica valore',
  quote_quality: 'Qualità della quota',
  fair_book: 'Probabilità fair del Book',
  theoretical_value: 'Valore teorico',
  penalties: 'Penalità applicate',
  family_ambiguity: 'Ambiguità nella famiglia',
  historical_reliability: 'Affidabilità storica',
  final_calculation: 'Calcolo finale',
  comparison_with_v3: 'Confronto con V3',
}

const V31_GATE_REASON_LABELS: Record<string, string> = {
  no_positive_value: 'Nessun valore positivo',
  rating_below_50: 'Rating sotto 50',
}

const V31_NON_CALCULABLE_REASON_LABELS: Record<string, string> = {
  missing_quote: 'Quota mancante',
  derived_quote: 'Quota derivata',
  incomplete_set_book: 'Set Book incompleto',
  missing_cecchino_formula: 'Formula Cecchino mancante',
  insufficient_history: 'Storico insufficiente',
  complement_unavailable: 'Complemento non disponibile',
}

function humanizeReasonCode(
  status: string | null,
  code: string | null,
): string {
  if (!code) return '—'
  if (status === 'gate_failed') {
    return V31_GATE_REASON_LABELS[code] ?? code
  }
  if (status === 'non_calculable') {
    return V31_NON_CALCULABLE_REASON_LABELS[code] ?? code
  }
  return code
}

function DlRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
      <dt className="shrink-0 text-slate-500 sm:w-48">{label}</dt>
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

function getSectionsArray(
  sections: CecchinoPurchasabilityV31ExplanationSection[] | Record<string, CecchinoPurchasabilityV31ExplanationSection> | undefined,
): CecchinoPurchasabilityV31ExplanationSection[] {
  if (!sections) return []
  if (Array.isArray(sections)) return sections
  return Object.values(sections)
}

export function CecchinoPurchasabilityV31AuditView({ explanation }: Props) {
  const explRec = explanation as UnknownRecord
  const v31Explanation = asRecord(explanation.v31_explanation) ?? asRecord(explanation.explanation) ?? {}

  const sectionsRaw = v31Explanation.sections as
    | CecchinoPurchasabilityV31ExplanationSection[]
    | Record<string, CecchinoPurchasabilityV31ExplanationSection>
    | undefined
  const sections = getSectionsArray(sectionsRaw)

  const finalState = asRecord(v31Explanation.final_state) ?? asRecord(explanation.final_state) ?? {}
  const gate = asRecord(v31Explanation.gate) ?? asRecord(explanation.gate) ?? {}
  const quoteQuality = asRecord(v31Explanation.quote_quality) ?? asRecord(explanation.quote_quality) ?? {}
  const fairBook = asRecord(v31Explanation.fair_book) ?? asRecord(explanation.fair_book) ?? {}
  const theoreticalValue = asRecord(v31Explanation.theoretical_value) ?? asRecord(explanation.theoretical_value) ?? {}
  const penalties = asRecord(v31Explanation.penalties) ?? asRecord(explanation.penalties) ?? {}
  const familyAmbiguity = asRecord(v31Explanation.family_ambiguity) ?? asRecord(explanation.family_ambiguity) ?? {}
  const historicalReliability = asRecord(v31Explanation.historical_reliability) ?? asRecord(explanation.historical_reliability) ?? {}
  const finalCalculation = asRecord(v31Explanation.final_calculation) ?? asRecord(explanation.final_calculation) ?? {}
  const comparisonWithV3 = asRecord(v31Explanation.comparison_with_v3) ?? asRecord(explanation.comparison_with_v3) ?? {}
  const persisted = asRecord(explanation.persisted_result) ?? {}
  const input = asRecord(explanation.input) ?? asRecord(v31Explanation.input) ?? {}
  const dataOrigin = asRecord(explanation.data_origin) ?? {}

  const status = asString(finalState.status) ?? asString(persisted.status) ?? null
  const score = asNumber(finalState.score) ?? asNumber(persisted.score) ?? asNumber(explanation.stored_result)
  const klass = asString(finalState.class) ?? asString(persisted.class)
  const reasonCode = asString(finalState.reason_code) ?? asString(persisted.reason_code)
  const reason = asString(finalState.reason) ?? asString(persisted.reason)

  const gatePassed = asBool(gate.gate_passed) ?? asString(gate.gate_status) === 'passed'
  const gateReasonCode = asString(gate.reason_code)
  const gateReason = asString(gate.reason)

  const theoreticalRaw = asNumber(theoreticalValue.theoretical_raw) ?? asNumber(finalCalculation.theoretical_raw)
  const historicalFactor = asNumber(historicalReliability.factor) ?? asNumber(finalCalculation.historical_factor)

  const candidateVersion = asString(explRec.candidate_version) ?? asString(input.candidate_version)
  const formulaVersion = explanation.formula_version ?? asString(v31Explanation.formula_version)
  const auditVersion = asString(explRec.audit_version)
  const generatedAt = asString(explRec.generated_at) ?? asString(dataOrigin.generated_at)
  const sourceSnapshotAt = asString(explRec.source_snapshot_at) ?? asString(dataOrigin.source_snapshot_at)

  const isNonCalculable = status === 'non_calculable'
  const isGateFailed = status === 'gate_failed' || (!isNonCalculable && !gatePassed && score == null)
  const hasScore = status === 'score' && score != null

  const v3Score = asNumber(comparisonWithV3.v3_score)
  const v31Score = asNumber(comparisonWithV3.v31_score) ?? score
  const delta = asNumber(comparisonWithV3.delta)
  const direction = asString(comparisonWithV3.direction)

  const penaltiesApplied = penalties.penalties_applied as Array<{
    key?: string | null
    label?: string | null
    points?: number | null
  }> | undefined
  const totalPenalty = asNumber(penalties.total_penalty)

  return (
    <div className="space-y-4" data-testid="purchasability-v31-audit-view">
      {/* Risultato */}
      <Section title="Risultato" testId="v31-section-result">
        <dl className="space-y-1.5 text-sm">
          <DlRow label="Mercato">{explanation.market_label || explanation.market_key}</DlRow>
          <DlRow label="Stato">
            <span
              className={`${
                hasScore ? 'text-emerald-800' : isGateFailed ? 'text-amber-800' : 'text-slate-600'
              }`}
              data-testid="v31-status"
            >
              {hasScore
                ? 'Score calcolato'
                : isGateFailed
                  ? 'Non attivato'
                  : isNonCalculable
                    ? 'Non calcolabile'
                    : '—'}
            </span>
          </DlRow>
          <DlRow label="Acquistabilità V3.1">
            <span data-testid="v31-score-final">
              {hasScore && score != null
                ? `${score}${klass ? ` — ${klass}` : ''}`
                : isGateFailed
                  ? 'Indice non attivato'
                  : isNonCalculable
                    ? 'Non calcolabile'
                    : '—'}
            </span>
          </DlRow>
          {(isGateFailed || isNonCalculable) && (reasonCode || reason) ? (
            <DlRow label="Motivo">
              <span data-testid="v31-reason">
                {humanizeReasonCode(status, reasonCode) || reason || '—'}
              </span>
            </DlRow>
          ) : null}
        </dl>
      </Section>

      {/* Gate */}
      <Section title="Esiste valore?" testId="v31-section-gate">
        <dl className="space-y-1.5">
          <DlRow label="Gate">
            <span
              className={gatePassed ? 'text-emerald-800' : 'text-amber-900'}
              data-testid="v31-gate-status"
            >
              {gatePassed ? 'Attivato' : 'Non attivato'}
            </span>
          </DlRow>
          {!gatePassed && (gateReasonCode || gateReason) ? (
            <DlRow label="Motivo gate">
              <span data-testid="v31-gate-reason">
                {humanizeReasonCode('gate_failed', gateReasonCode) || gateReason}
              </span>
            </DlRow>
          ) : null}
        </dl>
      </Section>

      {/* Qualità quota */}
      {asString(quoteQuality.status) || asString(quoteQuality.performance_type) ? (
        <Section title="Qualità della quota" testId="v31-section-quote-quality">
          <dl className="space-y-1.5">
            <DlRow label="Stato">{asString(quoteQuality.status) ?? '—'}</DlRow>
            <DlRow label="Tipo performance">{asString(quoteQuality.performance_type) ?? '—'}</DlRow>
            {asString(quoteQuality.reason) ? (
              <DlRow label="Nota">{asString(quoteQuality.reason)}</DlRow>
            ) : null}
          </dl>
        </Section>
      ) : null}

      {/* Fair Book */}
      {asNumber(fairBook.fair_book_probability) != null || asNumber(fairBook.quota_book) != null ? (
        <Section title="Probabilità fair del Book" testId="v31-section-fair-book">
          <dl className="space-y-1.5">
            <DlRow label="Quota Book">{formatV3Number(asNumber(fairBook.quota_book))}</DlRow>
            <DlRow label="Probabilità fair">
              {formatV3PctFromFraction(asNumber(fairBook.fair_book_probability))}
            </DlRow>
            {asNumber(fairBook.margin_pct) != null ? (
              <DlRow label="Margine">{formatV3PctAlready(asNumber(fairBook.margin_pct))}</DlRow>
            ) : null}
          </dl>
        </Section>
      ) : null}

      {/* Valore teorico */}
      {gatePassed && theoreticalRaw != null ? (
        <Section title="Valore teorico" testId="v31-section-theoretical">
          <dl className="space-y-1.5">
            <DlRow label="Edge">{formatV3PctAlready(asNumber(theoreticalValue.edge_pct) ?? asNumber(input.edge_pct))}</DlRow>
            <DlRow label="Valore teorico grezzo">
              <span data-testid="v31-theoretical-raw">{formatV3Number(theoreticalRaw)}</span>
            </DlRow>
          </dl>
        </Section>
      ) : null}

      {/* Penalità */}
      {gatePassed && penaltiesApplied && penaltiesApplied.length > 0 ? (
        <Section title="Penalità applicate" testId="v31-section-penalties">
          <div className="space-y-2">
            {penaltiesApplied.map((pen, idx) => (
              <div
                key={pen.key ?? idx}
                className="rounded-md border border-slate-200 bg-slate-50/80 px-2.5 py-2"
                data-testid={`v31-penalty-${pen.key ?? idx}`}
              >
                <p className="text-sm font-semibold text-slate-900">
                  {pen.label ?? pen.key ?? 'Penalità'}
                </p>
                <p className="mt-1 text-sm font-semibold tabular-nums text-rose-700">
                  {formatPenaltyPointsNegative(pen.points)} punti
                </p>
              </div>
            ))}
          </div>
          <dl className="mt-2 space-y-1 rounded-md border border-slate-200 px-2.5 py-2 text-sm">
            <DlRow label="Penalità totali">
              <span className="font-semibold text-rose-700" data-testid="v31-total-penalty">
                {formatPenaltyPointsNegative(totalPenalty)}
              </span>
            </DlRow>
          </dl>
        </Section>
      ) : gatePassed ? (
        <Section title="Penalità applicate" testId="v31-section-penalties">
          <p className="text-sm text-slate-600">Nessuna penalità applicata.</p>
        </Section>
      ) : null}

      {/* Ambiguità famiglia */}
      {gatePassed && (asBool(familyAmbiguity.is_leader) != null || asString(familyAmbiguity.status)) ? (
        <Section title="Ambiguità nella famiglia" testId="v31-section-family-ambiguity">
          <dl className="space-y-1.5">
            <DlRow label="È leader">{yesNo(asBool(familyAmbiguity.is_leader))}</DlRow>
            {asString(familyAmbiguity.leader_market_key) ? (
              <DlRow label="Mercato leader">{asString(familyAmbiguity.leader_market_key)}</DlRow>
            ) : null}
            {asNumber(familyAmbiguity.gap_from_leader) != null ? (
              <DlRow label="Margine dal leader">
                {formatV3Number(asNumber(familyAmbiguity.gap_from_leader))}
              </DlRow>
            ) : null}
          </dl>
        </Section>
      ) : null}

      {/* Affidabilità storica */}
      {gatePassed && (historicalFactor != null || asNumber(historicalReliability.score) != null) ? (
        <Section title="Affidabilità storica" testId="v31-section-historical">
          <dl className="space-y-1.5">
            <DlRow label="Fattore storico">
              <span data-testid="v31-historical-factor">
                {formatV3Number(historicalFactor)}
              </span>
            </DlRow>
            {asNumber(historicalReliability.score) != null ? (
              <DlRow label="Score affidabilità">{formatV3Number(asNumber(historicalReliability.score), 0)}</DlRow>
            ) : null}
            {asString(historicalReliability.class) ? (
              <DlRow label="Classe">{asString(historicalReliability.class)}</DlRow>
            ) : null}
            {asNumber(historicalReliability.sample_size) != null ? (
              <DlRow label="Campione">{asNumber(historicalReliability.sample_size)} casi</DlRow>
            ) : null}
          </dl>
        </Section>
      ) : null}

      {/* Calcolo finale */}
      {gatePassed && score != null ? (
        <Section title="Calcolo finale" testId="v31-section-final">
          <dl className="space-y-1.5 text-sm">
            <DlRow label="Valore teorico grezzo">{formatV3Number(theoreticalRaw)}</DlRow>
            <DlRow label="Fattore storico">{formatV3Number(historicalFactor)}</DlRow>
            <DlRow label="Risultato grezzo">
              <span data-testid="v31-raw-result">
                {formatV3Number(asNumber(finalCalculation.raw_result))}
              </span>
            </DlRow>
            <DlRow label="Arrotondamento">{asString(finalCalculation.rounding) ?? 'ROUND_HALF_UP'}</DlRow>
            <DlRow label="Score finale">
              <span className="font-semibold" data-testid="v31-final-score">{score}</span>
            </DlRow>
          </dl>
          <p
            className="mt-2 rounded-md bg-slate-50 px-2.5 py-2 font-mono text-sm text-slate-900"
            data-testid="v31-final-formula"
          >
            {formatV3Number(theoreticalRaw)} × {formatV3Number(historicalFactor)} = {formatV3Number(asNumber(finalCalculation.raw_result))} → ROUND_HALF_UP = {score}
          </p>
        </Section>
      ) : null}

      {/* Confronto con V3 */}
      {(v3Score != null || v31Score != null) ? (
        <Section title="Confronto con V3" testId="v31-section-comparison">
          <dl className="space-y-1.5">
            <DlRow label="Score V3">
              <span data-testid="v31-comparison-v3-score">{v3Score ?? '—'}</span>
            </DlRow>
            <DlRow label="Score V3.1">
              <span data-testid="v31-comparison-v31-score">{v31Score ?? '—'}</span>
            </DlRow>
            {delta != null ? (
              <DlRow label="Delta">
                <span
                  className={`font-semibold ${
                    delta > 0 ? 'text-emerald-700' : delta < 0 ? 'text-rose-700' : 'text-slate-600'
                  }`}
                  data-testid="v31-comparison-delta"
                >
                  {delta > 0 ? '+' : ''}{delta}
                </span>
              </DlRow>
            ) : null}
            {direction ? (
              <DlRow label="Direzione">{direction}</DlRow>
            ) : null}
          </dl>
        </Section>
      ) : null}

      {/* Dettagli tecnici */}
      <details
        className="rounded-lg border border-slate-200"
        data-testid="v31-technical-details"
      >
        <summary
          className="cursor-pointer px-3 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500 outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
          data-testid="v31-technical-details-summary"
        >
          Dettagli tecnici e audit
        </summary>
        <div className="space-y-4 border-t border-slate-100 px-3 py-3" data-testid="v31-section-diagnostics">
          <p className="text-xs text-violet-800" data-testid="v31-shadow-note">
            V3.1 shadow — formula candidata in osservazione.
          </p>
          <dl className="space-y-1.5 text-sm">
            <DlRow label="Risultato persistito">
              <span data-testid="v31-persisted-result">
                {asNumber(persisted.score) ??
                  explanation.stored_result_display ??
                  String(explanation.stored_result ?? '—')}
              </span>
            </DlRow>
            <DlRow label="Risultato audit">
              <span data-testid="v31-audit-result">
                {explanation.audit_result == null ? '—' : String(explanation.audit_result)}
              </span>
            </DlRow>
            <DlRow label="Consistency">
              <span data-testid="v31-consistency">{explanation.consistency?.status ?? '—'}</span>
            </DlRow>
            <DlRow label="candidate_version">
              <span data-testid="v31-candidate-version">{candidateVersion ?? '—'}</span>
            </DlRow>
            <DlRow label="formula_version">
              <span data-testid="v31-formula-version">{formulaVersion ?? '—'}</span>
            </DlRow>
            <DlRow label="audit_version">
              <span data-testid="v31-audit-version">{auditVersion ?? '—'}</span>
            </DlRow>
            <DlRow label="generated_at">
              <span data-testid="v31-generated-at">{generatedAt ?? '—'}</span>
            </DlRow>
            <DlRow label="source_snapshot_at">
              <span data-testid="v31-source-snapshot-at">{sourceSnapshotAt ?? '—'}</span>
            </DlRow>
          </dl>

          {/* Sezioni extra dal payload */}
          {sections.length > 0 ? (
            <div data-testid="v31-raw-sections">
              <p className="text-[10px] font-semibold uppercase text-slate-500">Sezioni payload</p>
              <div className="mt-2 space-y-2">
                {sections.map((sec, idx) => (
                  <div
                    key={sec.section_key ?? idx}
                    className="rounded border border-slate-100 px-2 py-2 text-xs"
                    data-testid={`v31-section-${sec.section_key ?? idx}`}
                  >
                    <p className="font-semibold text-slate-800">
                      {SECTION_TITLES[sec.section_key] ?? sec.title ?? sec.section_key}
                    </p>
                    {sec.description ? (
                      <p className="mt-1 text-slate-600">{sec.description}</p>
                    ) : null}
                    {sec.formula_symbolic ? (
                      <p className="mt-1 font-mono text-[10px] text-slate-500">
                        {sec.formula_symbolic}
                      </p>
                    ) : null}
                    {sec.formula_applied && sec.formula_applied.length > 0 ? (
                      <ol className="mt-1 list-decimal space-y-0.5 pl-4 font-mono text-[10px] text-slate-500">
                        {sec.formula_applied.map((step, i) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ol>
                    ) : null}
                    {sec.inputs && Object.keys(sec.inputs).length > 0 ? (
                      <pre className="mt-1 overflow-x-auto font-mono text-[10px] text-slate-500">
                        {JSON.stringify(sec.inputs, null, 0)}
                      </pre>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {/* Input grezzi */}
          {Object.keys(input).length > 0 ? (
            <div data-testid="v31-raw-inputs">
              <p className="text-[10px] font-semibold uppercase text-slate-500">Input grezzi</p>
              <div className="mt-1 overflow-x-auto">
                <table className="w-full min-w-[320px] text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500">
                    <tr>
                      <th className="px-2 py-1">Input</th>
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
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </div>
      </details>
    </div>
  )
}
