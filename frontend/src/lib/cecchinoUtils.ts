import type { CecchinoFinalOdds, CecchinoUpcomingFixtureRow, CecchinoWDL } from './cecchinoApi'

export type CecchinoSide = '1' | 'X' | '2'

export function formatWdl(w: CecchinoWDL | null | undefined): string {
  if (!w) return '—'
  return `${w.wins}V / ${w.draws}X / ${w.losses}S`
}

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}

export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `${v.toFixed(digits)}%`
}

export function canShowFinalOdds(status: string | null | undefined): boolean {
  return status === 'available' || status === 'partial_low_sample'
}

export function computeBestSideFromRow(row: CecchinoUpcomingFixtureRow): CecchinoSide | null {
  if (!canShowFinalOdds(row.calculation_status)) return null
  return computeBestSideFromQuotas(
    row.final_quota_1,
    row.final_quota_x,
    row.final_quota_2,
    row.final_prob_1_pct,
    row.final_prob_x_pct,
    row.final_prob_2_pct,
  )
}

export function computeBestSideFromFinal(final: CecchinoFinalOdds): CecchinoSide | null {
  if (!canShowFinalOdds(final.status)) return null
  return computeBestSideFromQuotas(
    final.quota_1,
    final.quota_x,
    final.quota_2,
    final.prob_1_pct,
    final.prob_x_pct,
    final.prob_2_pct,
  )
}

function computeBestSideFromQuotas(
  q1: number | null,
  qx: number | null,
  q2: number | null,
  p1: number | null,
  px: number | null,
  p2: number | null,
): CecchinoSide | null {
  const sides: CecchinoSide[] = ['1', 'X', '2']
  const quotas = [q1, qx, q2]
  const probs = [p1, px, p2]

  let best: CecchinoSide | null = null
  let bestQ = Infinity
  let bestP = -Infinity

  for (let i = 0; i < 3; i++) {
    const q = quotas[i]
    const p = probs[i]
    if (q == null || !Number.isFinite(q) || q <= 0) continue
    const side = sides[i]
    if (q < bestQ - 1e-9) {
      bestQ = q
      bestP = p ?? -Infinity
      best = side
    } else if (Math.abs(q - bestQ) < 1e-9 && (p ?? -Infinity) > bestP) {
      bestP = p ?? -Infinity
      best = side
    }
  }
  return best
}

export function statusLabel(status: string | null | undefined): string {
  switch (status) {
    case 'available':
      return 'Disponibile'
    case 'partial_low_sample':
      return 'Campione parziale'
    case 'insufficient_data':
      return 'Dati insufficienti'
    case 'pending_formula_extraction':
      return 'Formula in attesa'
    case 'not_implemented_yet':
      return 'Non implementato'
    case 'error':
      return 'Errore'
    default:
      return status ?? '—'
  }
}

export function hasLowSampleWarning(warnings: string[] | null | undefined): boolean {
  return (warnings ?? []).some((w) => w.startsWith('low_sample'))
}

export function statusBadgeClass(status: string | null | undefined): string {
  switch (status) {
    case 'available':
      return 'bg-emerald-100 text-emerald-800'
    case 'partial_low_sample':
      return 'bg-amber-100 text-amber-900'
    case 'insufficient_data':
      return 'bg-slate-100 text-slate-700'
    case 'pending_formula_extraction':
      return 'bg-slate-100 text-slate-600'
    case 'error':
      return 'bg-red-100 text-red-800'
    default:
      return 'bg-slate-100 text-slate-600'
  }
}

export function fmtKickoff(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      year: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}
