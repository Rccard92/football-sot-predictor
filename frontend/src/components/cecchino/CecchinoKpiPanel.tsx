import { Fragment, useState } from 'react'
import type { CecchinoKpiPanel as CecchinoKpiPanelType, CecchinoKpiRow } from '../../lib/cecchinoApi'

function fmtCell(v: string | number | null | undefined, asDecimal = false): string {
  if (v == null || v === '') return '—'
  if (typeof v === 'string') return v
  if (asDecimal) return Number(v).toFixed(2)
  return String(v)
}

function RowDetail({ row }: { row: CecchinoKpiRow }) {
  const [open, setOpen] = useState(false)
  const bm = row.bookmakers || {}
  const names = Object.keys(bm)
  if (!names.length && row.book_average == null) return null
  return (
    <tr className="bg-slate-900/40">
      <td colSpan={6} className="px-2 py-1 text-xs text-slate-300">
        <button
          type="button"
          className="text-sky-300 underline"
          onClick={() => setOpen((o) => !o)}
        >
          {open ? 'Nascondi' : 'Mostra'} quote bookmaker
        </button>
        {open && (
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {names.map((n) => (
              <div key={n}>
                <span className="font-medium text-slate-200">{n}:</span>{' '}
                {fmtCell(bm[n] as number)}
              </div>
            ))}
            <div>
              <span className="font-medium text-amber-200">Media book:</span>{' '}
              {fmtCell(row.book_average as number)}
            </div>
          </div>
        )}
      </td>
    </tr>
  )
}

type Props = {
  panel: CecchinoKpiPanelType
  bookmakerStatus?: string
}

export function CecchinoKpiPanel({ panel, bookmakerStatus }: Props) {
  const status = bookmakerStatus || panel.bookmaker_status || 'not_available'
  const isAnalysis = (label: string) =>
    label === 'ANALISI DEL MATCH' || label === 'DELTA DI FORZA'

  return (
    <section className="overflow-hidden rounded-lg border border-slate-500 shadow-lg">
      <div className="bg-[#1e3a5f] px-4 py-3 text-center">
        <h3 className="text-sm font-bold tracking-wide text-white">PANNELLO KPI</h3>
        {status === 'partial' && (
          <span className="mt-1 inline-block rounded bg-amber-500/90 px-2 py-0.5 text-xs text-white">
            Quote bookmaker parziali
          </span>
        )}
        {status === 'not_available' && (
          <p className="mt-1 text-xs text-amber-200">Quote bookmaker non disponibili — colonna BOOK vuota</p>
        )}
      </div>
      <div className="overflow-x-auto bg-[#163352]">
        <table className="w-full min-w-[640px] border-collapse text-center text-xs text-white">
          <thead>
            <tr className="border-b border-slate-400/60 bg-[#0f2847]">
              <th className="border-r border-slate-500/50 px-2 py-2 w-28" />
              <th className="border-r border-slate-500/50 px-2 py-2">STATISTICA</th>
              <th className="border-r border-slate-500/50 px-2 py-2">CECCHINO</th>
              <th className="border-r border-slate-500/50 px-2 py-2">BOOK</th>
              <th className="border-r border-slate-500/50 px-2 py-2">MEDIA</th>
              <th className="px-2 py-2">EDGE</th>
            </tr>
          </thead>
          <tbody>
            {(panel.rows || []).map((row) => (
              <Fragment key={row.label}>
                <tr className="border-b border-slate-500/40 hover:bg-slate-800/30">
                  <td className="border-r border-slate-500/50 px-2 py-2 text-left font-semibold text-slate-100">
                    {row.label}
                  </td>
                  <td className="border-r border-slate-500/50 px-2 py-2">
                    {fmtCell(row.statistica, !isAnalysis(row.label) && typeof row.statistica === 'number')}
                  </td>
                  <td className="border-r border-slate-500/50 px-2 py-2 font-medium text-amber-100">
                    {fmtCell(row.cecchino, !isAnalysis(row.label) && typeof row.cecchino === 'number')}
                  </td>
                  <td className="border-r border-slate-500/50 px-2 py-2">
                    {fmtCell(row.book, !isAnalysis(row.label) && typeof row.book === 'number')}
                  </td>
                  <td className="border-r border-slate-500/50 px-2 py-2">
                    {fmtCell(row.media, !isAnalysis(row.label) && typeof row.media === 'number')}
                  </td>
                  <td className="px-2 py-2 text-emerald-200">
                    {row.edge != null ? `${Number(row.edge).toFixed(2)}%` : '—'}
                  </td>
                </tr>
                {!isAnalysis(row.label) && <RowDetail row={row} />}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <div className="border-t border-slate-500/50 bg-[#0f2847] px-4 py-3 text-xs text-slate-200">
        <p className="font-semibold text-white">METRICA PERCENTUALE DELTA DI FORZA</p>
        <ul className="mt-2 space-y-1">
          {(panel.delta_force_legend || []).map((item) => (
            <li key={item.range}>
              <span className="text-sky-200">{item.range}</span>: {item.label}
            </li>
          ))}
        </ul>
        {(panel.warnings ?? []).length > 0 && (
          <ul className="mt-2 list-disc pl-4 text-amber-200">
            {(panel.warnings ?? []).map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
