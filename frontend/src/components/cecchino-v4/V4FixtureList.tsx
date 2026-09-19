import type { V4FixturesResponse } from '../../lib/cecchinoV4Api'
import { noPlayReasonLabel } from './constants'
import { V4FixtureCard } from './V4FixtureCard'
import { V4Empty, V4Error, V4Loading } from './V4States'

type Props = {
  data: V4FixturesResponse | null
  loading: boolean
  error: string | null
  onRetry: () => void
  selectedId: number | null
  onSelect: (id: number) => void
  hasActiveFilters: boolean
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

function abstentionLine(data: V4FixturesResponse): string {
  const analysed = data.items.length
  const plays = data.items.filter((f) => f.best_play != null).length
  const entries = Object.entries(data.abstentions ?? {}).filter(([, n]) => n > 0)
  const abstained = entries.reduce((s, [, n]) => s + n, 0)
  const parts = [plural(analysed, 'partita analizzata', 'partite analizzate'), plural(plays, 'giocata', 'giocate')]
  if (abstained > 0) {
    const reasons = entries
      .map(([reason, n]) => [noPlayReasonLabel(reason), n] as const)
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([label, n]) => `${label} ${n}`)
      .join(', ')
    parts.push(`${plural(abstained, 'astensione', 'astensioni')}: ${reasons}`)
  } else {
    parts.push('nessuna astensione')
  }
  return parts.join(' · ')
}

export function V4FixtureList({ data, loading, error, onRetry, selectedId, onSelect, hasActiveFilters }: Props) {
  if (loading) return <V4Loading label="Carico le partite…" rows={4} />
  if (error) return <V4Error message={error} onRetry={onRetry} />
  if (!data) return null

  return (
    <div className="space-y-3" data-testid="v4-fixture-list">
      {data.items.length === 0 ? (
        <V4Empty
          title={
            hasActiveFilters
              ? 'Nessuna partita con questi filtri'
              : 'Nessuna partita dei 16 campionati in questo giorno'
          }
          hint={hasActiveFilters ? 'Allarga i filtri per vedere le altre partite analizzate.' : undefined}
        />
      ) : (
        <ul className="space-y-3">
          {data.items.map((f) => (
            <li key={f.id}>
              <V4FixtureCard fixture={f} selected={f.id === selectedId} onSelect={onSelect} />
            </li>
          ))}
        </ul>
      )}
      <p className="text-base text-slate-600" data-testid="v4-abstention-line">
        {abstentionLine(data)}
      </p>
    </div>
  )
}
