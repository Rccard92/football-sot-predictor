export function formatKickoff(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('it-IT', { dateStyle: 'medium', timeStyle: 'short' })
}

export function formatNum(n: number, maxFrac = 2): string {
  return n.toLocaleString('it-IT', { maximumFractionDigits: maxFrac, minimumFractionDigits: 0 })
}

export function yn(v: unknown): string {
  return v === true ? 'Sì' : 'No'
}

