import type { ApiFootballScanDiagnostic } from '../../lib/api'

type Props = {
  diagnostics: ApiFootballScanDiagnostic[] | null
}

export function DirectScanDiagnosticsTable({ diagnostics }: Props) {
  if (!diagnostics || diagnostics.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
        Nessuna diagnostica disponibile. Esegui uno scan: i dettagli degli endpoint interrogati compaiono qui dopo il
        completamento del POST.
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
        <thead className="bg-slate-50 text-xs font-semibold uppercase text-slate-600">
          <tr>
            <th className="px-3 py-2">Endpoint</th>
            <th className="px-3 py-2">Parametri</th>
            <th className="px-3 py-2">Stato</th>
            <th className="px-3 py-2">Campi trovati</th>
            <th className="px-3 py-2">Errore</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {diagnostics.map((d, i) => (
            <tr key={`${d.endpoint}-${i}`} className="text-slate-800">
              <td className="px-3 py-2 font-mono text-xs">{d.endpoint}</td>
              <td className="max-w-xs truncate px-3 py-2 font-mono text-xs" title={JSON.stringify(d.params)}>
                {JSON.stringify(d.params)}
              </td>
              <td className="px-3 py-2">{d.status}</td>
              <td className="px-3 py-2">{d.fields_found}</td>
              <td className="max-w-md truncate px-3 py-2 text-xs text-rose-700" title={d.error ?? ''}>
                {d.error ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
