import ReactECharts from 'echarts-for-react'
import type { CecchinoLabAnalyticsOverview } from '../../../lib/cecchinoLabApi'
import { MetricTooltip } from './MetricTooltip'
import { formatPct } from './overviewTheme'

type Props = { favorite: CecchinoLabAnalyticsOverview['favorite'] }

export function MarketCalibration({ favorite }: Props) {
  const buckets = favorite.buckets || []
  const option = {
    backgroundColor: 'transparent',
    textStyle: { color: '#8aa0b5', fontFamily: 'IBM Plex Sans, sans-serif' },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#0f1c2c',
      borderColor: 'rgba(120,190,220,0.2)',
      textStyle: { color: '#e8f1f8' },
    },
    legend: {
      data: ['Prob. implicita norm.', 'Win rate reale', 'Gap (pp)'],
      textStyle: { color: '#8aa0b5' },
      top: 0,
    },
    grid: { left: 48, right: 24, top: 40, bottom: 40 },
    xAxis: {
      type: 'category',
      data: buckets.map((b) => b.bucket),
      axisLine: { lineStyle: { color: 'rgba(120,190,220,0.2)' } },
    },
    yAxis: {
      type: 'value',
      name: '%',
      splitLine: { lineStyle: { color: 'rgba(120,190,220,0.08)' } },
    },
    series: [
      {
        name: 'Prob. implicita norm.',
        type: 'bar',
        data: buckets.map((b) => b.normalized_implied_probability),
        itemStyle: { color: 'rgba(46,230,255,0.55)' },
      },
      {
        name: 'Win rate reale',
        type: 'bar',
        data: buckets.map((b) => b.actual_win_rate),
        itemStyle: { color: 'rgba(61,214,140,0.7)' },
      },
      {
        name: 'Gap (pp)',
        type: 'line',
        data: buckets.map((b) => b.calibration_gap_pp),
        itemStyle: { color: '#f0b429' },
        lineStyle: { width: 2 },
      },
    ],
  }

  return (
    <section
      className="rounded-2xl p-4 sm:p-5"
      style={{
        background: 'linear-gradient(160deg, rgba(21,38,58,0.95), rgba(12,24,38,0.98))',
        border: '1px solid var(--lab-border)',
      }}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-[0.16em]" style={{ color: 'var(--lab-cyan)' }}>
          Market Calibration
        </h2>
        <div className="text-xs" style={{ color: 'var(--lab-muted)' }}>
          Hit rate favorita: <strong style={{ color: 'var(--lab-text)' }}>{formatPct(favorite.hit_rate)}</strong>
          {' · '}
          <MetricTooltip metric="calibration_gap">Gap calibrazione</MetricTooltip>
        </div>
      </div>
      <div className="mb-3 grid gap-2 text-xs sm:grid-cols-4" style={{ color: 'var(--lab-muted)' }}>
        <div>Univoche: {favorite.unique_count.toLocaleString('it-IT')}</div>
        <div>Casa fav. {formatPct(favorite.home_favorite_pct)}</div>
        <div>Trasf. fav. {formatPct(favorite.away_favorite_pct)}</div>
        <div>X fav. {formatPct(favorite.draw_favorite_pct)}</div>
      </div>
      {buckets.length === 0 || buckets.every((b) => b.matches === 0) ? (
        <div className="py-10 text-center text-sm" style={{ color: 'var(--lab-muted)' }}>
          Nessun dato favorita nel campione.
        </div>
      ) : (
        <ReactECharts option={option} style={{ height: 280 }} opts={{ renderer: 'canvas' }} />
      )}
    </section>
  )
}
