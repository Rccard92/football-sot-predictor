import { useState } from 'react'
import {
  CECCHINO_HEATMAP_FORMULA_INTRO,
  CECCHINO_SCALA_MAPPING_NOTE,
  COLUMN_DISPLAY_LABELS,
  getLegendEntriesForSignal,
  getSignalTabs,
  type CecchinoSignalFormulaEntry,
} from '../../../lib/cecchinoSignalFormulaLegend'

function CopyFormulaButton({ formula }: { formula: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(formula)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <button
      type="button"
      onClick={() => void handleCopy()}
      className="mt-1 rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-600 hover:bg-slate-100"
    >
      {copied ? 'Copiata' : 'Copia formula'}
    </button>
  )
}

function ReadableFormula({ text }: { text: string }) {
  const parts = text.split('\n\n')
  return (
    <div className="space-y-1 text-xs leading-relaxed text-slate-700">
      {parts.map((part, i) => (
        <p key={i} className={i > 0 ? 'text-slate-600' : undefined}>
          {part}
        </p>
      ))}
    </div>
  )
}

function FormulaRow({ entry }: { entry: CecchinoSignalFormulaEntry }) {
  const colLabel = COLUMN_DISPLAY_LABELS[entry.source_column]

  if (!entry.is_active_column) {
    return (
      <tr className="border-t border-slate-100 bg-slate-50/40">
        <td className="px-3 py-2.5 font-medium text-slate-700">{colLabel}</td>
        <td className="px-3 py-2.5 text-slate-400">—</td>
        <td className="px-3 py-2.5 text-slate-400">—</td>
        <td className="px-3 py-2.5">
          <span className="text-xs text-slate-500">Non prevista da Excel</span>
        </td>
        <td className="px-3 py-2.5 text-xs text-slate-500">
          {entry.target_market_label ?? '—'}
        </td>
        <td className="px-3 py-2.5 text-xs text-slate-500">
          {entry.evaluation_rule ?? '—'}
        </td>
      </tr>
    )
  }

  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50/60">
      <td className="px-3 py-2.5 font-medium text-slate-800">{colLabel}</td>
      <td className="px-3 py-2.5 font-mono text-xs text-slate-800">{entry.source_cell}</td>
      <td className="px-3 py-2.5">
        <pre className="whitespace-pre-wrap break-all font-mono text-[11px] leading-snug text-slate-800">
          {entry.excel_formula}
        </pre>
        {entry.excel_formula && <CopyFormulaButton formula={entry.excel_formula} />}
      </td>
      <td className="px-3 py-2.5">
        <ReadableFormula text={entry.readable_formula} />
      </td>
      <td className="px-3 py-2.5 text-xs text-slate-700">{entry.target_market_label}</td>
      <td className="px-3 py-2.5 text-xs text-slate-700">{entry.evaluation_rule}</td>
    </tr>
  )
}

export function SignalsFormulaLegendAccordion() {
  const [open, setOpen] = useState(false)
  const tabs = getSignalTabs()
  const [activeTab, setActiveTab] = useState(tabs[0]?.signal_group ?? 'UNDER_UNDER_PT')
  const entries = getLegendEntriesForSignal(activeTab)
  const activeLabel = tabs.find((t) => t.signal_group === activeTab)?.signal_label ?? activeTab

  return (
    <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50/50">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left hover:bg-slate-100/60"
      >
        <div>
          <h3 className="text-sm font-semibold text-slate-800">Legenda formule segnali Cecchino</h3>
          <p className="mt-0.5 text-xs text-slate-600">
            Mostra da quale cella Excel nasce ogni segnale, la formula originale e la regola usata
            per valutarne l&apos;esito.
          </p>
        </div>
        <span className="shrink-0 text-slate-500" aria-hidden>
          {open ? '▾' : '▸'}
        </span>
      </button>

      {open && (
        <div className="space-y-4 border-t border-slate-200 px-4 py-4">
          <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-3 text-sm text-sky-900">
            <p>{CECCHINO_HEATMAP_FORMULA_INTRO.description}</p>
            <ul className="mt-2 list-inside list-disc space-y-0.5 text-xs">
              {CECCHINO_HEATMAP_FORMULA_INTRO.formulas.map((f) => (
                <li key={f} className="font-mono">
                  {f}
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-900">
            {CECCHINO_SCALA_MAPPING_NOTE}
          </div>

          <div className="flex gap-1 overflow-x-auto pb-1">
            {tabs.map((tab) => (
              <button
                key={tab.signal_group}
                type="button"
                onClick={() => setActiveTab(tab.signal_group)}
                className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  activeTab === tab.signal_group
                    ? 'bg-slate-800 text-white'
                    : 'bg-white text-slate-700 ring-1 ring-slate-200 hover:bg-slate-100'
                }`}
              >
                {tab.signal_label}
              </button>
            ))}
          </div>

          <p className="text-xs font-medium text-slate-600">
            Segnale: <span className="text-slate-900">{activeLabel}</span>
          </p>

          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="min-w-[720px] w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2">Colonna</th>
                  <th className="px-3 py-2">Cella Excel</th>
                  <th className="min-w-[200px] px-3 py-2">Formula Excel</th>
                  <th className="min-w-[220px] px-3 py-2">Formula parlante</th>
                  <th className="px-3 py-2">Target</th>
                  <th className="min-w-[160px] px-3 py-2">Esito W/L</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <FormulaRow key={`${entry.signal_group}-${entry.source_column}`} entry={entry} />
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-slate-500">
            Le formule documentano la griglia Excel AutomazioneCecchino.xlsm (tab CECCHINO). I
            segnali pending e non valutabili non entrano nel calcolo del success rate della
            heatmap. Le colonne contrassegnate come «Non prevista da Excel» non generano activation
            nel monitoraggio.
          </p>
        </div>
      )}
    </div>
  )
}
