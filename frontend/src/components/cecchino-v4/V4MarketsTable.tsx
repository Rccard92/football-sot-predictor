import { useMemo, useState } from 'react'
import type { V4MarketRow } from '../../lib/cecchinoV4Api'
import { statLabel, v4Mono, v4SmallButton, v4SmallButtonActive } from './constants'
import { capitalize, fmtInterval, fmtLine, fmtProfit, fmtQuota } from './format'
import {
  compareByProfitDesc,
  defaultLine,
  deriveUnderRow,
  keyMarkets,
  parseStatKey,
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

const th = 'px-2 py-1.5 text-left text-xs font-medium text-slate-500'
const td = 'px-2 py-1.5 text-sm text-slate-800'
const num = `${td} ${v4Mono} text-right`

function profitTone(v: number | null): string {
  if (v == null) return 'text-slate-400'
  if (v >= 0.03) return 'font-semibold text-emerald-700'
  if (v < 0) return 'text-slate-500'
  return 'text-slate-700'
}

// --- Mercati chiave -------------------------------------------------------------------------------

function KeyMarketsTable({ rows, bestKey }: { rows: V4MarketRow[]; bestKey: string | null }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full min-w-[480px] border-collapse" data-testid="v4-key-markets">
        <thead className="bg-slate-50">
          <tr>
            <th scope="col" className={th}>Mercato</th>
            <th scope="col" className={`${th} text-right`}>Prob.</th>
            <th scope="col" className={`${th} text-right`}>Quota</th>
            <th scope="col" className={`${th} text-right`}>Profitto</th>
            <th scope="col" className={th}>Verdetto</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.market_key}
              className={row.market_key === bestKey ? 'bg-emerald-50/70' : 'odd:bg-white even:bg-slate-50/60'}
              data-testid="v4-key-market-row"
            >
              <td className={`${td} font-medium text-slate-900`}>{row.label}</td>
              <td className={num}>{fmtInterval(row.p, row.lo, row.hi)}</td>
              <td className={num}>{fmtQuota(row.quota_used)}</td>
              <td className={`${num} ${profitTone(row.expected_profit)}`}>{fmtProfit(row.expected_profit)}</td>
              <td className={td}>
                <V4VerdictChip verdict={row.verdict} label={row.verdict_label} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// --- Tabella completa ------------------------------------------------------------------------------

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

/** Linea migliore del gruppo: quella della giocata, altrimenti quella col profitto atteso piu' alto. */
function bestLine(group: StatGroup, bestKey: string | null): string {
  const parts = bestKey ? parseStatKey(bestKey) : null
  if (parts && `${parts.stat}:${parts.side}` === group.key && group.lines.includes(parts.line)) return parts.line
  let best: { line: string; profit: number | null } | null = null
  for (const line of group.lines) {
    for (const r of [group.over[line], group.under[line]]) {
      if (!r) continue
      if (!best || compareByProfitDesc(r.expected_profit, best.profit) < 0) best = { line, profit: r.expected_profit }
    }
  }
  return best?.line ?? defaultLine(group, bestKey)
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
  const [expanded, setExpanded] = useState(false)
  const [line, setLine] = useState(() => bestLine(group, bestKey))
  const team = sideName(group.side, homeTeam, awayTeam)
  const title = `${capitalize(statLabel(group.stat))} · ${team}`
  const over = group.over[line] ?? null
  const under =
    group.under[line] ??
    (over ? deriveUnderRow(over, `${team} under ${fmtLine(line)} ${statLabel(group.stat)}`) : null)
  const hasMoreLines = group.lines.length > 1

  return (
    <>
      <tr className="bg-slate-100/80" data-testid="v4-stat-group">
        <td colSpan={6} className="px-2 py-1.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-medium text-slate-900">{title}</span>
            {hasMoreLines ? (
              expanded ? (
                <div className="inline-flex overflow-hidden rounded-lg border border-slate-300 bg-white" role="group" aria-label={`Linea per ${title}`}>
                  {group.lines.map((l) => (
                    <button
                      key={l}
                      type="button"
                      aria-pressed={l === line}
                      onClick={() => setLine(l)}
                      className={`${v4Mono} px-2.5 py-1 text-xs font-medium transition ${
                        l === line ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-50'
                      }`}
                    >
                      {fmtLine(l)}
                    </button>
                  ))}
                </div>
              ) : (
                <button type="button" onClick={() => setExpanded(true)} className="text-xs font-medium text-blue-700 hover:underline">
                  Altre linee ({group.lines.length - 1})
                </button>
              )
            ) : null}
          </div>
        </td>
      </tr>
      {over ? <MarketRowView row={over} highlight={over.market_key === bestKey} /> : null}
      {under ? <MarketRowView row={under} highlight={under.market_key === bestKey} /> : null}
    </>
  )
}

/**
 * Prima i sei mercati chiave; con "Mostra tutti i mercati" la tabella completa
 * (classici in righe, statistiche raggruppate sulla linea migliore con "Altre linee").
 */
export function V4MarketsTable({ markets, homeTeam, awayTeam, bestKey }: Props) {
  const [showAll, setShowAll] = useState(false)
  const [sortByProfit, setSortByProfit] = useState(false)
  const key = useMemo(() => keyMarkets(markets, bestKey), [markets, bestKey])
  const { classic, groups } = useMemo(() => splitMarkets(markets), [markets])

  const classicSorted = useMemo(
    () => (sortByProfit ? [...classic].sort((a, b) => compareByProfitDesc(a.expected_profit, b.expected_profit)) : classic),
    [classic, sortByProfit],
  )
  const groupsSorted = useMemo(
    () => (sortByProfit ? [...groups].sort((a, b) => compareByProfitDesc(a.bestProfit, b.bestProfit)) : groups),
    [groups, sortByProfit],
  )

  if (markets.length === 0) {
    return <p className="text-sm text-slate-500">Nessun mercato calcolato per questa partita.</p>
  }

  return (
    <div className="space-y-2" data-testid="v4-markets-table">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-slate-800">{showAll ? `Tutti i mercati · ${markets.length}` : 'Mercati chiave'}</p>
        <div className="flex flex-wrap items-center gap-2">
          {showAll ? (
            <button
              type="button"
              aria-pressed={sortByProfit}
              onClick={() => setSortByProfit((s) => !s)}
              className={sortByProfit ? v4SmallButtonActive : v4SmallButton}
            >
              Ordina per profitto
            </button>
          ) : null}
          <button type="button" aria-pressed={showAll} onClick={() => setShowAll((s) => !s)} className={v4SmallButton}>
            {showAll ? 'Solo i mercati chiave' : 'Mostra tutti i mercati'}
          </button>
        </div>
      </div>

      {!showAll ? (
        <KeyMarketsTable rows={key} bestKey={bestKey} />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full min-w-[640px] border-collapse" data-testid="v4-all-markets">
            <thead className="bg-slate-50">
              <tr>
                <th scope="col" className={th}>Mercato</th>
                <th scope="col" className={`${th} text-right`}>Probabilità</th>
                <th scope="col" className={`${th} text-right`}>Bet365</th>
                <th scope="col" className={`${th} text-right`}>Betfair</th>
                <th scope="col" className={`${th} text-right`}>Profitto</th>
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
      )}
      <p className="text-xs text-slate-500">
        Probabilità calibrata con intervallo al 90%. Profitto atteso = probabilità prudente × quota − 1: sopra il 3% la
        giocata è giocabile.
      </p>
    </div>
  )
}
