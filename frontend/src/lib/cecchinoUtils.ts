import type {
  CecchinoDataQuality,
  CecchinoFinalOdds,
  CecchinoLeakageCheck,
  CecchinoUpcomingFixtureRow,
  CecchinoWDL,
} from './cecchinoApi'

export const INPUT_SNAPSHOT_CONTEXT_KEYS = [
  'home_context',
  'away_context',
  'home_total',
  'away_total',
  'home_recent_context_5',
  'away_recent_context_5',
  'home_recent_total_6',
  'away_recent_total_6',
] as const

const CONTEXT_LABELS: Record<string, string> = {
  home_context: 'Casa split casalinghe',
  away_context: 'Trasferta split esterne',
  home_total: 'Totali casa',
  away_total: 'Totali trasferta',
  home_recent_context_5: 'Ultime 5 casalinghe',
  away_recent_context_5: 'Ultime 5 esterne',
  home_recent_total_6: 'Ultime 6 totali casa',
  away_recent_total_6: 'Ultime 6 totali trasferta',
}

export type NormalizedContextSlice = {
  key: string
  label: string
  wdl: CecchinoWDL | null
  sampleCount: number | null
  targetSample: number | null
  status: string | null
}

export function normalizeLeakageCheck(raw: unknown): CecchinoLeakageCheck | null {
  if (raw == null) return null
  if (typeof raw === 'string') {
    return {
      status: raw,
      target_kickoff: null,
      max_source_fixture_date: null,
      checked_at: null,
    }
  }
  if (typeof raw === 'object') {
    const o = raw as Record<string, unknown>
    return {
      status: String(o.status ?? 'undefined'),
      target_kickoff: (o.target_kickoff as string | null) ?? null,
      max_source_fixture_date: (o.max_source_fixture_date as string | null) ?? null,
      checked_at: (o.checked_at as string | null) ?? null,
    }
  }
  return null
}

export function getLeakageStatus(dataQuality: CecchinoDataQuality | null | undefined): string {
  const lc = normalizeLeakageCheck(dataQuality?.leakage_check)
  return lc?.status ?? 'undefined'
}

export function leakageDisplayLabel(status: string | null | undefined): string {
  const s = (status ?? 'undefined').toLowerCase()
  if (s === 'passed') return 'PASSED'
  if (s === 'failed') return 'FAILED'
  if (s === 'not_applicable') return 'N/A'
  return 'UNDEFINED'
}

function parseWdl(raw: unknown): CecchinoWDL | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  const inner = o.wdl && typeof o.wdl === 'object' ? (o.wdl as Record<string, unknown>) : o
  const wins = Number(inner.wins)
  const draws = Number(inner.draws)
  const losses = Number(inner.losses)
  if (!Number.isFinite(wins) || !Number.isFinite(draws) || !Number.isFinite(losses)) {
    return null
  }
  return { wins, draws, losses }
}

export function normalizeContextSlice(
  key: string,
  raw: unknown,
  fallbackLabel?: string,
): NormalizedContextSlice | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  const wdl = parseWdl(o)
  const sampleCount =
    typeof o.sample_count === 'number' && Number.isFinite(o.sample_count)
      ? o.sample_count
      : null
  const targetSample =
    typeof o.target_sample === 'number' && Number.isFinite(o.target_sample)
      ? o.target_sample
      : null
  const status = typeof o.status === 'string' ? o.status : null
  const label =
    typeof o.label === 'string' ? o.label : (fallbackLabel ?? CONTEXT_LABELS[key] ?? key)
  return { key, label, wdl, sampleCount, targetSample, status }
}

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
