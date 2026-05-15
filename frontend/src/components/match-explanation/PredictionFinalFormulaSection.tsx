import type { InternalFormulaBlock, PredictionFormulaBreakdownSide } from '../../types/sotExplanation'

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

export function PredictionFinalFormulaSection({
  teamName,
  formula,
  cardPredicted,
  traceFormulaCount,
}: {
  teamName: string
  formula: PredictionFormulaBreakdownSide | null | undefined
  cardPredicted: number | null
  /** Conteggio «Usate nella formula finale» dal trace (deriveTraceabilityForSide), per confronto UI. */
  traceFormulaCount?: number
}) {
  if (!formula?.terms?.length) return null

  const cardMismatch =
    cardPredicted != null &&
    formula.stored_predicted_sot != null &&
    Math.abs(Number(cardPredicted) - Number(formula.stored_predicted_sot)) > 0.01

  // N mostrato all'utente = righe della tabella componenti (stessa griglia sotto).
  const numericComponentsUsed = formula.components_table.length
  const traceCountMismatch =
    traceFormulaCount != null &&
    numericComponentsUsed > 0 &&
    traceFormulaCount !== numericComponentsUsed

  return (
    <div className="space-y-3 rounded-xl border border-slate-100 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">Formula finale — {teamName}</h3>
        <div className="flex flex-wrap gap-1">
          {formula.flags.cap_applied ? <Badge tone="rose">Cap: sì</Badge> : <Badge tone="slate">Cap: no</Badge>}
          {formula.flags.fallbacks_used?.length ? (
            <Badge tone="amber">Fallback: {formula.flags.fallbacks_used.join(', ')}</Badge>
          ) : (
            <Badge tone="emerald">Fallback: nessuno</Badge>
          )}
        </div>
      </div>

      <p className="text-[11px] text-slate-700">
        Variabili/componenti numerici usati:{' '}
        <span className="font-mono font-semibold tabular-nums text-slate-900">{numericComponentsUsed}</span>
      </p>
      {traceCountMismatch ? (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-950">
          Il conteggio «Usate nella formula finale» nel trace ({traceFormulaCount}) non coincide con le righe della tabella
          formula qui sotto ({numericComponentsUsed}). Controlla ruoli trace e breakdown salvato.
        </p>
      ) : null}

      <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 font-mono text-[11px] leading-relaxed text-slate-900">
        {formula.formula_symbolic}
      </pre>
      <pre className="whitespace-pre-wrap rounded-lg border border-slate-100 bg-white p-3 font-mono text-[11px] leading-relaxed text-slate-900">
        {formula.formula_numeric}
      </pre>

      <div className="overflow-x-auto rounded-lg border border-slate-100">
        <table className="min-w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-slate-600">
              <th className="px-3 py-2 font-medium">Componente</th>
              <th className="px-3 py-2 font-medium">Valore</th>
              <th className="px-3 py-2 font-medium">Peso</th>
              <th className="px-3 py-2 font-medium">Calcolo contributo</th>
              <th className="px-3 py-2 font-medium">Contributo finale</th>
              <th className="px-3 py-2 font-medium">Provenienza</th>
            </tr>
          </thead>
          <tbody className="text-slate-800">
            {formula.components_table.map((r) => (
              <tr key={r.componente} className="border-b border-slate-100">
                <td className="px-3 py-2 font-medium">
                  {r.componente}
                  {r.fallback_used ? (
                    <span className="ml-1 text-[10px] font-normal text-amber-800">(fallback)</span>
                  ) : null}
                </td>
                <td className="px-3 py-2 tabular-nums">{r.valore_componente ?? '—'}</td>
                <td className="px-3 py-2 tabular-nums">
                  {r.peso != null && Number.isFinite(Number(r.peso))
                    ? `${Math.round(Number(r.peso) * 100)}%`
                    : '—'}
                </td>
                <td className="px-3 py-2 font-mono text-[10px] text-slate-700">{r.calcolo_contributo}</td>
                <td className="px-3 py-2 tabular-nums font-medium">{r.contributo_finale ?? '—'}</td>
                <td className="px-3 py-2 font-mono text-[9px] text-slate-500">
                  {r.source_path ?? '—'}
                  {r.fallback_reason ? (
                    <span className="mt-0.5 block text-amber-900">{String(r.fallback_reason)}</span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

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
    </div>
  )
}

export { InternalFormulaPanel }
