import { useState } from 'react'
import type { CecchinoDataQuality } from '../../lib/cecchinoApi'
import {
  formatWdl,
  INPUT_SNAPSHOT_CONTEXT_KEYS,
  normalizeContextSlice,
  statusBadgeClass,
  statusLabel,
} from '../../lib/cecchinoUtils'

type Props = {
  inputSnapshot: Record<string, unknown>
  dataQuality?: CecchinoDataQuality | null
}

const SAMPLE_KEYS: Record<string, keyof CecchinoDataQuality> = {
  home_context: 'sample_home_context',
  away_context: 'sample_away_context',
  home_total: 'sample_home_total',
  away_total: 'sample_away_total',
  home_recent_context_5: 'sample_home_recent_context',
  away_recent_context_5: 'sample_away_recent_context',
  home_recent_total_6: 'sample_home_recent_total',
  away_recent_total_6: 'sample_away_recent_total',
}

export function CecchinoInputDataPanel({ inputSnapshot, dataQuality }: Props) {
  const [open, setOpen] = useState(true)

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
                <th className="py-1 pr-2">Stato</th>
              </tr>
            </thead>
            <tbody>
              {INPUT_SNAPSHOT_CONTEXT_KEYS.map((key) => {
                const slice = normalizeContextSlice(key, inputSnapshot[key])
                const sampleKey = SAMPLE_KEYS[key]
                const dqCount =
                  sampleKey && dataQuality?.[sampleKey] != null
                    ? Number(dataQuality[sampleKey])
                    : null
                const count = slice?.sampleCount ?? dqCount
                const target = slice?.targetSample ?? null
                const sampleLabel =
                  count != null
                    ? target != null
                      ? `${count} / ${target}`
                      : String(count)
                    : '—'
                const rowStatus = slice?.status ?? (count === 0 ? 'insufficient_data' : null)

                return (
                  <tr key={key} className="border-t border-slate-50">
                    <td className="py-1.5 pr-2 font-medium">{slice?.label ?? key}</td>
                    <td className="py-1.5 pr-2 tabular-nums">
                      {slice?.wdl ? formatWdl(slice.wdl) : '—'}
                    </td>
                    <td className="py-1.5 pr-2 tabular-nums">{sampleLabel}</td>
                    <td className="py-1.5 pr-2">
                      {rowStatus ? (
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${statusBadgeClass(rowStatus)}`}
                        >
                          {statusLabel(rowStatus)}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
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
