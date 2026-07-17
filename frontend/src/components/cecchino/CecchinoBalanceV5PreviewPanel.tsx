import { useState } from 'react'
import type {
  CecchinoBalanceV5Pillar,
  CecchinoBalanceV5Preview,
  CecchinoFixtureIdentityConsistency,
} from '../../lib/cecchinoTodayApi'
import { formatBalanceNumber } from '../../utils/formatBalanceNumber'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

type Props = {
  preview?: CecchinoBalanceV5Preview | null
  identityConsistency?: CecchinoFixtureIdentityConsistency | null
}

const IDENTITY_MISMATCH_ALERT =
  'Analisi non disponibile: data, stato o snapshot della fixture non risultano coerenti.'

const PILLAR_ORDER = ['f36', 'dominance', 'draw_credibility', 'gap_coherence'] as const

const BADGE_LABEL: Record<string, string> = {
  official: 'Produttivo',
  research: 'Ricerca',
  calibration_pending: 'In calibrazione',
  unavailable: 'Dato non disponibile',
}

function badgeClass(status: string): string {
  switch (status) {
    case 'official':
      return 'bg-slate-800 text-white ring-slate-800'
    case 'research':
      return 'bg-amber-50 text-amber-900 ring-amber-200'
    case 'calibration_pending':
      return 'bg-slate-100 text-slate-600 ring-slate-200'
    default:
      return 'bg-slate-50 text-slate-500 ring-slate-200'
  }
}

function fmtIndex(index: number | null | undefined): string {
  return formatBalanceNumber(index, 'index')
}

function fmtClass(label: string | null | undefined, status: string): string {
  if (label) return label
  if (status === 'calibration_pending') return 'In calibrazione'
  if (status === 'unavailable') return 'Dato non disponibile'
  return '—'
}

function fmtValue(value: number | string | null | undefined, unit: string): string {
  if (unit === 'pct' || unit === 'pp' || unit === 'quota' || unit === 'index' || unit === 'text') {
    return formatBalanceNumber(value, unit)
  }
  return formatBalanceNumber(value, 'index')
}

function isIdentityMismatch(
  preview?: CecchinoBalanceV5Preview | null,
  identityConsistency?: CecchinoFixtureIdentityConsistency | null,
): boolean {
  if (identityConsistency?.status === 'inconsistent') return true
  if (preview?.status === 'unavailable') {
    const warnings = preview.warnings ?? []
    if (warnings.includes('fixture_identity_mismatch')) return true
  }
  return false
}

function PillarCard({ pillar, number }: { pillar: CecchinoBalanceV5Pillar; number: number }) {
  const [open, setOpen] = useState(false)
  return (
    <article className={`${todayCard} ${todayCardPadding} flex flex-col gap-3`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            Pilastro {number}
          </p>
          <h4 className="text-sm font-semibold text-slate-900">{pillar.title}</h4>
        </div>
        <span
          className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ${badgeClass(pillar.status)}`}
        >
          {BADGE_LABEL[pillar.status] ?? pillar.status}
        </span>
      </div>
      <p className="text-xs text-slate-500">{pillar.question}</p>
      <div className="flex items-end justify-between gap-3 border-t border-slate-100 pt-3">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-slate-400">Indice</p>
          <p className="text-2xl font-semibold tabular-nums text-slate-900">{fmtIndex(pillar.index)}</p>
        </div>
        <div className="text-right">
          <p className="text-[10px] uppercase tracking-wide text-slate-400">Classe</p>
          <p className="text-sm font-medium text-slate-800">
            {fmtClass(pillar.class_label, pillar.status)}
          </p>
          {pillar.direction ? (
            <p className="mt-0.5 text-xs text-slate-500">Segno: {pillar.direction}</p>
          ) : null}
        </div>
      </div>
      <p className="text-xs leading-relaxed text-slate-700">{pillar.reading}</p>
      <button
        type="button"
        className="self-start text-xs font-medium text-slate-600 underline-offset-2 hover:underline"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? 'Nascondi componenti' : 'Mostra componenti'}
      </button>
      {open ? (
        <ul className="space-y-1 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-700">
          {pillar.components.map((c) => (
            <li key={c.key} className="flex justify-between gap-2">
              <span className="text-slate-500">{c.label}</span>
              <span className="tabular-nums font-medium">{fmtValue(c.value, c.unit)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {pillar.source_version ? (
        <p className="text-[10px] text-slate-400">Fonte: {pillar.source_version}</p>
      ) : null}
    </article>
  )
}

export function CecchinoBalanceV5PreviewPanel({ preview, identityConsistency }: Props) {
  if (!preview) {
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <h3 className={todaySectionTitle}>Equilibrio vs Squilibrio — Preview v5</h3>
        <p className={`mt-2 ${todaySectionSubtitle}`}>Anteprima non disponibile per questa partita.</p>
      </section>
    )
  }

  if (isIdentityMismatch(preview, identityConsistency)) {
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <h3 className={todaySectionTitle}>Equilibrio vs Squilibrio — Preview v5</h3>
        <p
          role="alert"
          className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950"
        >
          {IDENTITY_MISMATCH_ALERT}
        </p>
      </section>
    )
  }

  const pillars = PILLAR_ORDER.map((key) => preview.pillars.find((p) => p.key === key)).filter(
    Boolean,
  ) as CecchinoBalanceV5Pillar[]

  const market = preview.market_deviation

  return (
    <section className="space-y-4">
      <div>
        <h3 className={todaySectionTitle}>Equilibrio vs Squilibrio — Preview v5</h3>
        <p className={todaySectionSubtitle}>
          Quattro pilastri descrittivi indipendenti. Nessuna promozione di formule sperimentali.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
        {pillars.map((p, i) => (
          <PillarCard key={p.key} pillar={p} number={i + 1} />
        ))}
      </div>

      <section className={`${todayCard} ${todayCardPadding} border-slate-300`}>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h4 className="text-sm font-semibold text-slate-900">{market.title}</h4>
            <p className="text-xs text-slate-500">{market.subtitle}</p>
          </div>
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ${badgeClass(market.status)}`}
          >
            {BADGE_LABEL[market.status] ?? market.status}
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="py-1 pr-3">Mercato</th>
                <th className="py-1 pr-3">Quota Cecchino</th>
                <th className="py-1 pr-3">Quota Book</th>
                <th className="py-1 pr-3">Dev. pp</th>
              </tr>
            </thead>
            <tbody>
              {(market.pairs ?? []).map((pair) => (
                <tr key={pair.key} className="border-t border-slate-100">
                  <td className="py-1.5 pr-3 font-medium text-slate-800">{pair.label}</td>
                  <td className="py-1.5 pr-3 tabular-nums">{fmtValue(pair.quota_cecchino ?? null, 'quota')}</td>
                  <td className="py-1.5 pr-3 tabular-nums">{fmtValue(pair.quota_book ?? null, 'quota')}</td>
                  <td className="py-1.5 pr-3 tabular-nums">{fmtValue(pair.deviation_pp ?? null, 'pp')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-slate-600">{market.reading}</p>
      </section>

      <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
        {preview.research_note}
      </p>
    </section>
  )
}
