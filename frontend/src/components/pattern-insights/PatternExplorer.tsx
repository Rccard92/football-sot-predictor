import { useCallback, useEffect, useState } from 'react'
import { Section } from './PatternInsightsShell'
import { PatternDetailPanel } from './PatternDetailPanel'
import { ABOVE_CHANCE, BELOW_CHANCE } from './PatternValidationBlocks'
import {
  VERDICT_LABELS,
  getPatternInsightCandidates,
  type OosStats,
  type PatternHold,
  type PatternInsightCandidate,
  type PatternInsightTargetType,
  type PatternSeasonRow,
  type PatternSort,
} from '../../lib/patternInsightsApi'

const PAGE_SIZE = 25

const MARKET_OPTIONS: Array<[string, string]> = [
  ['HOME', 'Segno 1'],
  ['DRAW', 'Segno X'],
  ['AWAY', 'Segno 2'],
  ['HOME_PT', 'Segno 1 primo tempo'],
  ['DRAW_PT', 'Segno X primo tempo'],
  ['AWAY_PT', 'Segno 2 primo tempo'],
  ['ONE_X', '1X'],
  ['X_TWO', 'X2'],
  ['ONE_TWO', '12'],
  ['OVER_0_5', 'Over 0.5'],
  ['UNDER_0_5', 'Under 0.5'],
  ['OVER_1_5', 'Over 1.5'],
  ['UNDER_1_5', 'Under 1.5'],
  ['OVER_2_5', 'Over 2.5'],
  ['UNDER_2_5', 'Under 2.5'],
  ['OVER_3_5', 'Over 3.5'],
  ['UNDER_3_5', 'Under 3.5'],
]

function pct(v: number | null | undefined, d = 1): string {
  if (v == null) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(d)}%`
}

function units(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(1)} u`
}

function tone(v: number | null | undefined): string {
  if (v == null) return 'var(--pi-muted)'
  return v >= 0 ? ABOVE_CHANCE : BELOW_CHANCE
}

export function VerdictChip({ verdict }: { verdict: OosStats['verdict'] | null | undefined }) {
  if (!verdict) return <span style={{ color: 'var(--pi-muted)' }}>—</span>
  const color =
    verdict === 'confirmed'
      ? ABOVE_CHANCE
      : verdict === 'rejected'
        ? BELOW_CHANCE
        : verdict === 'attenuated'
          ? 'var(--pi-warn)'
          : 'var(--pi-muted)'
  const icon = verdict === 'confirmed' ? '✓' : verdict === 'rejected' ? '✗' : verdict === 'attenuated' ? '~' : '·'
  return (
    <span
      className="whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-semibold"
      style={{ color: 'var(--pi-text)', background: 'rgba(255,255,255,0.03)', border: `1px solid ${color}` }}
    >
      <span style={{ color }}>{icon}</span> {VERDICT_LABELS[verdict]}
    </span>
  )
}

function SeasonCell({ s, isMarket }: { s: PatternSeasonRow | undefined; isMarket: boolean }) {
  if (!s || s.n === 0) {
    return (
      <td className="whitespace-nowrap text-[11px]" style={{ borderLeft: '1px solid var(--pi-border)', color: 'var(--pi-muted)' }}>
        nessuna partita
      </td>
    )
  }
  const metric = isMarket ? s.roi_pct : s.deviation_pct
  return (
    <td className="whitespace-nowrap tabular-nums" style={{ borderLeft: '1px solid var(--pi-border)' }}>
      <div className="flex items-center gap-2">
        <span className="font-semibold" style={{ color: tone(metric) }}>
          {isMarket ? pct(metric) : `${metric != null && metric > 0 ? '+' : ''}${metric?.toFixed(1) ?? '—'} pt`}
        </span>
        {s.role === 'discovery' ? (
          <span className="text-[10px]" style={{ color: '#b9adf2' }}>
            scoperta
          </span>
        ) : (
          <VerdictChip verdict={s.verdict} />
        )}
      </div>
      <div className="text-[10px]" style={{ color: 'var(--pi-muted)' }}>
        {s.n} giocate · {s.wins}V {s.losses}P · {s.win_rate_pct?.toFixed(1)}%
      </div>
      {isMarket && (
        <div className="text-[10px]" style={{ color: 'var(--pi-muted)' }}>
          {units(s.profit_units)}
          {s.avg_quota != null ? ` · quota ${s.avg_quota.toFixed(2)}` : ''}
        </div>
      )}
    </td>
  )
}

function Row({
  c,
  seasons,
  onOpen,
}: {
  c: PatternInsightCandidate
  seasons: Array<string | null>
  onOpen: () => void
}) {
  const isMarket = c.target_type === 'market'
  const t = c.total
  const bySeason = new Map((c.seasons ?? []).map((s) => [s.season_label, s]))
  const allConfirmed = t != null && t.validations_total > 0 && t.validations_confirmed === t.validations_total
  return (
    <tr onClick={onOpen} style={{ cursor: 'pointer' }} title="Apri dettaglio: stagioni, campionati e partite">
      <td className="whitespace-nowrap font-semibold">{c.target_label}</td>
      <td style={{ minWidth: 240, maxWidth: 340 }}>
        <div className="leading-snug">{c.filters_text_human}</div>
        {c.refined_from_text ? (
          <div className="mt-0.5 text-[10px]" style={{ color: 'var(--pi-muted)' }}>
            raffinamento di un pattern piu&apos; semplice
          </div>
        ) : null}
      </td>
      <td className="whitespace-nowrap tabular-nums" style={{ borderLeft: '1px solid var(--pi-border)', background: 'rgba(30,166,143,0.05)' }}>
        {t ? (
          <>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold" style={{ color: tone(isMarket ? t.roi_pct : t.deviation_pct) }}>
                {isMarket ? pct(t.roi_pct) : `${t.deviation_pct != null && t.deviation_pct > 0 ? '+' : ''}${t.deviation_pct?.toFixed(1) ?? '—'} pt`}
              </span>
              {isMarket && (
                <span className="text-xs font-semibold" style={{ color: tone(t.profit_units) }}>
                  {units(t.profit_units)}
                </span>
              )}
            </div>
            <div className="text-[10px]" style={{ color: 'var(--pi-muted)' }}>
              {t.n} giocate · {t.wins} vinte · {t.losses} perse · {t.win_rate_pct?.toFixed(1)}%
            </div>
            <div className="mt-0.5 text-[10px] font-semibold" style={{ color: allConfirmed ? ABOVE_CHANCE : 'var(--pi-muted)' }}>
              {allConfirmed ? '✓ ' : ''}confermato {t.validations_confirmed}/{t.validations_total} verifiche
            </div>
          </>
        ) : (
          '—'
        )}
      </td>
      {seasons.map((label) => (
        <SeasonCell key={label ?? 'x'} s={bySeason.get(label)} isMarket={isMarket} />
      ))}
    </tr>
  )
}

export function PatternExplorer({ defaultMinN = 50 }: { defaultMinN?: number }) {
  const [targetType, setTargetType] = useState<PatternInsightTargetType>('market')
  const [targetKey, setTargetKey] = useState<string>('')
  const [hold, setHold] = useState<PatternHold>('positive_total')
  const [minN, setMinN] = useState(defaultMinN)
  const [sort, setSort] = useState<PatternSort>('total_profit_desc')
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [items, setItems] = useState<PatternInsightCandidate[]>([])
  const [seasons, setSeasons] = useState<Array<string | null>>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detailId, setDetailId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getPatternInsightCandidates({
        targetType,
        targetKey: targetType === 'market' && targetKey ? targetKey : undefined,
        minN,
        hold,
        sort,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      })
      setTotal(res.total)
      setItems(res.items)
      setSeasons(res.seasons ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore caricamento pattern')
    } finally {
      setLoading(false)
    }
  }, [targetType, targetKey, minN, hold, sort, page])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setPage(0)
  }, [targetType, targetKey, minN, hold, sort])

  const isMarket = targetType === 'market'
  const verifications = Math.max(0, seasons.length - 1)

  return (
    <Section
      title="Esplora i pattern"
      note={`${total.toLocaleString('it-IT')} pattern con i filtri attuali · clicca una riga per campionati e partite`}
    >
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
          Tenuta
          <select className="pi-select" value={hold} onChange={(e) => setHold(e.target.value as PatternHold)}>
            <option value="positive_total">
              {isMarket ? 'In attivo sul totale delle stagioni' : 'Effetto ancora presente sul totale'}
            </option>
            <option value="confirmed_all">
              Confermati in tutte le {seasons.length || 4} stagioni
            </option>
            <option value="all">Tutti, anche respinti (rumore)</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
          Tipo di bersaglio
          <select
            className="pi-select"
            value={targetType}
            onChange={(e) => {
              const v = e.target.value as PatternInsightTargetType
              setTargetType(v)
              setSort(v === 'market' ? 'total_profit_desc' : 'total_deviation_desc')
            }}
          >
            <option value="market">Mercati con quota</option>
            <option value="synthetic">Tiri / corner / cartellini</option>
          </select>
        </label>
        {isMarket && (
          <label className="flex flex-col gap-1 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            Mercato
            <select className="pi-select" value={targetKey} onChange={(e) => setTargetKey(e.target.value)}>
              <option value="">Tutti i mercati</option>
              {MARKET_OPTIONS.map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="flex flex-col gap-1 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
          Giocate minime in scoperta
          <input
            type="number"
            min={20}
            step={10}
            className="pi-input w-24"
            value={minN}
            onChange={(e) => setMinN(Math.max(20, Number(e.target.value) || 20))}
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
          Ordinamento
          <select className="pi-select" value={sort} onChange={(e) => setSort(e.target.value as PatternSort)}>
            {isMarket ? (
              <>
                <option value="total_profit_desc">Profitto totale</option>
                <option value="total_roi_desc">ROI totale</option>
              </>
            ) : (
              <option value="total_deviation_desc">Scarto totale</option>
            )}
            <option value="total_n_desc">Giocate totali</option>
          </select>
        </label>
      </div>

      {hold === 'confirmed_all' && (
        <div
          className="mb-3 rounded-xl border px-3 py-2 text-[11px] leading-relaxed"
          style={{ borderColor: 'rgba(251,191,36,0.35)', background: 'rgba(251,191,36,0.07)', color: '#f6d68a' }}
        >
          Pattern promossi nel {seasons[0] ?? 'primo anno'} e confermati in ognuna delle {verifications} stagioni
          successive. Attenzione: su migliaia di pattern provati, una parte passa tutte le verifiche anche per
          caso. Il blocco &quot;Tenuta nel tempo&quot; qui sopra dice quanti se ne aspetterebbero per pura fortuna.
        </div>
      )}

      {error && (
        <div className="mb-3 text-xs" style={{ color: '#fca5a5' }}>
          {error}
        </div>
      )}

      <div className="pi-scroll" style={{ maxHeight: 680 }}>
        <table className="pi-table">
          <thead>
            <tr>
              <th>Bersaglio</th>
              <th>Pattern</th>
              <th style={{ color: '#7fd9c8', borderLeft: '1px solid var(--pi-border)' }}>
                Totale {seasons.length} stagioni
              </th>
              {seasons.map((s, i) => (
                <th
                  key={s ?? i}
                  style={{ color: i === 0 ? '#b9adf2' : 'var(--pi-muted)', borderLeft: '1px solid var(--pi-border)' }}
                >
                  {s}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <Row key={c.id} c={c} seasons={seasons} onOpen={() => setDetailId(c.id)} />
            ))}
          </tbody>
        </table>
        {loading && (
          <div className="p-3 text-xs" style={{ color: 'var(--pi-muted)' }}>
            Caricamento…
          </div>
        )}
        {!loading && items.length === 0 && (
          <div className="p-3 text-xs" style={{ color: 'var(--pi-muted)' }}>
            Nessun pattern con questi filtri.
          </div>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between text-[11px]" style={{ color: 'var(--pi-muted)' }}>
        <button
          type="button"
          className="pi-btn"
          disabled={page === 0}
          onClick={() => setPage((p) => Math.max(0, p - 1))}
        >
          ← Precedenti
        </button>
        <span className="tabular-nums">
          {total === 0 ? 0 : page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} di{' '}
          {total.toLocaleString('it-IT')}
        </span>
        <button
          type="button"
          className="pi-btn"
          disabled={(page + 1) * PAGE_SIZE >= total}
          onClick={() => setPage((p) => p + 1)}
        >
          Successivi →
        </button>
      </div>

      {detailId != null && (
        <PatternDetailPanel candidateId={detailId} onClose={() => setDetailId(null)} />
      )}
    </Section>
  )
}
