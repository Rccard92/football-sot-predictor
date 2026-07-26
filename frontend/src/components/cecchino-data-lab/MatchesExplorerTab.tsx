import { useEffect, useMemo, useState } from 'react'
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table'
import {
  formatOdd,
  getCecchinoLabMatches,
  qualityBadgeClass,
  type CecchinoLabMatch,
} from '../../lib/cecchinoLabApi'
import { qualityLabel } from './labTheme'
import { MatchDetailDrawer } from './MatchDetailDrawer'

type Props = {
  datasetId: number | null
  refreshKey: number
}

export function MatchesExplorerTab({ datasetId, refreshKey }: Props) {
  const [items, setItems] = useState<CecchinoLabMatch[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(50)
  const [sortBy, setSortBy] = useState('match_date')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [search, setSearch] = useState('')
  const [quality, setQuality] = useState('')
  const [result, setResult] = useState('')
  const [has1x2, setHas1x2] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  useEffect(() => {
    setPage(1)
  }, [datasetId, search, quality, result, has1x2])

  useEffect(() => {
    let cancelled = false
    getCecchinoLabMatches({
      dataset_id: datasetId ?? undefined,
      search: search || undefined,
      quality_status: quality || undefined,
      result: result || undefined,
      has_bet365_1x2: has1x2 === '' ? undefined : has1x2 === 'true',
      page,
      page_size: pageSize,
      sort_by: sortBy,
      sort_dir: sortDir,
    })
      .then((res) => {
        if (!cancelled) {
          setItems(res.items)
          setTotal(res.total)
          setLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setItems([])
          setTotal(0)
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [datasetId, refreshKey, page, pageSize, sortBy, sortDir, search, quality, result, has1x2])

  const columns = useMemo<ColumnDef<CecchinoLabMatch>[]>(
    () => [
      {
        accessorKey: 'match_date',
        header: 'Data',
        cell: (info) => info.getValue() ?? '—',
      },
      {
        id: 'competition',
        header: 'Campionato',
        cell: ({ row }) => row.original.competition_name ?? '—',
      },
      {
        id: 'season',
        header: 'Stagione',
        cell: ({ row }) => row.original.season_label ?? '—',
      },
      { accessorKey: 'home_team', header: 'Casa' },
      { accessorKey: 'away_team', header: 'Trasferta' },
      {
        id: 'ft',
        header: 'FT',
        cell: ({ row }) =>
          row.original.ft_home_goals != null
            ? `${row.original.ft_home_goals}–${row.original.ft_away_goals}`
            : '—',
      },
      {
        id: 'ht',
        header: 'HT',
        cell: ({ row }) =>
          row.original.ht_home_goals != null
            ? `${row.original.ht_home_goals}–${row.original.ht_away_goals}`
            : '—',
      },
      {
        accessorKey: 'bet365_home',
        header: 'B365 1',
        cell: (info) => formatOdd(info.getValue() as number | null),
      },
      {
        accessorKey: 'bet365_draw',
        header: 'B365 X',
        cell: (info) => formatOdd(info.getValue() as number | null),
      },
      {
        accessorKey: 'bet365_away',
        header: 'B365 2',
        cell: (info) => formatOdd(info.getValue() as number | null),
      },
      {
        accessorKey: 'bet365_over_25',
        header: 'Over 2.5',
        cell: (info) => formatOdd(info.getValue() as number | null),
      },
      {
        accessorKey: 'bet365_under_25',
        header: 'Under 2.5',
        cell: (info) => formatOdd(info.getValue() as number | null),
      },
      {
        accessorKey: 'row_quality_status',
        header: 'Stato',
        cell: ({ row }) => (
          <span className={`rounded px-2 py-0.5 text-xs ${qualityBadgeClass(row.original.row_quality_status)}`}>
            {qualityLabel(row.original.row_quality_status)}
          </span>
        ),
      },
      {
        id: 'detail',
        header: 'Dettaglio',
        cell: ({ row }) => (
          <button
            type="button"
            className="lab-btn-ghost px-2 py-1 text-xs"
            onClick={() => setSelectedId(row.original.id)}
          >
            Apri
          </button>
        ),
      },
    ],
    [],
  )

  const table = useReactTable({
    data: items,
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
  })

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const toggleSort = (id: string) => {
    if (sortBy === id) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortBy(id)
      setSortDir('desc')
    }
  }

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <input
          className="lab-input lg:col-span-2"
          placeholder="Cerca squadra / campionato…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select className="lab-input" value={quality} onChange={(e) => setQuality(e.target.value)}>
          <option value="">Qualità</option>
          <option value="complete">complete</option>
          <option value="partial">partial</option>
          <option value="error">error</option>
        </select>
        <select className="lab-input" value={result} onChange={(e) => setResult(e.target.value)}>
          <option value="">Risultato FT</option>
          <option value="H">H</option>
          <option value="D">D</option>
          <option value="A">A</option>
        </select>
        <select className="lab-input" value={has1x2} onChange={(e) => setHas1x2(e.target.value)}>
          <option value="">Bet365 1X2</option>
          <option value="true">presente</option>
          <option value="false">assente</option>
        </select>
      </div>

      <div className="flex items-center justify-between text-sm" style={{ color: 'var(--lab-muted)' }}>
        <span>
          {loading ? 'Caricamento…' : `${total} partite`}
          {datasetId ? ` · dataset #${datasetId}` : ''}
        </span>
        <div className="flex items-center gap-2">
          <button type="button" className="lab-btn-ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            ←
          </button>
          <span>
            {page} / {totalPages}
          </span>
          <button
            type="button"
            className="lab-btn-ghost"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            →
          </button>
        </div>
      </div>

      <div className="lab-table-wrap">
        <table className="lab-table">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => {
                  const sortKey =
                    h.column.id === 'match_date' ||
                    h.column.id === 'home_team' ||
                    h.column.id === 'away_team' ||
                    h.column.id === 'bet365_home' ||
                    h.column.id === 'row_quality_status'
                      ? h.column.id
                      : null
                  return (
                    <th
                      key={h.id}
                      className={sortKey ? 'cursor-pointer select-none' : undefined}
                      onClick={() => sortKey && toggleSort(sortKey)}
                    >
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {sortBy === sortKey ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
                    </th>
                  )
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                ))}
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="py-10 text-center" style={{ color: 'var(--lab-muted)' }}>
                  Nessuna partita trovata.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <MatchDetailDrawer matchId={selectedId} onClose={() => setSelectedId(null)} />
    </div>
  )
}
