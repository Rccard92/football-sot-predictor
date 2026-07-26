import { motion } from 'framer-motion'
import ReactECharts from 'echarts-for-react'
import type { CecchinoLabOverview } from '../../lib/cecchinoLabApi'
import { qualityLabel } from './labTheme'

type Props = {
  overview: CecchinoLabOverview | null
  loading: boolean
  error: string | null
  onGoImport: () => void
}

function KpiCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <motion.div
      className="lab-card p-4"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <div className="text-xs uppercase tracking-wider" style={{ color: 'var(--lab-muted)' }}>
        {label}
      </div>
      <div className="mt-2 text-3xl font-semibold tabular-nums" style={{ color: 'var(--lab-cyan)' }}>
        {value}
      </div>
      {hint ? (
        <div className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
          {hint}
        </div>
      ) : null}
    </motion.div>
  )
}

export function OverviewTab({ overview, loading, error, onGoImport }: Props) {
  if (loading) {
    return <div className="p-8 text-sm" style={{ color: 'var(--lab-muted)' }}>Caricamento overview…</div>
  }
  if (error) {
    return <div className="p-8 text-sm" style={{ color: 'var(--lab-err)' }}>{error}</div>
  }
  if (!overview || overview.is_empty) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 px-6 py-20 text-center">
        <div
          className="flex h-16 w-16 items-center justify-center rounded-2xl text-2xl"
          style={{ background: 'var(--lab-cyan-dim)', color: 'var(--lab-cyan)' }}
        >
          ⧉
        </div>
        <h2 className="text-2xl font-semibold">Nessun dataset storico</h2>
        <p className="max-w-md text-sm" style={{ color: 'var(--lab-muted)' }}>
          Importa i CSV di football-data.co.uk per costruire l&apos;archivio isolato del Cecchino Lab.
          Nessuna formula e nessun impatto su Cecchino Today.
        </p>
        <button type="button" className="lab-btn" onClick={onGoImport}>
          Importa CSV
        </button>
      </div>
    )
  }

  const coverageOption = {
    backgroundColor: 'transparent',
    textStyle: { color: '#8aa0b5' },
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    xAxis: {
      type: 'category',
      data: ['1X2 pre', 'O/U 2.5 pre'],
      axisLine: { lineStyle: { color: 'rgba(120,190,220,0.2)' } },
    },
    yAxis: {
      type: 'value',
      max: 100,
      axisLabel: { formatter: '{value}%' },
      splitLine: { lineStyle: { color: 'rgba(120,190,220,0.08)' } },
    },
    series: [
      {
        type: 'bar',
        data: [overview.bet365_1x2_coverage_pct, overview.bet365_ou25_coverage_pct],
        itemStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: '#2ee6ff' },
              { offset: 1, color: '#1a8fa8' },
            ],
          },
          borderRadius: [6, 6, 0, 0],
        },
        barWidth: 42,
      },
    ],
  }

  const completenessOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'pie',
        radius: ['48%', '72%'],
        label: { color: '#e8f1f8' },
        data: [
          { name: 'Complete', value: overview.matches_complete, itemStyle: { color: '#3dd68c' } },
          { name: 'Incomplete', value: overview.matches_incomplete, itemStyle: { color: '#f0b429' } },
        ],
      },
    ],
  }

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <KpiCard label="Campionati" value={overview.competitions_count} />
        <KpiCard label="Stagioni" value={overview.seasons_count} />
        <KpiCard label="Dataset" value={overview.datasets_count} />
        <KpiCard label="Partite" value={overview.matches_total} />
        <KpiCard
          label="Completezza"
          value={`${overview.completeness.complete_pct}%`}
          hint={`${overview.matches_complete} complete`}
        />
        <KpiCard
          label="Anomalie"
          value={overview.anomalies_total}
          hint={`${overview.anomalies_errors} err · ${overview.anomalies_warnings} warn`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="lab-card p-4">
          <h3 className="mb-2 text-sm font-semibold" style={{ color: 'var(--lab-cyan)' }}>
            Coverage Bet365
          </h3>
          <ReactECharts option={coverageOption} style={{ height: 240 }} />
        </div>
        <div className="lab-card p-4">
          <h3 className="mb-2 text-sm font-semibold" style={{ color: 'var(--lab-cyan)' }}>
            Distribuzione completezza
          </h3>
          <ReactECharts option={completenessOption} style={{ height: 240 }} />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="lab-card p-4">
          <h3 className="mb-3 text-sm font-semibold">Ultimi import</h3>
          {overview.recent_imports.length === 0 ? (
            <p className="text-sm" style={{ color: 'var(--lab-muted)' }}>Nessun import recente.</p>
          ) : (
            <ul className="space-y-2">
              {overview.recent_imports.map((imp) => (
                <li
                  key={imp.id}
                  className="flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm"
                  style={{ background: 'rgba(0,0,0,0.18)' }}
                >
                  <div>
                    <div className="font-medium">{imp.source_filename}</div>
                    <div className="text-xs" style={{ color: 'var(--lab-muted)' }}>
                      {imp.competition_name} · {imp.season_label} · +{imp.rows_imported} righe
                    </div>
                  </div>
                  <span className={`rounded-md px-2 py-0.5 text-xs ${imp.status === 'completed' ? 'lab-badge-ok' : 'lab-badge-muted'}`}>
                    {imp.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="lab-card p-4 space-y-4">
          <div>
            <h3 className="mb-2 text-sm font-semibold">Migliore qualità</h3>
            <div className="space-y-1">
              {overview.best_quality_datasets.map((d) => (
                <div key={d.id} className="flex justify-between text-sm">
                  <span>
                    {d.competition_name} {d.season_label}
                  </span>
                  <span className={`rounded px-2 text-xs ${d.data_quality_status === 'complete' ? 'lab-badge-ok' : 'lab-badge-warn'}`}>
                    {qualityLabel(d.data_quality_status)}
                  </span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <h3 className="mb-2 text-sm font-semibold">Peggiore qualità</h3>
            <div className="space-y-1">
              {overview.worst_quality_datasets.map((d) => (
                <div key={d.id} className="flex justify-between text-sm">
                  <span>
                    {d.competition_name} {d.season_label}
                  </span>
                  <span className={`rounded px-2 text-xs lab-badge-warn`}>
                    {qualityLabel(d.data_quality_status)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
