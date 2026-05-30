import type { FormulaComponentTableRow, PredictionFormulaBreakdownSide } from '../../types/sotExplanation'
import { formatAuditNumber, formatV21ManifestWeight } from '../../utils/v21Display'
import {
  ANCHOR_OPP_SOT_CONCEDED_WEIGHT,
  ANCHOR_TEAM_SOT_WEIGHT,
  extractV21FormulaValues,
  formatMultiplierPctChange,
  formatSotValue,
  getMacroEffect,
  macroEffectLabel,
  macroHighlightSentence,
  macroMultiplierTrendText,
  pickMacroHighlight,
  V21_MACRO_DERIVED_FROM,
  type MacroEffectKind,
} from '../../utils/v21FormulaExplain'

function EffectBadge({ kind }: { kind: MacroEffectKind }) {
  const tone =
    kind === 'push_up'
      ? 'bg-emerald-50 text-emerald-900 border-emerald-200'
      : kind === 'push_down'
        ? 'bg-amber-50 text-amber-950 border-amber-200'
        : 'bg-slate-100 text-slate-800 border-slate-200'
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${tone}`}>
      {macroEffectLabel(kind)}
    </span>
  )
}

function ExplainCard({
  title,
  tipo,
  fonte,
  descrizione,
  value,
}: {
  title: string
  tipo: string
  fonte?: string
  descrizione: string
  value?: string | null
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
      <p className="text-xs font-semibold text-slate-900">{title}</p>
      {value ? (
        <p className="mt-1 text-sm font-semibold tabular-nums text-slate-900">{value}</p>
      ) : null}
      <dl className="mt-2 space-y-1 text-[11px] text-slate-700">
        <div>
          <dt className="inline font-medium text-slate-500">Tipo: </dt>
          <dd className="inline">{tipo}</dd>
        </div>
        {fonte ? (
          <div>
            <dt className="inline font-medium text-slate-500">Fonte: </dt>
            <dd className="inline">{fonte}</dd>
          </div>
        ) : null}
        <div>
          <dt className="font-medium text-slate-500">Descrizione</dt>
          <dd className="mt-0.5 leading-relaxed">{descrizione}</dd>
        </div>
      </dl>
    </div>
  )
}

export function V21FormulaOverviewBox({ formula }: { formula: PredictionFormulaBreakdownSide }) {
  const v = extractV21FormulaValues(formula)
  const pct = formatMultiplierPctChange(v.macroMultiplier)

  return (
    <div className="space-y-3 rounded-lg border border-sky-100 bg-sky-50/50 p-3 sm:p-4">
      <h4 className="text-sm font-semibold text-sky-950">Come nasce questa previsione</h4>
      <ol className="space-y-3 text-[11px] leading-relaxed text-slate-800">
        <li>
          <p className="font-semibold text-slate-900">Step 1 — Punto di partenza</p>
          <p className="mt-1">
            Il modello parte da una stima base dei tiri in porta della squadra. Combina quanto produce la squadra con
            quanto concede l&apos;avversario.
          </p>
          <p className="mt-1 font-medium tabular-nums text-slate-900">Base: {formatSotValue(v.baseAnchor)} SOT</p>
        </li>
        <li>
          <p className="font-semibold text-slate-900">Step 2 — Correzione del modello</p>
          <p className="mt-1">
            Poi controlla 9 macroaree: produzione offensiva, difesa avversaria, forma, xG, giocatori, formazioni,
            infortuni e ritmo. Queste aree aumentano o riducono la previsione base.
          </p>
          <p className="mt-1 font-medium tabular-nums text-slate-900">
            Correzione macroaree: {formatSotValue(v.macroMultiplier)}
            {pct ? `, cioè ${pct}` : ''}
          </p>
        </li>
        <li>
          <p className="font-semibold text-slate-900">Step 3 — Previsione finale</p>
          <p className="mt-1">
            La base viene moltiplicata per il correttivo delle macroaree. Se il moltiplicatore è sopra 1, la previsione
            sale. Se è sotto 1, la previsione scende.
          </p>
          <p className="mt-1 font-medium tabular-nums text-slate-900">
            Risultato finale: {formatSotValue(v.finalSot)} SOT
          </p>
        </li>
      </ol>
    </div>
  )
}

export function V21VariableTypesLegend() {
  return (
    <details className="rounded-lg border border-slate-200 bg-white p-3 text-[11px] text-slate-800">
      <summary className="cursor-pointer font-semibold text-slate-900">Tipi di variabili</summary>
      <ul className="mt-2 space-y-2 leading-relaxed">
        <li>
          <span className="font-medium text-slate-900">Dato diretto:</span> Dato letto direttamente dalle statistiche,
          per esempio SOT fatti, xG prodotti, possesso.
        </li>
        <li>
          <span className="font-medium text-slate-900">Dato derivato:</span> Dato calcolato partendo da altri dati, per
          esempio delta xG rispetto alla media lega.
        </li>
        <li>
          <span className="font-medium text-slate-900">Variabile composita:</span> Area del modello composta da più dati,
          per esempio Qualità occasioni o Player layer.
        </li>
      </ul>
    </details>
  )
}

export function V21AnchorExplainSection({ formula }: { formula: PredictionFormulaBreakdownSide }) {
  const v = extractV21FormulaValues(formula)
  const teamPct = Math.round(ANCHOR_TEAM_SOT_WEIGHT * 100)
  const oppPct = Math.round(ANCHOR_OPP_SOT_CONCEDED_WEIGHT * 100)

  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold text-slate-900">Base anchor SOT</p>
      <p className="text-[11px] leading-relaxed text-slate-700">
        Questa è la base di partenza della previsione. Non tiene ancora conto di forma, xG, formazioni o infortuni.
        Guarda solo due cose: quanti tiri in porta produce la squadra e quanti ne concede l&apos;avversario.
      </p>
      <div className="grid gap-2">
        <ExplainCard
          title="Media SOT fatti squadra"
          tipo="dato diretto"
          fonte="statistiche squadra"
          descrizione="Quanto tira mediamente in porta questa squadra."
          value={v.teamSotAvg != null ? formatSotValue(v.teamSotAvg) : null}
        />
        <ExplainCard
          title="Media SOT concessi avversario"
          tipo="dato diretto"
          fonte="statistiche avversario"
          descrizione="Quanti tiri in porta concede mediamente l&apos;avversario."
          value={v.oppSotConcededAvg != null ? formatSotValue(v.oppSotConcededAvg) : null}
        />
        <ExplainCard
          title="Formula base"
          tipo="formula scelta dal modello v2.1"
          descrizione={`La v2.1 dà un peso leggermente maggiore alla produzione della squadra: ${teamPct}%. La difesa concessiva dell'avversario pesa ${oppPct}%.`}
        />
      </div>
      <p className="rounded-md bg-slate-50 px-3 py-2 text-[11px] font-medium text-slate-900">
        Base = {teamPct}% produzione squadra + {oppPct}% concessioni avversario
      </p>
      {v.anchorFormulaExpr ? (
        <p className="font-mono text-[11px] tabular-nums text-slate-800">Base = {v.anchorFormulaExpr}</p>
      ) : null}
      <p className="text-[10px] italic leading-relaxed text-slate-600">
        Il rapporto {teamPct}/{oppPct} è una scelta del modello v2.1. Serve a dare una base stabile prima delle
        correzioni delle macroaree.
      </p>
    </div>
  )
}

export function V21MacroMultiplierIntro({ formula }: { formula: PredictionFormulaBreakdownSide }) {
  const highlight = pickMacroHighlight(formula.macro_areas_table)
  const example = macroHighlightSentence(highlight)

  return (
    <div className="space-y-2 text-[11px] leading-relaxed text-slate-700">
      <p className="text-xs font-semibold text-slate-900">Macroaree predittive (moltiplicatore)</p>
      <p>
        Ogni macroarea produce un indice. L&apos;indice dice se quella parte del modello spinge la previsione verso
        l&apos;alto, verso il basso o la lascia stabile.
      </p>
      <ul className="list-inside list-disc space-y-1 text-slate-700">
        <li>indice &gt; 1.03: spinge verso l&apos;alto</li>
        <li>indice tra 0.97 e 1.03: quasi neutra</li>
        <li>indice &lt; 0.97: spinge verso il basso</li>
      </ul>
      <p>
        Il peso indica quanto conta quella macroarea nel correttivo finale. Le macroaree più importanti pesano di più.
      </p>
      {example ? <p className="rounded-md bg-slate-50 px-2 py-1.5 text-slate-800">Esempio: {example}</p> : null}
    </div>
  )
}

export function V21MacroAreasTable({ rows }: { rows: FormulaComponentTableRow[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-100">
      <table className="min-w-full text-left text-xs">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-slate-600">
            <th className="px-3 py-2 font-medium">Componente</th>
            <th className="px-3 py-2 font-medium">Valore</th>
            <th className="hidden px-3 py-2 font-medium sm:table-cell">Peso</th>
            <th className="px-3 py-2 font-medium">Effetto</th>
            <th className="hidden px-3 py-2 font-medium md:table-cell">Calcolo</th>
            <th className="hidden px-3 py-2 font-medium lg:table-cell">Contributo</th>
            <th className="hidden px-3 py-2 font-medium sm:table-cell">Stato</th>
          </tr>
        </thead>
        <tbody className="text-slate-800">
          {rows.map((r) => {
            const index = r.valore_componente != null ? Number(r.valore_componente) : null
            const effect = index != null && Number.isFinite(index) ? getMacroEffect(index) : 'neutral'
            const derivedFrom = r.macro_key ? V21_MACRO_DERIVED_FROM[r.macro_key] : null
            return (
              <tr key={`${r.componente}-${r.macro_key ?? ''}`} className="border-b border-slate-100 align-top">
                <td className="px-3 py-2 font-medium">
                  {r.componente}
                  {derivedFrom ? (
                    <span className="mt-1 block text-[10px] font-normal leading-snug text-slate-500">
                      Da cosa è ricavata: {derivedFrom}
                    </span>
                  ) : null}
                  {r.warning ? (
                    <span className="mt-0.5 block text-[10px] font-normal text-amber-900">{r.warning}</span>
                  ) : null}
                </td>
                <td className="px-3 py-2 tabular-nums">{r.valore_componente != null ? formatAuditNumber(Number(r.valore_componente)) : '—'}</td>
                <td className="hidden px-3 py-2 tabular-nums sm:table-cell">
                  {formatV21ManifestWeight(r.peso, 'manifest_points')}
                </td>
                <td className="px-3 py-2">
                  <EffectBadge kind={effect} />
                </td>
                <td className="hidden px-3 py-2 font-mono text-[10px] text-slate-700 md:table-cell">{r.calcolo_contributo}</td>
                <td className="hidden px-3 py-2 tabular-nums font-medium lg:table-cell">{r.contributo_finale ?? '—'}</td>
                <td className="hidden px-3 py-2 text-[10px] text-slate-600 sm:table-cell">{r.status ?? '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function V21FinalSummary({ formula }: { formula: PredictionFormulaBreakdownSide }) {
  const v = extractV21FormulaValues(formula)
  const pct = formatMultiplierPctChange(v.macroMultiplier)
  const trend = macroMultiplierTrendText(v.macroMultiplier)

  if (v.baseAnchor == null || v.macroMultiplier == null || v.finalSot == null) return null

  return (
    <div className="rounded-lg border border-emerald-100 bg-emerald-50/40 p-3 text-[11px] leading-relaxed text-slate-800">
      <p className="font-semibold text-slate-900">Riepilogo</p>
      <p className="mt-1">
        Il modello parte da {formatSotValue(v.baseAnchor)} SOT. Le macroaree nel complesso generano un moltiplicatore di{' '}
        {formatSotValue(v.macroMultiplier)}
        {pct ? `, quindi ${pct.startsWith('-') ? 'riducono' : pct === '0%' ? 'lasciano stabile' : 'aumentano'} la previsione di circa il ${pct.replace('+', '')}` : ''}.
        La previsione finale diventa {formatSotValue(v.finalSot)} SOT.
      </p>
      <p className="mt-1 text-slate-700">{trend}</p>
    </div>
  )
}

export function V21TechnicalFormulaSection({ formula }: { formula: PredictionFormulaBreakdownSide }) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-slate-600">Formula tecnica</p>
      <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 font-mono text-[10px] leading-relaxed text-slate-700">
        {formula.formula_symbolic}
      </pre>
      <pre className="whitespace-pre-wrap rounded-lg border border-slate-100 bg-white p-3 font-mono text-[10px] leading-relaxed text-slate-700">
        {formula.formula_numeric}
      </pre>
    </div>
  )
}
