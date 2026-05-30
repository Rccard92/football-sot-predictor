import type { InternalFormulaBlock, PredictionFormulaBreakdownSide, V21CoverageSummary } from '../../types/sotExplanation'
import { V21_MODEL } from '../../lib/modelVersions'
import {
  V21AnchorExplainSection,
  V21FinalSummary,
  V21FormulaOverviewBox,
  V21MacroAreasTable,
  V21MacroMultiplierIntro,
  V21TechnicalFormulaSection,
  V21VariableTypesLegend,
} from './V21FormulaExplanationPanels'

function Badge({
  children,
  tone,
}: {
  children: React.ReactNode
  tone: 'slate' | 'emerald' | 'rose' | 'amber'
}) {
  const map = {
    slate: 'bg-slate-100 text-slate-800 border-slate-200',
    emerald: 'bg-emerald-50 text-emerald-900 border-emerald-200',
    rose: 'bg-rose-50 text-rose-900 border-rose-200',
    amber: 'bg-amber-50 text-amber-950 border-amber-200',
  }
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${map[tone]}`}>
      {children}
    </span>
  )
}

function InternalFormulaPanel({ block }: { block: InternalFormulaBlock }) {
  return (
    <div className="space-y-2 text-[11px] text-slate-800">
      {block.formula_text ? <p className="leading-relaxed text-slate-700">{block.formula_text}</p> : null}
      {block.formula_symbolic ? (
        <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-2 font-mono text-[10px] leading-relaxed text-slate-900">
          {block.formula_symbolic}
        </pre>
      ) : null}
      {block.formula_numeric ? (
        <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-2 font-mono text-[10px] leading-relaxed text-slate-900">
          {block.formula_numeric}
        </pre>
      ) : null}
      {block.component_value != null ? (
        <p className="tabular-nums text-slate-800">
          Valore componente (salvato): <span className="font-semibold">{block.component_value}</span>
        </p>
      ) : null}
      {block.rows.length ? (
        <div className="overflow-x-auto rounded-lg border border-slate-100">
          <table className="min-w-full text-left text-[10px]">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-slate-600">
                <th className="px-2 py-1 font-medium">Voce</th>
                <th className="px-2 py-1 font-medium">Valore</th>
                <th className="px-2 py-1 font-medium">Peso</th>
                <th className="px-2 py-1 font-medium">Contributo</th>
                <th className="px-2 py-1 font-medium">Calcolo / altro</th>
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, i) => (
                <tr key={i} className="border-t border-slate-100 align-top">
                  <td className="px-2 py-1.5 font-medium text-slate-900">{String(row.label ?? row.key ?? i)}</td>
                  <td className="px-2 py-1.5 tabular-nums text-slate-800">{row.value != null ? String(row.value) : '—'}</td>
                  <td className="px-2 py-1.5 tabular-nums text-slate-600">
                    {row.weight != null
                      ? String(row.weight)
                      : row.weight_internal != null
                        ? String(row.weight_internal)
                        : '—'}
                  </td>
                  <td className="px-2 py-1.5 tabular-nums text-slate-800">
                    {row.contribution != null ? String(row.contribution) : '—'}
                  </td>
                  <td className="px-2 py-1.5 text-slate-600">
                    {row.calc_expression != null ? String(row.calc_expression) : ''}
                    {row.formula != null ? String(row.formula) : ''}
                    {row.resolved != null || row.raw_input != null ? (
                      <span className="block text-[9px] text-slate-500">
                        {row.resolved != null ? `resolved: ${String(row.resolved)} ` : ''}
                        {row.raw_input != null ? `input: ${String(row.raw_input)}` : ''}
                      </span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {block.notes.map((n) => (
        <p key={n} className="text-slate-600">
          {n}
        </p>
      ))}
      <div className="flex flex-wrap gap-1">
        {block.flags.cap_applied ? <Badge tone="rose">Cap applicato</Badge> : null}
        {block.flags.fallbacks_used?.length ? (
          <Badge tone="amber">Fallback: {block.flags.fallbacks_used.join(', ')}</Badge>
        ) : null}
      </div>
    </div>
  )
}

function V21CoverageSummaryPanel({ summary }: { summary: V21CoverageSummary }) {
  return (
    <dl className="grid gap-2 text-[11px] text-slate-800 sm:grid-cols-2">
      <div>
        <dt className="text-slate-500">Macroaree predittive usate</dt>
        <dd className="font-mono font-semibold">{summary.predictive_macros_used ?? '—'}</dd>
      </div>
      <div>
        <dt className="text-slate-500">Micro disponibili</dt>
        <dd className="font-mono font-semibold">
          {summary.micro_available ?? 0}/{summary.micro_total ?? '—'}
        </dd>
      </div>
      <div>
        <dt className="text-slate-500">Micro in fallback neutro</dt>
        <dd className="font-mono font-semibold">{summary.micro_fallback_neutral ?? 0}</dd>
      </div>
      <div>
        <dt className="text-slate-500">Micro non disponibili dal feed</dt>
        <dd className="font-mono font-semibold">{summary.micro_feed_unavailable ?? 0}</dd>
      </div>
      <div>
        <dt className="text-slate-500">Macro qualità</dt>
        <dd className="text-slate-700">{summary.quality_macro_note ?? 'confidence only'}</dd>
      </div>
    </dl>
  )
}

function FormulaTable({
  rows,
  showStatus = false,
}: {
  rows: PredictionFormulaBreakdownSide['components_table']
  showStatus?: boolean
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-100">
      <table className="min-w-full text-left text-xs">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-slate-600">
            <th className="px-3 py-2 font-medium">Componente</th>
            <th className="px-3 py-2 font-medium">Valore</th>
            <th className="px-3 py-2 font-medium">Peso</th>
            <th className="px-3 py-2 font-medium">Calcolo contributo</th>
            <th className="px-3 py-2 font-medium">Contributo finale</th>
            {showStatus ? <th className="px-3 py-2 font-medium">Stato</th> : null}
          </tr>
        </thead>
        <tbody className="text-slate-800">
          {rows.map((r) => (
            <tr key={`${r.componente}-${r.macro_key ?? ''}`} className="border-b border-slate-100 align-top">
              <td className="px-3 py-2 font-medium">
                {r.componente}
                {r.fallback_used ? (
                  <span className="ml-1 text-[10px] font-normal text-amber-800">(fallback)</span>
                ) : null}
                {r.warning ? <span className="mt-0.5 block text-[10px] font-normal text-amber-900">{r.warning}</span> : null}
              </td>
              <td className="px-3 py-2 tabular-nums">{r.valore_componente ?? '—'}</td>
              <td className="px-3 py-2 tabular-nums">{r.peso ?? '—'}</td>
              <td className="px-3 py-2 font-mono text-[10px] text-slate-700">{r.calcolo_contributo}</td>
              <td className="px-3 py-2 tabular-nums font-medium">{r.contributo_finale ?? '—'}</td>
              {showStatus ? (
                <td className="px-3 py-2 text-[10px] text-slate-600">{r.status ?? '—'}</td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FormulaStoredSummary({
  formula,
  cardPredicted,
  cardMismatch,
}: {
  formula: PredictionFormulaBreakdownSide
  cardPredicted: number | null
  cardMismatch: boolean
}) {
  return (
    <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-800">
      <p>
        <span className="font-semibold">Somma contributi (display):</span>{' '}
        <span className="tabular-nums">{formula.sum_contributions ?? '—'}</span>
      </p>
      <p className="mt-1">
        <span className="font-semibold">Valore previsto salvato:</span>{' '}
        <span className="tabular-nums text-base font-semibold text-slate-900">
          {formula.stored_predicted_sot ?? '—'}
        </span>
      </p>
      {formula.delta_vs_stored != null ? (
        <p className="mt-1 text-slate-600">
          Differenza (somma − salvato): <span className="tabular-nums">{formula.delta_vs_stored}</span>
        </p>
      ) : null}
      {formula.checksum_warning ? (
        <p className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-950">
          {formula.checksum_warning}
        </p>
      ) : null}
      {cardMismatch ? (
        <p className="mt-2 text-[11px] text-rose-700">
          Attenzione: la card mostra {cardPredicted} ma il breakdown usa {formula.stored_predicted_sot} dal salvataggio.
        </p>
      ) : null}
    </div>
  )
}

export function PredictionFinalFormulaSection({
  teamName,
  formula,
  cardPredicted,
  traceFormulaCount,
}: {
  teamName: string
  formula: PredictionFormulaBreakdownSide | null | undefined
  cardPredicted: number | null
  traceFormulaCount?: number
}) {
  if (!formula?.terms?.length) return null

  const isV21 = formula.model_version === V21_MODEL
  const cardMismatch =
    cardPredicted != null &&
    formula.stored_predicted_sot != null &&
    Math.abs(Number(cardPredicted) - Number(formula.stored_predicted_sot)) > 0.01

  const v21Summary = formula.v21_coverage_summary
  const numericComponentsUsed = isV21
    ? v21Summary?.micro_total ?? formula.macro_areas_table?.length ?? formula.components_table.length
    : formula.components_table.length
  const traceCountMismatch =
    !isV21 &&
    traceFormulaCount != null &&
    numericComponentsUsed > 0 &&
    traceFormulaCount !== numericComponentsUsed

  return (
    <div className="space-y-3 rounded-xl border border-slate-100 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">
          {isV21 ? 'Formula v2.1 — macro weighted' : 'Formula finale'} — {teamName}
        </h3>
        <div className="flex flex-wrap gap-1">
          {formula.flags.cap_applied ? <Badge tone="rose">Cap: sì</Badge> : <Badge tone="slate">Cap: no</Badge>}
          {formula.flags.fallbacks_used?.length ? (
            <Badge tone="amber">Fallback: {formula.flags.fallbacks_used.join(', ')}</Badge>
          ) : (
            <Badge tone="emerald">Fallback: nessuno</Badge>
          )}
        </div>
      </div>

      {isV21 ? (
        <>
          {v21Summary ? (
            <div className="rounded-lg border border-indigo-100 bg-indigo-50/40 p-3">
              <p className="mb-2 text-[11px] font-semibold text-indigo-950">Copertura componenti v2.1</p>
              <V21CoverageSummaryPanel summary={v21Summary} />
            </div>
          ) : null}

          <V21FormulaOverviewBox formula={formula} />
          <V21VariableTypesLegend />

          {formula.anchor_breakdown_table?.length ? (
            <div className="space-y-2">
              <V21AnchorExplainSection formula={formula} />
              <FormulaTable rows={formula.anchor_breakdown_table} />
            </div>
          ) : null}

          {formula.macro_areas_table?.length ? (
            <div className="space-y-2">
              <V21MacroMultiplierIntro formula={formula} />
              <V21MacroAreasTable rows={formula.macro_areas_table} />
            </div>
          ) : null}

          {formula.quality_macro_table?.length ? (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-slate-900">
                Controlli qualità / confidence (non nel moltiplicatore SOT)
              </p>
              <FormulaTable rows={formula.quality_macro_table} showStatus />
            </div>
          ) : null}

          <V21FinalSummary formula={formula} />
          <V21TechnicalFormulaSection formula={formula} />
        </>
      ) : (
        <>
          <p className="text-[11px] text-slate-700">
            Variabili/componenti numerici usati:{' '}
            <span className="font-mono font-semibold tabular-nums text-slate-900">{numericComponentsUsed}</span>
          </p>
          {traceCountMismatch ? (
            <p className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-950">
              Il conteggio «Usate nella formula finale» nel trace ({traceFormulaCount}) non coincide con le righe della
              tabella formula qui sotto ({numericComponentsUsed}).
            </p>
          ) : null}

          <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 font-mono text-[11px] leading-relaxed text-slate-900">
            {formula.formula_symbolic}
          </pre>
          <pre className="whitespace-pre-wrap rounded-lg border border-slate-100 bg-white p-3 font-mono text-[11px] leading-relaxed text-slate-900">
            {formula.formula_numeric}
          </pre>

          <FormulaTable rows={formula.components_table} />
        </>
      )}

      <FormulaStoredSummary formula={formula} cardPredicted={cardPredicted} cardMismatch={cardMismatch} />
    </div>
  )
}

export { InternalFormulaPanel }
