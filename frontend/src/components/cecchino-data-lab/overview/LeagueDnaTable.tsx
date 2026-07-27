import { useMemo, useState, type CSSProperties } from 'react'
import type { CecchinoLabLeagueRow } from '../../../lib/cecchinoLabApi'
import { formatPct, formatRoi, heatBg, roiColor } from './overviewTheme'

type Props = {
  leagues: CecchinoLabLeagueRow[]
  onSelectCompetition: (name: string) => void
}

type SortKey = keyof CecchinoLabLeagueRow

const COLS: Array<{ key: SortKey; label: string; heat?: boolean; roi?: boolean }> = [
  { key: 'competition_name', label: 'Campionato' },
  { key: 'matches', label: 'N' },
  { key: 'home_win_pct', label: '1%', heat: true },
  { key: 'draw_pct', label: 'X%', heat: true },
  { key: 'away_win_pct', label: '2%', heat: true },
  { key: 'over_25_pct', label: 'O2.5', heat: true },
  { key: 'btts_pct', label: 'BTTS', heat: true },
  { key: 'average_goals', label: 'Goal' },
  { key: 'favorite_hit_pct', label: 'Fav%', heat: true },
  { key: 'average_pre_margin_pct', label: 'Marg.' },
  { key: 'roi_home_pct', label: 'ROI 1', roi: true },
  { key: 'roi_over_25_pct', label: 'ROI O', roi: true },
]

export function LeagueDnaTable({ leagues, onSelectCompetition }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('matches')
  const [asc, setAsc] = useState(false)

  const sorted = useMemo(() => {
    const copy = [...leagues]
    copy.sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      if (typeof av === 'string' && typeof bv === 'string') {
        return asc ? av.localeCompare(bv) : bv.localeCompare(av)
      }
      const an = Number(av)
      const bn = Number(bv)
      return asc ? an - bn : bn - an
    })
    return copy
  }, [leagues, sortKey, asc])

  const toggle = (key: SortKey) => {
    if (sortKey === key) setAsc((v) => !v)
    else {
      setSortKey(key)
      setAsc(key === 'competition_name')
    }
  }

  return (
    <section
      className="rounded-2xl p-4 sm:p-5"
      style={{
        background: 'linear-gradient(160deg, rgba(21,38,58,0.95), rgba(12,24,38,0.98))',
        border: '1px solid var(--lab-border)',
      }}
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-[0.16em]" style={{ color: 'var(--lab-cyan)' }}>
          League DNA
        </h2>
        <span className="text-xs" style={{ color: 'var(--lab-muted)' }}>
          Clicca una riga per filtrare · tabella ordinabile
        </span>
      </div>
      <div className="lab-table-wrap overflow-x-auto">
        <table className="lab-table text-xs">
          <thead>
            <tr>
              {COLS.map((c) => (
                <th key={c.key}>
                  <button type="button" className="lab-btn-ghost px-1 py-0.5 text-[11px]" onClick={() => toggle(c.key)}>
                    {c.label}
                    {sortKey === c.key ? (asc ? ' ↑' : ' ↓') : ''}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr
                key={`${row.country}-${row.competition_name}`}
                className="cursor-pointer transition-colors hover:bg-white/5"
                onClick={() => onSelectCompetition(row.competition_name)}
              >
                {COLS.map((c) => {
                  const raw = row[c.key]
                  let display: string
                  if (c.key === 'competition_name') display = String(raw)
                  else if (c.key === 'matches') display = String(raw)
                  else if (c.key === 'average_goals') display = raw == null ? '—' : Number(raw).toFixed(2)
                  else if (c.roi) display = formatRoi(raw as number | null)
                  else display = formatPct(raw as number | null)

                  const style: CSSProperties = {}
                  if (c.heat && typeof raw === 'number') style.background = heatBg(raw, 55)
                  if (c.roi) style.color = roiColor(raw as number | null)

                  return (
                    <td key={c.key} className="tabular-nums" style={style}>
                      {c.key === 'competition_name' ? (
                        <span>
                          <span className="font-medium">{row.competition_name}</span>
                          <span className="ml-1 opacity-60">{row.country}</span>
                        </span>
                      ) : (
                        display
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={COLS.length} className="py-8 text-center" style={{ color: 'var(--lab-muted)' }}>
                  Nessun campionato nel filtro.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  )
}
