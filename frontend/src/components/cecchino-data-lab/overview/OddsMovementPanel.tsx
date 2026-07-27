import ReactECharts from 'echarts-for-react'
import type { CecchinoLabAnalyticsOverview } from '../../../lib/cecchinoLabApi'
import { MetricTooltip } from './MetricTooltip'
import { formatPct, overviewColors } from './overviewTheme'

type Props = {
  movement: CecchinoLabAnalyticsOverview['odds_movement']
  margins: CecchinoLabAnalyticsOverview['margins']
}

const DIST_LABELS: Record<string, string> = {
  strong_shorten: 'Forte accorc. ≤−10%',
  shorten: 'Accorc. −10/−3%',
  stable: 'Stabile −3/+3%',
  lengthen: 'Allung. +3/+10%',
  strong_lengthen: 'Forte allung. ≥+10%',
}

export function OddsMovementPanel({ movement, margins }: Props) {
  const dist = movement.distribution || []
  const option = {
    backgroundColor: 'transparent',
    textStyle: { color: '#8aa0b5' },
    tooltip: { trigger: 'axis', backgroundColor: '#0f1c2c', borderColor: 'rgba(120,190,220,0.2)' },
    grid: { left: 48, right: 16, top: 24, bottom: 60 },
    xAxis: {
      type: 'category',
      data: dist.map((d) => DIST_LABELS[d.bucket] || d.bucket),
      axisLabel: { rotate: 25, fontSize: 10 },
      axisLine: { lineStyle: { color: 'rgba(120,190,220,0.2)' } },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: 'rgba(120,190,220,0.08)' } },
    },
    series: [
      {
        type: 'bar',
        data: dist.map((d) => d.count),
        itemStyle: {
          color: (params: { dataIndex: number }) => {
            const colors = [overviewColors.home, overviewColors.over, overviewColors.draw, overviewColors.away, overviewColors.negative]
            return colors[params.dataIndex] || overviewColors.accent
          },
          borderRadius: [4, 4, 0, 0],
        },
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
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.16em]" style={{ color: 'var(--lab-cyan)' }}>
        Pre-closing → Closing
      </h2>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
        <div>
          <div style={{ color: 'var(--lab-muted)' }}>
            <MetricTooltip metric="pre_closing">Mov. medio 1</MetricTooltip>
          </div>
          <div className="text-lg font-semibold tabular-nums">{movement.average_home_movement_pct?.toFixed(2) ?? '—'}%</div>
        </div>
        <div>
          <div style={{ color: 'var(--lab-muted)' }}>Mov. medio X</div>
          <div className="text-lg font-semibold tabular-nums">{movement.average_draw_movement_pct?.toFixed(2) ?? '—'}%</div>
        </div>
        <div>
          <div style={{ color: 'var(--lab-muted)' }}>Mov. medio 2</div>
          <div className="text-lg font-semibold tabular-nums">{movement.average_away_movement_pct?.toFixed(2) ?? '—'}%</div>
        </div>
        <div>
          <div style={{ color: 'var(--lab-muted)' }}>
            <MetricTooltip metric="favorite">Favorite accorciate</MetricTooltip>
          </div>
          <div className="text-lg font-semibold tabular-nums">{formatPct(movement.favorite_shortened_pct)}</div>
        </div>
        <div>
          <div style={{ color: 'var(--lab-muted)' }}>Esiti vincenti accorciati</div>
          <div className="text-lg font-semibold tabular-nums">{formatPct(movement.winning_selection_shortened_pct)}</div>
        </div>
        <div>
          <div style={{ color: 'var(--lab-muted)' }}>Mov. medio vincente</div>
          <div className="text-lg font-semibold tabular-nums">{movement.average_winner_movement_pct?.toFixed(2) ?? '—'}%</div>
        </div>
        <div>
          <div style={{ color: 'var(--lab-muted)' }}>
            <MetricTooltip metric="margin">Margine pre medio</MetricTooltip>
          </div>
          <div className="text-lg font-semibold tabular-nums">{formatPct(margins.average_pre_closing_margin_pct)}</div>
        </div>
        <div>
          <div style={{ color: 'var(--lab-muted)' }}>Δ pre → closing</div>
          <div className="text-lg font-semibold tabular-nums">
            {margins.average_pre_to_closing_delta_pp != null
              ? `${margins.average_pre_to_closing_delta_pp > 0 ? '+' : ''}${margins.average_pre_to_closing_delta_pp.toFixed(1)} pp`
              : '—'}
          </div>
        </div>
      </div>
      <div className="text-xs mb-2" style={{ color: 'var(--lab-muted)' }}>
        Campione movimento: {movement.sample_size.toLocaleString('it-IT')} partite · quote senza C = pre-closing (non opening)
      </div>
      {movement.sample_size === 0 ? (
        <div className="py-8 text-center text-sm" style={{ color: 'var(--lab-muted)' }}>
          Nessun movimento calcolabile (serve pre e closing).
        </div>
      ) : (
        <ReactECharts option={option} style={{ height: 240 }} opts={{ renderer: 'canvas' }} />
      )}
    </section>
  )
}
