import { useMemo, useState } from 'react'
import type { V4MarketRow } from '../../lib/cecchinoV4Api'
import { capitalize, fmtInterval, fmtLine, fmtProfit, fmtQuota } from './format'
import { statLabel } from './constants'
import {
  compareByProfitDesc,
  defaultLine,
  deriveUnderRow,
  splitMarkets,
  type StatGroup,
} from './marketKeys'
import { V4VerdictChip } from './V4Chips'

type Props = {
  markets: V4MarketRow[]
  homeTeam: string
  awayTeam: string
  bestKey: string | null
}

const th = 'px-3 py-2 text-left text-base font-semibold uppercase tracking-wide text-slate-500'
const td = 'px-3 py-2 text-base text-slate-800'
const num = `${td} text-right tabular-nums`

function profitTone(v: number | null): string {
  if (v == null) return 'text-slate-400'
  if (v >= 0.03) return 'font-semibold text-emerald-700'
  if (v < 0) return 'text-slate-500'
  return 'text-slate-700'
}

function MarketRowView({ row, highlight }: { row: V4MarketRow; highlight: boolean }) {
  return (
    <tr className={highlight ? 'bg-emerald-50/70' : 'odd:bg-white even:bg-slate-50/60'} data-testid="v4-market-row">
      <td className={`${td} font-medium text-slate-900`}>{row.label}</td>
      <td className={num}>{fmtInterval(row.p, row.lo, row.hi)}</td>
      <td className={num}>{fmtQuota(row.quota_bet365)}</td>
      <td className={num}>{fmtQuota(row.quota_betfair)}</td>
      <td className={`${num} ${profitTone(row.expected_profit)}`}>{fmtProfit(row.expected_profit)}</td>
      <td className={td}>
        <V4VerdictChip verdict={row.verdict} label={row.verdict_label} />
      </td>
    </tr>
  )
}

function sideName(side: StatGroup['side'], home: string, away: string): string {
  if (side === 'home') return home
  if (side === 'away') return away
  return 'Totale'
}

function StatGroupRows({
  group,
  homeTeam,
  awayTeam,
  bestKey,
}: {
  group: StatGroup
  homeTeam: string
  awayTeam: string
  bestKey: string | null
}) {
  const [line, setLine] = useState(() => defaultLine(group, bestKey))
  const team = sideName(group.side, homeTeam, awayTeam)
  const title = `${capitalize(statLabel(group.stat))} · ${team}`
  const over = group.over[line] ?? null
  const under =
    group.under[line] ??
    (over ? deriveUnderRow(over, `${team} under ${fmtLine(line)} ${statLabel(group.stat)}`) : null)

  return (
    <>
      <tr className="bg-slate-100/80" data-testid="v4-stat-group">
        <td colSpan={6} className="px-3 py-2">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-base font-semibold text-slate-900">{title}</span>
            <div
              className="inline-flex overflow-hidden rounded-lg border border-slate-300 bg-white"
              role="group"
              aria-label={`Linea per ${title}`}
            >
              {group.lines.map((l) => (
                <button
                  key={l}
                  type="button"
                  aria-pressed={l === line}
                  onClick={() => setLine(l)}
                  className={`min-h-10 px-3 text-base font-medium tabular-nums transition ${
                    l === line ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  {fmtLine(l)}
                </button>
              ))}
            </div>
          </div>
        </td>
      </tr>
      {over ? <MarketRowView row={over} highlight={over.market_key === bestKey} /> : null}
      {under ? <MarketRowView row={under} highlight={under.market_key === bestKey} /> : null}
    </>
  )
}

/** Tabella dei mercati: classici in righe, statistiche raggruppate con selettore di linea. */
export function V4MarketsTable({ markets, homeTeam, awayTeam, bestKey }: Props) {
  const [sortByProfit, setSortByProfit] = useState(false)
  const { classic, groups } = useMemo(() => splitMarkets(markets), [markets])

  const classicSorted = useMemo(
    () =>
      sortByProfit
        ? [...classic].sort((a, b) => compareByProfitDesc(a.expected_profit, b.expected_profit))
        : classic,
    [classic, sortByProfit],
  )
  const groupsSorted = useMemo(
    () => (sortByProfit ? [...groups].sort((a, b) => compareByProfitDesc(a.bestProfit, b.bestProfit)) : groups),
    [groups, sortByProfit],
  )

  if (markets.length === 0) {
    return <p className="text-base text-slate-500">Nessun mercato calcolato per questa partita.</p>
  }

  return (
    <div className="space-y-2" data-testid="v4-markets-table">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-base font-semibold text-slate-900">Tabella dei mercati</p>
        <button
          type="button"
          aria-pressed={sortByProfit}
          onClick={() => setSortByProfit((s) => !s)}
          className={`min-h-10 rounded-lg border px-3 text-base font-medium transition ${
            sortByProfit
              ? 'border-slate-900 bg-slate-900 text-white'
              : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
          }`}
        >
          {sortByProfit ? 'Ordinati per profitto atteso' : 'Ordina per profitto atteso'}
        </button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-[760px] w-full border-collapse">
          <thead className="bg-slate-50">
            <tr>
              <th scope="col" className={th}>Mercato</th>
              <th scope="col" className={`${th} text-right`}>Probabilità</th>
              <th scope="col" className={`${th} text-right`}>Quota Bet365</th>
              <th scope="col" className={`${th} text-right`}>Quota Betfair</th>
              <th scope="col" className={`${th} text-right`}>Profitto atteso</th>
              <th scope="col" className={th}>Verdetto</th>
            </tr>
          </thead>
          <tbody>
            {classicSorted.map((row) => (
              <MarketRowView key={row.market_key} row={row} highlight={row.market_key === bestKey} />
            ))}
            {groupsSorted.map((g) => (
              <StatGroupRows key={g.key} group={g} homeTeam={homeTeam} awayTeam={awayTeam} bestKey={bestKey} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-base text-slate-500">
        La probabilità è quella calibrata con l'intervallo al 90%. Il profitto atteso usa la probabilità
        prudente per la quota: sopra il 3% la giocata è giocabile.
      </p>
    </div>
  )
}
