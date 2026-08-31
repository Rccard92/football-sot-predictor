import ReactECharts from 'echarts-for-react'
import { roiColor } from '../overview/overviewTheme'
import type { LpaLatestPayload } from '../../../lib/leaguePatternAnalysisApi'

type Props = {
  heatmap: LpaLatestPayload['heatmap']
  onSelectCell?: (patternId: string, competition: string) => void
}

export function PatternLeagueHeatmap({ heatmap, onSelectCell }: Props) {
  const patternIds = heatmap.pattern_ids || []
  const competitions = heatmap.competitions || []
  const cellMap = new Map(
    (heatmap.cells || []).map((c) => [`${c.pattern_id}||${c.competition}`, c]),
  )

  const data: Array<[number, number, number | null]> = []
  patternIds.forEach((pid, yi) => {
    competitions.forEach((comp, xi) => {
      const cell = cellMap.get(`${pid}||${comp}`)
      const v = cell?.roi_pct ?? null
      data.push([xi, yi, v])
    })
  })

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      backgroundColor: '#0f1c2c',
      borderColor: 'rgba(255,255,255,0.12)',
      textStyle: { color: '#e8eef5', fontSize: 12 },
      formatter: (params: { data?: [number, number, number | null] }) => {
        const d = params.data
        if (!d) return ''
        const [xi, yi] = d
        const pid = patternIds[yi]
        const comp = competitions[xi]
        const cell = cellMap.get(`${pid}||${comp}`)
        if (!cell) return `${pid} × ${comp}<br/>Nessun dato`
        const low = cell.low_sample ? '<br/><em>Low sample</em>' : ''
        const roi =
          cell.roi_pct == null
            ? '—'
            : `${cell.roi_pct > 0 ? '+' : ''}${cell.roi_pct.toFixed(1)}%`
        return (
          `<strong>${pid} × ${comp}</strong><br/>` +
          `N = ${cell.n}<br/>ROI = ${roi}<br/>Profit = ${Number(cell.profit_1u || 0).toFixed(2)}u<br/>` +
          `Positive seasons = ${cell.positive_seasons ?? 0}/${cell.seasons_with_bets ?? 0}<br/>` +
          `Worst season ROI = ${
            cell.worst_season_roi_pct == null
              ? '—'
              : `${cell.worst_season_roi_pct.toFixed(1)}%`
          }` +
          low
        )
      },
    },
    grid: { left: 56, right: 24, top: 16, bottom: 96 },
    xAxis: {
      type: 'category',
      data: competitions,
      axisLabel: {
        color: '#8aa0b5',
        rotate: 45,
        fontSize: 10,
      },
      splitArea: { show: false },
    },
    yAxis: {
      type: 'category',
      data: patternIds,
      axisLabel: { color: '#8aa0b5', fontSize: 11 },
    },
    visualMap: {
      min: -40,
      max: 40,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: {
        color: ['#ef4444', '#1a2f47', '#22c55e'],
      },
      textStyle: { color: '#8aa0b5' },
    },
    series: [
      {
        type: 'heatmap',
        data,
        label: {
          show: true,
          formatter: (p: { data?: [number, number, number | null] }) => {
            const d = p.data
            if (!d || d[2] == null) return ''
            const cell = cellMap.get(`${patternIds[d[1]]}||${competitions[d[0]]}`)
            const n = cell?.n ?? 0
            if (n <= 0) return ''
            return `${d[2] > 0 ? '+' : ''}${d[2].toFixed(0)}`
          },
          color: '#e8eef5',
          fontSize: 9,
        },
        emphasis: {
          itemStyle: { borderColor: '#38bdf8', borderWidth: 1 },
        },
      },
    ],
  }

  return (
    <div className="lab-card p-4">
      <div className="mb-2 text-sm font-semibold">Heatmap Pattern × Campionato (ROI pooled)</div>
      <p className="mb-3 text-xs" style={{ color: 'var(--lab-muted)' }}>
        Colore = ROI pooled 4 stagioni. N sempre nel tooltip
        {heatmap.low_sample_n != null ? ` · low-sample se N < ${heatmap.low_sample_n}` : ''}.
      </p>
      <ReactECharts
        option={option}
        style={{ height: Math.max(320, patternIds.length * 28 + 120), width: '100%' }}
        onEvents={{
          click: (params: { data?: [number, number, number | null] }) => {
            const d = params.data
            if (!d || !onSelectCell) return
            onSelectCell(patternIds[d[1]], competitions[d[0]])
          },
        }}
      />
      <div className="mt-2 text-[10px]" style={{ color: roiColor(1) }}>
        Verde = ROI positivo · Rosso = ROI negativo
      </div>
    </div>
  )
}
