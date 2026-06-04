import { useState } from 'react'
import type { CecchinoContextSnapshot, CecchinoDataQuality } from '../../lib/api'

const CONTEXT_ROWS: { key: string; label: string; sampleKey: keyof CecchinoDataQuality }[] = [
  { key: 'home_context', label: 'Casa (split casalinghe)', sampleKey: 'sample_home_context' },
  { key: 'away_context', label: 'Trasferta (split esterne)', sampleKey: 'sample_away_context' },
  { key: 'home_total', label: 'Totali casa', sampleKey: 'sample_home_total' },
  { key: 'away_total', label: 'Totali trasferta', sampleKey: 'sample_away_total' },
  {
    key: 'home_recent_context_5',
    label: 'Ultime 5 casalinghe',
    sampleKey: 'sample_home_recent_context',
  },
  {
    key: 'away_recent_context_5',
    label: 'Ultime 5 esterne',
    sampleKey: 'sample_away_recent_context',
  },
  { key: 'home_recent_total_6', label: 'Ultime 6 totali casa', sampleKey: 'sample_home_recent_total' },
  { key: 'away_recent_total_6', label: 'Ultime 6 totali trasferta', sampleKey: 'sample_away_recent_total' },
]

function fmtWdl(w: { wins: number; draws: number; losses: number }) {
  return `${w.wins}V / ${w.draws}X / ${w.losses}S`
}

type Props = {
  inputSnapshot: Record<string, unknown>
  dataQuality?: CecchinoDataQuality | null
}

export function CecchinoInputDataPanel({ inputSnapshot, dataQuality }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-slate-800"
      >
        Dati usati dal Cecchino
        <span className="text-slate-500">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="border-t border-slate-100 px-4 pb-4">
          <table className="mt-2 w-full text-left text-xs text-slate-700">
            <thead>
              <tr className="text-[11px] uppercase text-slate-500">
                <th className="py-1 pr-2">Contesto</th>
                <th className="py-1 pr-2">Record W/D/L</th>
                <th className="py-1 pr-2">Campione</th>
              </tr>
            </thead>
            <tbody>
              {CONTEXT_ROWS.map((row) => {
                const snap = inputSnapshot[row.key] as CecchinoContextSnapshot | undefined
                const wdl = snap?.wdl
                const target = snap?.target_sample
                const count =
                  dataQuality?.[row.sampleKey] ?? snap?.sample_count ?? '—'
                const sampleLabel =
                  target != null ? `${count} / ${target}` : String(count)
                return (
                  <tr key={row.key} className="border-t border-slate-50">
                    <td className="py-1.5 pr-2 font-medium">{row.label}</td>
                    <td className="py-1.5 pr-2 tabular-nums">
                      {wdl ? fmtWdl(wdl) : '—'}
                    </td>
                    <td className="py-1.5 pr-2 tabular-nums">{sampleLabel}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {dataQuality?.warnings && dataQuality.warnings.length > 0 && (
            <ul className="mt-2 list-inside list-disc text-[11px] text-amber-800">
              {dataQuality.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
