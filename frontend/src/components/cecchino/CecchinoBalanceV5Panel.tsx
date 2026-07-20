import { useState } from 'react'
import type {
  CecchinoBalanceV5,
  CecchinoBalanceV5MarketPair,
  CecchinoBalanceV5Pillar,
  CecchinoBalanceV5SnapshotMeta,
  CecchinoFixtureIdentityConsistency,
} from '../../lib/cecchinoTodayApi'
import { formatBalanceNumber } from '../../utils/formatBalanceNumber'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

type Props = {
  balance?: CecchinoBalanceV5 | null
  identityConsistency?: CecchinoFixtureIdentityConsistency | null
  snapshotMeta?: CecchinoBalanceV5SnapshotMeta | null
}

const PANEL_TITLE = 'Equilibrio vs Squilibrio v5'
const PANEL_SUBTITLE = 'Quattro letture distinte della struttura della partita.'
const INDEX_DISCLAIMER =
  'Gli indici descrivono dimensioni diverse e non vanno confrontati direttamente tra loro.'
const DRAW_NOTE_FALLBACK =
  'Indice descrittivo interno, non ancora probabilità calibrata sull’esito reale.'

const IDENTITY_MISMATCH_ALERT =
  'Analisi non disponibile: data, stato o snapshot della fixture non risultano coerenti.'

const HIST_VERIFIED_TEXT =
  'Analisi ricostruita esclusivamente dai dati salvati prima della partita. Stato e risultato finali non modificano i quattro pilastri.'
const HIST_PARTIAL_TEXT =
  'Analisi basata sullo snapshot storico salvato. Alcuni metadati temporali legacy non sono disponibili e vengono indicati come non verificabili.'

const PILLAR_ORDER = ['f36', 'dominance', 'draw_credibility', 'gap_coherence'] as const

const BADGE_LABEL: Record<string, string> = {
  official: 'Ufficiale',
  descriptive_official: 'Descrittivo',
  unavailable: 'Dato non disponibile',
}

function badgeClass(status: string): string {
  switch (status) {
    case 'official':
      return 'bg-slate-800 text-white ring-slate-800'
    case 'descriptive_official':
      return 'bg-slate-100 text-slate-800 ring-slate-300'
    default:
      return 'bg-slate-50 text-slate-500 ring-slate-200'
  }
}

function indexLabel(key: string): string {
  switch (key) {
    case 'f36':
      return 'Indice equilibrio'
    case 'dominance':
      return 'Indice convinzione'
    case 'draw_credibility':
      return 'Probabilità X norm.'
    case 'gap_coherence':
      return 'Indice coerenza'
    default:
      return 'Indice'
  }
}

function classLabelTitle(key: string): string {
  if (key === 'draw_credibility') return 'Classe quota X'
  return 'Classe'
}

function directionLabel(key: string, direction: string): string {
  if (key === 'f36') return `Inclinazione strutturale: lato ${direction}`
  if (key === 'dominance') return `Scenario dominante: ${direction}`
  return `Segno: ${direction}`
}

function fmtIndex(index: number | null | undefined): string {
  return formatBalanceNumber(index, 'index')
}

function fmtClass(label: string | null | undefined, status: string): string {
  if (label) return label
  if (status === 'unavailable') return 'Dato non disponibile'
  return '—'
}

function fmtValue(value: number | string | null | undefined, unit: string): string {
  if (unit === 'pct' || unit === 'pp' || unit === 'quota' || unit === 'index' || unit === 'text') {
    return formatBalanceNumber(value, unit)
  }
  return formatBalanceNumber(value, 'index')
}

/** Quote a due decimali fissi (3 → 3,00). */
function fmtQuotaFixed(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('it-IT', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function isIdentityMismatch(
  balance?: CecchinoBalanceV5 | null,
  identityConsistency?: CecchinoFixtureIdentityConsistency | null,
  snapshotMeta?: CecchinoBalanceV5SnapshotMeta | null,
): boolean {
  if (snapshotMeta?.mode === 'historical_snapshot' && snapshotMeta.status === 'blocked') {
    return true
  }
  if (snapshotMeta?.mode === 'historical_snapshot' && (snapshotMeta.status === 'verified' || snapshotMeta.status === 'partial')) {
    // Storico verificato/parziale: non bloccare per status/score Today vs Local
    return balance?.status === 'unavailable' && (balance.warnings ?? []).includes('fixture_identity_mismatch')
  }
  if (identityConsistency?.status === 'inconsistent') return true
  if (balance?.status === 'unavailable') {
    const warnings = balance.warnings ?? []
    if (warnings.includes('fixture_identity_mismatch')) return true
  }
  return false
}

function blockedAlertMessage(snapshotMeta?: CecchinoBalanceV5SnapshotMeta | null): string {
  const warnings = snapshotMeta?.warnings ?? []
  if (warnings.includes('historical_target_kickoff_mismatch') || warnings.includes('today_local_kickoff_mismatch')) {
    return 'Snapshot storico bloccato: kickoff non coerente.'
  }
  if (warnings.includes('provider_fixture_id_mismatch')) {
    return 'Snapshot storico bloccato: fixture provider differente.'
  }
  if (
    warnings.includes('historical_cecchino_output_absent') ||
    warnings.includes('historical_cecchino_final_unavailable')
  ) {
    return 'Snapshot storico non disponibile: output Cecchino originale assente.'
  }
  if (warnings.includes('local_fixture_id_mismatch') || warnings.includes('historical_local_fixture_missing')) {
    return 'Snapshot storico bloccato: fixture locale non coerente.'
  }
  if (warnings.includes('competition_mismatch')) {
    return 'Snapshot storico bloccato: competizione differente.'
  }
  if (warnings.includes('teams_mismatch')) {
    return 'Snapshot storico bloccato: squadre non coerenti.'
  }
  if (snapshotMeta?.mode === 'historical_snapshot') {
    return 'Snapshot storico bloccato: identità o dati pre-match non coerenti.'
  }
  return IDENTITY_MISMATCH_ALERT
}

function bookStatusLabel(status: string | undefined): string {
  switch (status) {
    case 'verified':
      return 'Book: verificato pre-match'
    case 'partial':
      return 'Book: timestamp non verificabile'
    case 'blocked':
      return 'Book: non usabile (post-kickoff)'
    case 'unavailable':
      return 'Book: assente'
    default:
      return status ? `Book: ${status}` : ''
  }
}

function resolvePillars(balance: CecchinoBalanceV5): CecchinoBalanceV5Pillar[] {
  const order = balance.pillar_order?.length ? balance.pillar_order : [...PILLAR_ORDER]
  const raw = balance.pillars
  if (Array.isArray(raw)) {
    return order
      .map((key) => (raw as CecchinoBalanceV5Pillar[]).find((p) => p.key === key))
      .filter(Boolean) as CecchinoBalanceV5Pillar[]
  }
  return order
    .map((key) => (raw as Record<string, CecchinoBalanceV5Pillar>)[key])
    .filter(Boolean)
}

function marketRowHasAnyData(pair: CecchinoBalanceV5MarketPair): boolean {
  return (
    pair.quota_cecchino != null ||
    pair.quota_book != null ||
    pair.prob_cecchino_norm != null ||
    pair.prob_book_norm != null ||
    pair.prob_cecchino_pct != null ||
    pair.prob_book_pct != null
  )
}

function PillarCard({ pillar, number }: { pillar: CecchinoBalanceV5Pillar; number: number }) {
  const [open, setOpen] = useState(false)
  const note =
    pillar.key === 'draw_credibility'
      ? pillar.informational_note || DRAW_NOTE_FALLBACK
      : null
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
          <p className="text-[10px] uppercase tracking-wide text-slate-400">
            {indexLabel(pillar.key)}
          </p>
          <p className="text-2xl font-semibold tabular-nums text-slate-900">{fmtIndex(pillar.index)}</p>
        </div>
        <div className="text-right">
          <p className="text-[10px] uppercase tracking-wide text-slate-400">
            {classLabelTitle(pillar.key)}
          </p>
          <p className="text-sm font-medium text-slate-800">
            {fmtClass(pillar.class_label, pillar.status)}
          </p>
          {pillar.direction ? (
            <p className="mt-0.5 text-xs text-slate-500">
              {directionLabel(pillar.key, pillar.direction)}
            </p>
          ) : null}
        </div>
      </div>
      <p className="text-xs leading-relaxed text-slate-700">{pillar.reading}</p>
      {note ? <p className="text-[11px] leading-snug text-slate-500">{note}</p> : null}
      <button
        type="button"
        className="self-start text-xs font-medium text-slate-600 underline-offset-2 hover:underline"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? 'Nascondi componenti' : 'Mostra componenti'}
      </button>
      {open ? (
        <ul className="space-y-1 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-700">
          {(pillar.components ?? []).map((c) => (
            <li key={c.key} className="flex justify-between gap-2">
              <span className="text-slate-500">{c.label}</span>
              <span className="tabular-nums font-medium">
                {c.unit === 'quota'
                  ? fmtQuotaFixed(c.value == null || c.value === '' ? null : Number(c.value))
                  : fmtValue(c.value, c.unit)}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  )
}

export function CecchinoBalanceV5Panel({ balance, identityConsistency, snapshotMeta }: Props) {
  if (!balance) {
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <h3 className={todaySectionTitle}>{PANEL_TITLE}</h3>
        <p className={`mt-2 ${todaySectionSubtitle}`}>Analisi non disponibile per questa partita.</p>
      </section>
    )
  }

  if (isIdentityMismatch(balance, identityConsistency, snapshotMeta)) {
    return (
      <section className={`${todayCard} ${todayCardPadding}`}>
        <h3 className={todaySectionTitle}>{PANEL_TITLE}</h3>
        <p
          role="alert"
          className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950"
        >
          {blockedAlertMessage(snapshotMeta)}
        </p>
      </section>
    )
  }

  const pillars = resolvePillars(balance)
  const pairs = (balance.market_deviation?.pairs ?? []).filter(marketRowHasAnyData)
  const showHistoricalBox =
    snapshotMeta?.mode === 'historical_snapshot' &&
    (snapshotMeta.status === 'verified' || snapshotMeta.status === 'partial')

  return (
    <section className="space-y-4">
      <div>
        <h3 className={todaySectionTitle}>{PANEL_TITLE}</h3>
        <p className={`mt-1 ${todaySectionSubtitle}`}>{PANEL_SUBTITLE}</p>
        <p className="mt-1 text-xs text-slate-500">{INDEX_DISCLAIMER}</p>
      </div>

      {showHistoricalBox ? (
        <div className="rounded-lg border border-sky-200/80 bg-sky-50/70 px-3 py-2.5 text-sm text-slate-800">
          <p className="text-xs font-semibold uppercase tracking-wide text-sky-900/80">
            Snapshot storico pre-match
          </p>
          <p className="mt-1 text-xs leading-relaxed text-slate-700">
            {snapshotMeta?.status === 'partial' ? HIST_PARTIAL_TEXT : HIST_VERIFIED_TEXT}
          </p>
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-600">
            {snapshotMeta?.scan_date ? <li>Scan: {snapshotMeta.scan_date}</li> : null}
            {snapshotMeta?.kickoff ? <li>Kickoff: {snapshotMeta.kickoff}</li> : null}
            {snapshotMeta?.odds_fetched_at ? (
              <li>Quote: {snapshotMeta.odds_fetched_at}</li>
            ) : null}
            {snapshotMeta?.book_snapshot_status ? (
              <li>{bookStatusLabel(snapshotMeta.book_snapshot_status)}</li>
            ) : null}
          </ul>
        </div>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2">
        {pillars.map((p, i) => (
          <PillarCard key={p.key} pillar={p} number={i + 1} />
        ))}
      </div>

      {balance.structural_summary ? (
        <p className="text-sm leading-relaxed text-slate-700">{balance.structural_summary}</p>
      ) : null}

      <div className={`${todayCard} ${todayCardPadding}`}>
        <h4 className="text-sm font-semibold text-slate-900">
          {balance.market_deviation?.title ?? 'Scostamento dal mercato'}
        </h4>
        <p className="mt-0.5 text-xs text-slate-500">
          {balance.market_deviation?.subtitle ??
            'Lo scostamento descrive la distanza tra Cecchino e mercato.'}
        </p>
        {balance.market_deviation?.status === 'unavailable' || pairs.length === 0 ? (
          <p className="mt-2 text-xs text-slate-500">
            {balance.market_deviation?.reading || 'Scostamento dal mercato storico non disponibile.'}
          </p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="text-slate-500">
                <tr>
                  <th className="py-1 pr-3">Mercato</th>
                  <th className="py-1 pr-3">Prob. Cecchino</th>
                  <th className="py-1 pr-3">Prob. Book</th>
                  <th className="py-1 pr-3">Diff.</th>
                  <th className="py-1 pr-3">|Diff.|</th>
                  <th className="py-1 pr-3">Quota Cecch.</th>
                  <th className="py-1 pr-3">Quota Book</th>
                  <th className="py-1 pr-3">Confronto probabilità</th>
                </tr>
              </thead>
              <tbody>
                {pairs.map((pair) => (
                  <tr key={pair.key} className="border-t border-slate-100">
                    <td className="py-1.5 pr-3 font-medium text-slate-800">{pair.label}</td>
                    <td className="py-1.5 pr-3 tabular-nums">
                      {fmtValue(pair.prob_cecchino_norm ?? pair.prob_cecchino_pct ?? null, 'pct')}
                    </td>
                    <td className="py-1.5 pr-3 tabular-nums">
                      {fmtValue(pair.prob_book_norm ?? pair.prob_book_pct ?? null, 'pct')}
                    </td>
                    <td className="py-1.5 pr-3 tabular-nums">
                      {fmtValue(pair.signed_diff ?? pair.signed_diff_pp ?? null, 'pp')}
                    </td>
                    <td className="py-1.5 pr-3 tabular-nums">
                      {fmtValue(pair.abs_diff ?? pair.deviation_pp ?? pair.abs_diff_pp ?? null, 'pp')}
                    </td>
                    <td className="py-1.5 pr-3 tabular-nums">
                      {fmtQuotaFixed(pair.quota_cecchino ?? null)}
                    </td>
                    <td className="py-1.5 pr-3 tabular-nums">
                      {fmtQuotaFixed(pair.quota_book ?? null)}
                    </td>
                    <td className="py-1.5 pr-3 text-slate-600">
                      {pair.direction_label ?? pair.direction ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {balance.market_deviation?.status !== 'unavailable' && pairs.length > 0 ? (
          <p className="mt-3 text-xs leading-relaxed text-slate-600">
            {balance.market_deviation?.reading ||
              'Lo scostamento descrive la distanza tra Cecchino e mercato. Non stabilisce quale dei due abbia ragione e non modifica i quattro pilastri.'}
          </p>
        ) : null}
      </div>
    </section>
  )
}
