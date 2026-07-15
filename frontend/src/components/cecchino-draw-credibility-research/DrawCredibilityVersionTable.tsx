import { useState } from 'react'
import type { VersionDistributionBlock } from '../../lib/cecchinoDrawCredibilityResearchApi'

type Props = {
  selected: VersionDistributionBlock
  globalDistribution?: VersionDistributionBlock
}

const LABELS: Record<string, string> = {
  cecchino_output: 'Cecchino output',
  balance_analysis: 'Balance analysis',
  goal_markets: 'Goal markets',
  kpi_panel: 'KPI panel',
  payload_structure: 'Payload structure',
}

function formatVersion(version: string): string {
  return version === 'null' ? 'Non dichiarata' : version
}

function DistributionBlock({
  title,
  distribution,
}: {
  title: string
  distribution: VersionDistributionBlock
}) {
  return (
    <div className="space-y-4">
      <p className="text-xs font-medium text-slate-600">{title}</p>
      {Object.entries(distribution).map(([key, rows]) => (
        <div key={key}>
          <p className="text-xs font-medium text-slate-600">{LABELS[key] ?? key}</p>
          <div className="mt-1 overflow-x-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="px-2 py-1.5 font-medium">Versione</th>
                  <th className="px-2 py-1.5 font-medium">Count</th>
                  <th className="px-2 py-1.5 font-medium">%</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={`${key}-${row.version}`} className="border-t border-slate-100">
                    <td className="px-2 py-1.5 font-mono text-[11px]">{formatVersion(row.version)}</td>
                    <td className="px-2 py-1.5 tabular-nums">{row.count}</td>
                    <td className="px-2 py-1.5 tabular-nums">{row.pct.toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}

export function DrawCredibilityVersionTable({ selected, globalDistribution }: Props) {
  const [showGlobal, setShowGlobal] = useState(false)

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-800">
          Distribuzione versioni — coorte selezionata
        </h3>
        {globalDistribution ? (
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={showGlobal}
              onChange={(e) => setShowGlobal(e.target.checked)}
              className="rounded border-slate-300"
            />
            Mostra universo compatibile globale
          </label>
        ) : null}
      </div>
      <div className="mt-3">
        {showGlobal && globalDistribution ? (
          <DistributionBlock title="Universo compatibile globale" distribution={globalDistribution} />
        ) : (
          <DistributionBlock title="Coorte selezionata" distribution={selected} />
        )}
      </div>
    </section>
  )
}
