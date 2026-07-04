/** Data locale browser (YYYY-MM-DD), senza conversione UTC. */

function formatLocalDate(d: Date): string {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function todayLocalIso(): string {
  return formatLocalDate(new Date())
}

export function isoDaysAgoLocal(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return formatLocalDate(d)
}
