import { useMemo } from 'react'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import LabEChartsCore from '../cecchino-lab/LabEChartsCore'
import type { CecchinoV4Api, V4MeasureLeagueGroup, V4MeasureMarketGroup } from '../../lib/cecchinoV4Api'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from '../cecchino/cecchinoTodayStyles'
import { familyLabel, leagueName, v4Label, v4Mono } from './constants'
import { fmtCount, fmtDateTimeRome, fmtRoi, fmtRoiWithCi, fmtSignedPct } from './format'
import { useV4Query } from './useV4Query'
import { V4Empty, V4Error, V4Loading } from './V4States'

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

type Props = {
  api: CecchinoV4Api
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className={`${todayCard} ${todayCardPadding}`}>
      <p className={v4Label}>{label}</p>
      <p className={`${v4Mono} mt-1 text-xl font-semibold text-slate-900`}>{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-slate-500">{hint}</p> : null}
    </div>
  )
}

type TooltipParam = { dataIndex: number }

type ChartGroup = {
  label: string
  plays: number
  roi: number | null
  roi_lo: number | null
  roi_hi: number | null
  clv: number | null
  alarm?: boolean | null
}

function leagueGroups(rows: V4MeasureLeagueGroup[]): ChartGroup[] {
  return rows.map((r) => ({ ...r, label: leagueName(r.league_code) }))
}

function marketGroups(rows: V4MeasureMarketGroup[]): ChartGroup[] {
  return rows.map((r) => ({ ...r, label: r.label || familyLabel(r.market_family) }))
}

function roiBarOption(groups: ChartGroup[]): Record<string, unknown> {
  const labels = groups.map((g) => g.label)
  return {
    grid: { left: 56, right: 12, top: 16, bottom: 64 },
    tooltip: {
      trigger: 'axis',
      textStyle: { fontSize: 12 },
      formatter: (params: TooltipParam[] | TooltipParam) => {
        const p = Array.isArray(params) ? params[0] : params
        const g = groups[p?.dataIndex ?? -1]
        if (!g) return ''
        return `${g.label}<br/>ROI ${fmtRoiWithCi(g.roi, g.roi_lo, g.roi_hi)}<br/>${g.plays} giocate${
          g.clv != null ? `<br/>CLV ${fmtSignedPct(g.clv, 1)}` : ''
        }${g.alarm ? '<br/>Allarme CUSUM' : ''}`
      },
    },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: { fontSize: 12, interval: 0, rotate: labels.length > 6 ? 30 : 0 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 12, formatter: (v: number) => `${String(v).replace('.', ',')}%` },
      splitLine: { lineStyle: { color: '#e2e8f0' } },
    },
    series: [
      {
        type: 'bar',
        barMaxWidth: 36,
        data: groups.map((g) => ({
          value: g.roi == null ? null : Math.round(g.roi * 1000) / 10,
          itemStyle: {
            color: g.alarm ? '#d97706' : (g.roi ?? 0) >= 0 ? '#059669' : '#dc2626',
            borderRadius: [4, 4, 0, 0],
          },
        })),
        label: {
          show: true,
          position: 'top',
          fontSize: 12,
          formatter: (p: { dataIndex: number }) => fmtRoi(groups[p.dataIndex]?.roi),
        },
      },
    ],
  }
}

export function V4MeasureView({ api }: Props) {
  const q = useV4Query('measure', (signal) => api.getMeasureSummary({}, signal))
  const leagueOption = useMemo(() => (q.data ? roiBarOption(leagueGroups(q.data.by_league)) : null), [q.data])
  const marketOption = useMemo(() => (q.data ? roiBarOption(marketGroups(q.data.by_market)) : null), [q.data])

  if (q.loading) return <V4Loading label="Carico la misura…" rows={3} />
  if (q.error) return <V4Error message={q.error} onRetry={q.reload} />
  if (!q.data) return null
  const data = q.data

  if (data.totals.plays === 0) {
    return (
      <V4Empty
        title="Nessuna giocata regolata ancora: la misura parte con la prima shortlist sigillata"
        hint="CLV, ROI e allarmi compaiono qui dopo il primo regolamento."
      />
    )
  }

  return (
    <div className="space-y-4" data-testid="v4-measure">
      <div className="grid gap-3 sm:grid-cols-3">
        <Kpi label="Giocate regolate" value={fmtCount(data.totals.plays)} />
        <Kpi
          label="ROI"
          value={fmtRoiWithCi(data.totals.roi, data.totals.roi_lo, data.totals.roi_hi)}
          hint="Intervallo bootstrap a blocchi per giornata"
        />
        <Kpi label="CLV medio" value={fmtSignedPct(data.totals.clv, 1)} hint="Quota presa contro quota di chiusura" />
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        <section className={`${todayCard} ${todayCardPadding} space-y-2`}>
          <h3 className={todaySectionTitle}>ROI per campionato</h3>
          {leagueOption && data.by_league.length > 0 ? (
            <LabEChartsCore echarts={echarts} option={leagueOption} style={{ height: 260 }} notMerge lazyUpdate />
          ) : (
            <p className="text-sm text-slate-500">Nessun campionato con giocate regolate.</p>
          )}
        </section>
        <section className={`${todayCard} ${todayCardPadding} space-y-2`}>
          <h3 className={todaySectionTitle}>ROI per famiglia di mercato</h3>
          {marketOption && data.by_market.length > 0 ? (
            <LabEChartsCore echarts={echarts} option={marketOption} style={{ height: 260 }} notMerge lazyUpdate />
          ) : (
            <p className="text-sm text-slate-500">Nessuna famiglia con giocate regolate.</p>
          )}
        </section>
      </div>

      <section className={`${todayCard} ${todayCardPadding} space-y-2`}>
        <h3 className={todaySectionTitle}>Allarmi CUSUM</h3>
        {data.alerts.length === 0 ? (
          <p className="text-sm text-slate-500">Nessun campionato o mercato in decadimento.</p>
        ) : (
          <ul className="space-y-2">
            {data.alerts.map((a) => (
              <li
                key={`${a.scope}-${a.key}`}
                className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
                data-testid="v4-alert"
              >
                <span className="font-semibold">
                  {a.scope === 'league' ? `Campionato ${leagueName(a.key)}` : `Mercato ${familyLabel(a.key)}`}
                </span>
                : {a.sentence}
                <span className={`${v4Mono} block text-xs text-amber-800`}>
                  {a.plays} giocate · ROI {fmtRoi(a.roi)}
                  {a.alarm_at ? ` · allarme dal ${fmtDateTimeRome(a.alarm_at)}` : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {data.postmortem && data.postmortem.length > 0 ? (
        <section className={`${todayCard} ${todayCardPadding} space-y-2`}>
          <h3 className={todaySectionTitle}>Post-mortem della settimana</h3>
          <p className={todaySectionSubtitle}>Cosa ha funzionato e cosa no, in parole.</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-800">
            {data.postmortem.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
