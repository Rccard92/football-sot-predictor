import type {
  CecchinoSignalContract,
  CecchinoSignalRowConsensus,
  CecchinoSignalsMatrix,
} from '../../lib/cecchinoApi'
import {
  CURRENT_SIGNAL_FORMULA_VERSION,
  SIGNAL_FORMULA_CURRENT_BADGE,
} from '../../lib/cecchinoSignalsApi'

type Props = {
  matrix: CecchinoSignalsMatrix
  variant?: 'default' | 'embedded'
  analysisMode?: boolean
  onOpenCell?: (rowKey: string, columnKey: string) => void
  hasExplanation?: (rowKey: string, columnKey: string) => boolean
  signalContract?: CecchinoSignalContract | null
}

function SiNoBadge({
  value,
  embedded,
  interactive,
  onClick,
  ariaLabel,
}: {
  value: string
  embedded?: boolean
  interactive?: boolean
  onClick?: () => void
  ariaLabel?: string
}) {
  if (value !== 'SI' && value !== 'NO') {
    return <span className="text-slate-400">—</span>
  }
  const isSi = value === 'SI'
  const base = embedded
    ? isSi
      ? 'bg-emerald-100 text-emerald-800 ring-emerald-200/80'
      : 'bg-rose-50 text-rose-700/90 ring-rose-200/60'
    : isSi
      ? 'bg-emerald-100 text-emerald-800'
      : 'bg-slate-100 text-slate-600'
  const className = `inline-block min-w-[2.25rem] rounded-md px-2 py-0.5 text-center text-[11px] font-semibold uppercase ring-1 ${base}`
  const title = isSi
    ? 'SI grezzo di formula: non implica da solo segno acquisito'
    : undefined

  if (interactive && onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        aria-label={ariaLabel}
        title={title}
        className={`${className} cursor-pointer hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/70`}
      >
        {value}
      </button>
    )
  }

  return (
    <span className={className} title={title}>
      {value}
    </span>
  )
}

function signalVal(signals: Record<string, string>, key: string): string {
  const v = signals[key]
  return v === 'SI' || v === 'NO' ? v : '—'
}

function consensusOutcomeLabel(consensus: CecchinoSignalRowConsensus | null | undefined): string {
  if (consensus == null) return '—'
  switch (consensus.acquisition_status) {
    case 'acquired_consensus':
      return 'Acquisito'
    case 'rejected_insufficient_consensus':
      return 'Non acquisito — consenso insufficiente'
    case 'acquired_single_formula_exempt':
      return 'Esente — singola formula'
    case 'no_raw_signal':
      return 'Nessun segnale'
    case 'legacy_unclassified':
      return 'Legacy non classificato'
    default:
      if (consensus.is_acquired === true) return 'Acquisito'
      return 'Nessun segnale'
  }
}

function consensusOutcomeClass(consensus: CecchinoSignalRowConsensus | null | undefined): string {
  switch (consensus?.acquisition_status) {
    case 'acquired_consensus':
      return 'bg-emerald-50 text-emerald-800 ring-emerald-200/70'
    case 'acquired_single_formula_exempt':
      return 'bg-sky-50 text-sky-800 ring-sky-200/70'
    case 'rejected_insufficient_consensus':
      return 'bg-amber-50 text-amber-900 ring-amber-200/70'
    case 'no_raw_signal':
      return 'bg-slate-50 text-slate-600 ring-slate-200/70'
    default:
      return 'bg-slate-50 text-slate-600 ring-slate-200/70'
  }
}

const EXCEL_COLS = ['excel_d', 'excel_e', 'excel_f', 'excel_g'] as const
const EXCEL_HEADERS = ['Excel D', 'Excel E', 'Excel F', 'Excel G']

export function CecchinoSignalsMatrixPanel({
  matrix,
  variant = 'default',
  analysisMode = false,
  onOpenCell,
  hasExplanation,
  signalContract = null,
}: Props) {
  const embedded = variant === 'embedded'
  const rows = matrix.rows ?? []
  const rel = matrix.reliability
  const inputs = matrix.inputs

  const detectedVersion =
    signalContract?.detected_formula_version ?? matrix.formula_version ?? null
  const formulaVersion = detectedVersion ?? signalContract?.formula_version ?? null
  const isCurrentFormula =
    signalContract?.is_current_formula === true
      ? true
      : signalContract?.is_current_formula === false
        ? false
        : matrix.status === 'available' && formulaVersion === CURRENT_SIGNAL_FORMULA_VERSION
  const showCurrentBadge = isCurrentFormula === true
  const nonCurrentWarning =
    !isCurrentFormula
      ? `Matrice storica non corrente — esclusa dai flussi operativi${
          formulaVersion ? ` (${formulaVersion})` : ''
        }${
          signalContract?.reason_code ? ` — ${signalContract.reason_code}` : ''
        }.`
      : null

  const outerClass = embedded
    ? 'space-y-4'
    : 'space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm'

  const renderBadge = (rowKey: string, columnKey: string, value: string, rowLabel: string) => {
    const canOpen =
      analysisMode &&
      (value === 'SI' || value === 'NO') &&
      (hasExplanation ? hasExplanation(rowKey, columnKey) : true)
    return (
      <SiNoBadge
        value={value}
        embedded={embedded}
        interactive={canOpen}
        onClick={canOpen ? () => onOpenCell?.(rowKey, columnKey) : undefined}
        ariaLabel={
          canOpen
            ? `Apri analisi ${rowLabel}, ${columnKey}, risultato ${value}`
            : undefined
        }
      />
    )
  }

  return (
    <div className={outerClass}>
      {!embedded && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-800">Segnali Cecchino (matrice SI/NO)</h3>
          <span className="text-[10px] text-slate-500">{matrix.source ?? ''}</span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {showCurrentBadge ? (
          <span className="inline-flex rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800 ring-1 ring-emerald-200/80">
            {SIGNAL_FORMULA_CURRENT_BADGE}
          </span>
        ) : null}
        {formulaVersion && !showCurrentBadge ? (
          <span className="inline-flex rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-900 ring-1 ring-amber-200/80">
            Formula {formulaVersion}
          </span>
        ) : null}
      </div>

      {nonCurrentWarning ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          {nonCurrentWarning}
        </div>
      ) : null}

      {inputs && (
        <p className="text-xs tabular-nums text-slate-600">
          F32={inputs.q1 != null ? Number(inputs.q1).toFixed(2) : '—'} · F33=
          {inputs.qx != null ? Number(inputs.qx).toFixed(2) : '—'} · F34=
          {inputs.q2 != null ? Number(inputs.q2).toFixed(2) : '—'} · F35=
          {inputs.avg_q != null ? Number(inputs.avg_q).toFixed(2) : '—'} · F36=
          {inputs.diff_1_2 != null ? Number(inputs.diff_1_2).toFixed(2) : '—'}
        </p>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full text-left text-sm text-slate-700">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2.5">Mercato / Segnale</th>
              {EXCEL_HEADERS.map((h) => (
                <th key={h} className="px-3 py-2.5 text-center">
                  {h}
                </th>
              ))}
              <th className="px-3 py-2.5 text-center">Scala</th>
              <th className="px-3 py-2.5 text-center">Consenso</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const sig = row.signals ?? {}
              const scalaKey =
                row.key === 'one_x' ? 'scala_1x' : row.key === 'x_two' ? 'scala_x2' : null
              const scala = scalaKey ? signalVal(sig, scalaKey) : '—'
              const outcome = consensusOutcomeLabel(row.consensus)
              return (
                <tr key={row.key} className="border-t border-slate-100 hover:bg-slate-50/60">
                  <td className="px-3 py-2 font-medium text-slate-800">{row.label}</td>
                  {EXCEL_COLS.map((col) => (
                    <td key={col} className="px-3 py-2 text-center">
                      {renderBadge(row.key, col, signalVal(sig, col), row.label)}
                    </td>
                  ))}
                  <td className="px-3 py-2 text-center">
                    {scala !== '—' && scalaKey
                      ? renderBadge(row.key, scalaKey, scala, row.label)
                      : '—'}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <span
                      className={`inline-block max-w-[11rem] rounded-md px-2 py-0.5 text-[10px] font-medium leading-snug ring-1 ${consensusOutcomeClass(row.consensus)}`}
                    >
                      {outcome}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="text-[11px] text-slate-500">
        Badge SI = esito grezzo della formula cella; l&apos;acquisizione del segno dipende dal
        consenso (colonna Consenso).
      </p>

      {rel && (
        <div
          className={
            embedded
              ? 'rounded-xl border border-slate-200 bg-gradient-to-br from-slate-50 to-indigo-50/40 px-4 py-4'
              : 'rounded-lg border border-indigo-100 bg-indigo-50/50 px-3 py-3 text-xs text-slate-700'
          }
        >
          <p className="text-sm font-semibold text-slate-900">Indice affidabilità</p>
          <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg bg-white/80 px-3 py-2 ring-1 ring-slate-200/80">
              <dt className="text-xs text-slate-500">Sample</dt>
              <dd className="mt-0.5 font-semibold tabular-nums text-slate-900">{rel.sample ?? '—'}</dd>
            </div>
            <div className="rounded-lg bg-white/80 px-3 py-2 ring-1 ring-slate-200/80">
              <dt className="text-xs text-slate-500">Indice</dt>
              <dd className="mt-0.5 font-semibold tabular-nums text-slate-900">
                {rel.index != null && Number.isFinite(rel.index)
                  ? Number(rel.index).toFixed(2)
                  : '—'}
              </dd>
            </div>
            <div className="rounded-lg bg-white/80 px-3 py-2 ring-1 ring-slate-200/80">
              <dt className="text-xs text-slate-500">Status</dt>
              <dd className="mt-0.5 font-semibold text-slate-900">{rel.status ?? '—'}</dd>
            </div>
            <div className="rounded-lg bg-white/80 px-3 py-2 ring-1 ring-slate-200/80">
              <dt className="text-xs text-slate-500">Livello</dt>
              <dd className="mt-0.5 font-semibold text-slate-900">{rel.level ?? '—'}</dd>
            </div>
          </dl>
        </div>
      )}

      {(matrix.warnings?.length ?? 0) > 0 && (
        <ul className="list-inside list-disc text-xs text-amber-800">
          {matrix.warnings!.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
