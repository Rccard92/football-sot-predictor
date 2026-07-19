/** Formattazione numerica Balance v5 — locale it-IT, max 2 decimali. */

export type BalanceNumberUnit = 'pct' | 'pp' | 'quota' | 'index' | 'text'

const itNumber = new Intl.NumberFormat('it-IT', {
  maximumFractionDigits: 2,
})

export function formatBalanceNumber(
  value: number | string | null | undefined,
  unit: BalanceNumberUnit = 'index',
): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'string') {
    if (unit === 'text') return value
    const n = Number(value)
    if (!Number.isFinite(n)) return value || '—'
    return formatBalanceNumber(n, unit)
  }
  if (!Number.isFinite(value)) return '—'
  const core = itNumber.format(value)
  switch (unit) {
    case 'pct':
      return `${core}%`
    case 'pp':
      return `${core} pp`
    case 'quota':
    case 'index':
      return core
    case 'text':
      return String(value)
    default:
      return core
  }
}
