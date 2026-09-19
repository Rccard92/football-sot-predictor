import type { CecchinoV4Api, V4ShortlistDayStatus, V4ShortlistItem } from '../../lib/cecchinoV4Api'
import { todayCard, todayCardPadding } from '../cecchino/cecchinoTodayStyles'
import { noPlayReasonLabel, V4_TOP_PLAYS, v4Chip, v4Label, v4SectionTitle } from './constants'
import {
  capitalize,
  digestShort,
  fmtDayLong,
  fmtInterval,
  fmtProfit,
  fmtQuota,
  fmtSignedPct,
  fmtTimeRome,
} from './format'
import { useV4Query } from './useV4Query'
import { V4ShortlistStatusChip } from './V4Chips'
import { V4Empty, V4Error, V4Loading } from './V4States'

type Props = {
  api: CecchinoV4Api
  date: string
}

const DAY_STATUS: Record<V4ShortlistDayStatus, { label: string; cls: string }> = {
  provvisoria: { label: 'Provvisoria', cls: 'bg-amber-100 text-amber-800 ring-amber-200' },
  confermata: { label: 'Confermata', cls: 'bg-emerald-100 text-emerald-800 ring-emerald-200' },
  regolata: { label: 'Regolata', cls: 'bg-slate-100 text-slate-700 ring-slate-200' },
}

function ShortlistRow({ item }: { item: V4ShortlistItem }) {
  const observed = item.advised === false
  return (
    <li
      className={`grid gap-2 rounded-xl border bg-white p-4 shadow-sm lg:grid-cols-[3rem_minmax(0,2fr)_minmax(0,2fr)_auto] lg:items-center ${
        item.status === 'ritirata' ? 'border-red-200' : 'border-slate-200'
      }`}
      data-testid="v4-shortlist-row"
    >
      <span className="text-xl font-bold tabular-nums text-slate-900">{item.rank}</span>
      <div className="min-w-0">
        <p className="truncate text-xl font-semibold text-slate-900">
          {item.home_team} - {item.away_team}
        </p>
        <p className="text-base text-slate-500">alle {fmtTimeRome(item.kickoff_at)}</p>
      </div>
      <div className="min-w-0">
        <p className="text-base font-semibold text-slate-900">{item.label}</p>
        <p className="text-base tabular-nums text-slate-700">
          probabilità {fmtInterval(item.p, item.lo, item.hi)} · quota {fmtQuota(item.quota_used)} · profitto{' '}
          <span className={item.expected_profit != null && item.expected_profit >= 0.03 ? 'font-semibold text-emerald-700' : ''}>
            {fmtProfit(item.expected_profit)}
          </span>
        </p>
      </div>
      <div className="flex flex-col items-start gap-1 lg:items-end">
        <div className="flex flex-wrap items-center gap-2">
          {observed ? (
            <span className={`${v4Chip} bg-sky-100 text-sky-800 ring-sky-200`}>In osservazione</span>
          ) : null}
          <V4ShortlistStatusChip status={item.status} result={item.result} />
        </div>
        {item.status === 'ritirata' && item.withdraw_reason ? (
          <p className="text-base text-red-700">{item.withdraw_reason}</p>
        ) : null}
        {item.clv != null ? (
          <p className="text-base tabular-nums text-slate-600">
            CLV {fmtSignedPct(item.clv, 1)}
            {item.closing_quota != null ? ` · chiusura ${fmtQuota(item.closing_quota)}` : ''}
          </p>
        ) : null}
      </div>
    </li>
  )
}

export function V4ShortlistView({ api, date }: Props) {
  const q = useV4Query(`shortlist:${date}`, (signal) => api.getShortlist(date, signal))

  if (q.loading) return <V4Loading label="Carico la shortlist…" rows={4} />
  if (q.error) return <V4Error message={q.error} onRetry={q.reload} />
  if (!q.data) return null

  const data = q.data
  const sorted = [...data.items].sort((a, b) => a.rank - b.rank)
  const top = sorted.filter((i) => i.top || i.rank <= V4_TOP_PLAYS)
  const others = sorted.filter((i) => !top.includes(i))
  const hasObserved = data.advised === false || data.items.some((i) => i.advised === false)
  const banner = data.banner || 'Esame E4 non superato: giocate classiche in osservazione, non consigliate'
  const day = DAY_STATUS[data.status] ?? DAY_STATUS.provvisoria

  return (
    <div className="space-y-6" data-testid="v4-shortlist">
      <section className={`${todayCard} ${todayCardPadding} space-y-3`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className={v4SectionTitle}>Shortlist di {fmtDayLong(date)}</h2>
          <span className={`${v4Chip} ${day.cls}`} data-testid="v4-shortlist-status">
            {day.label}
          </span>
        </div>
        {data.sealed_at ? (
          <p className="text-base text-slate-700" data-testid="v4-shortlist-seal">
            Sigillata alle {fmtTimeRome(data.sealed_at)} · impronta{' '}
            <span className="font-mono text-base">{digestShort(data.digest)}</span>
          </p>
        ) : (
          <p className="text-base text-slate-500">Non ancora sigillata: le giocate possono cambiare fino alle formazioni.</p>
        )}
        {hasObserved ? (
          <p className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-2 text-base text-sky-900" role="note">
            {banner}
          </p>
        ) : null}
        <p className="text-base text-slate-600">
          {data.items.length} giocate, una per partita, ordinate per profitto atteso. Le prime {V4_TOP_PLAYS} sono le Top.
        </p>
      </section>

      {data.items.length === 0 ? (
        <V4Empty title="Nessuna giocata in shortlist per questo giorno" hint="Le astensioni sono elencate sotto." />
      ) : (
        <>
          <section className="space-y-3">
            <h3 className={v4SectionTitle} data-testid="v4-shortlist-top-title">
              Top · {top.length}
            </h3>
            <ul className="space-y-3">
              {top.map((i) => (
                <ShortlistRow key={`${i.fixture_id}-${i.market_key}`} item={i} />
              ))}
            </ul>
          </section>
          <section className="space-y-3">
            <h3 className={v4SectionTitle} data-testid="v4-shortlist-others-title">
              Altre · {others.length}
            </h3>
            {others.length === 0 ? (
              <p className="text-base text-slate-500">Nessuna altra giocata oltre le Top.</p>
            ) : (
              <ul className="space-y-3">
                {others.map((i) => (
                  <ShortlistRow key={`${i.fixture_id}-${i.market_key}`} item={i} />
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      <section className={`${todayCard} ${todayCardPadding} space-y-3`}>
        <h3 className={v4SectionTitle}>Astensioni</h3>
        {data.abstentions.length === 0 ? (
          <p className="text-base text-slate-500">Nessuna partita scartata.</p>
        ) : (
          <ul className="space-y-3">
            {data.abstentions.map((a) => (
              <li key={a.reason} className="space-y-1">
                <p className="text-base font-semibold text-slate-900">
                  {a.label ? capitalize(a.label) : capitalize(noPlayReasonLabel(a.reason))} · {a.count}{' '}
                  {a.count === 1 ? 'partita' : 'partite'}
                </p>
                {a.examples.length > 0 ? (
                  <p className="text-base text-slate-600">
                    <span className={v4Label}>Esempi</span> {a.examples.join(' · ')}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
