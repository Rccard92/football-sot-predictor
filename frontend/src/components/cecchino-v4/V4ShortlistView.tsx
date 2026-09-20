import type { CecchinoV4Api, V4ShortlistDayStatus, V4ShortlistItem } from '../../lib/cecchinoV4Api'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from '../cecchino/cecchinoTodayStyles'
import { noPlayReasonLabel, V4_TOP_PLAYS, v4Chip, v4Label, v4Mono } from './constants'
import { capitalize, digestShort, fmtDayLong, fmtInterval, fmtProfit, fmtQuota, fmtSignedPct, fmtTimeRome } from './format'
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

/** Riga a tabella: posizione, partita e orario, giocata con i numeri, stato. */
function ShortlistRow({ item }: { item: V4ShortlistItem }) {
  const observed = item.advised === false
  const profitOk = item.expected_profit != null && item.expected_profit >= 0.03
  return (
    <li
      className={`grid gap-x-3 gap-y-1.5 px-3 py-2.5 lg:grid-cols-[2rem_minmax(0,5fr)_minmax(0,6fr)_auto] lg:items-center ${
        item.status === 'ritirata' ? 'bg-red-50/40' : 'odd:bg-white even:bg-slate-50/60'
      }`}
      data-testid="v4-shortlist-row"
    >
      <span className={`${v4Mono} text-sm font-semibold text-slate-500`}>{item.rank}</span>
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-slate-900">
          {item.home_team} - {item.away_team}
        </p>
        <p className={`${v4Mono} text-xs text-slate-500`}>{fmtTimeRome(item.kickoff_at)}</p>
      </div>
      <div className="min-w-0">
        <p className={`text-sm font-medium ${observed ? 'text-slate-700' : 'text-slate-900'}`}>{item.label}</p>
        <p className={`${v4Mono} text-xs text-slate-600`}>
          {fmtInterval(item.p, item.lo, item.hi)} · {fmtQuota(item.quota_used)} ·{' '}
          <span className={!observed && profitOk ? 'font-semibold text-emerald-700' : 'font-semibold text-slate-700'}>
            {fmtProfit(item.expected_profit)}
          </span>
          {item.clv != null ? (
            <span className="text-slate-500">
              {' '}
              · CLV {fmtSignedPct(item.clv, 1)}
              {item.closing_quota != null ? ` · chiusura ${fmtQuota(item.closing_quota)}` : ''}
            </span>
          ) : null}
        </p>
        {item.status === 'ritirata' && item.withdraw_reason ? (
          <p className="text-xs text-red-700">{item.withdraw_reason}</p>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-1.5 lg:justify-end">
        {observed ? <span className={`${v4Chip} bg-slate-100 text-slate-600 ring-slate-200`}>In osservazione</span> : null}
        <V4ShortlistStatusChip status={item.status} result={item.result} />
      </div>
    </li>
  )
}

function RowsCard({ title, testId, items, empty }: { title: string; testId: string; items: V4ShortlistItem[]; empty: string }) {
  return (
    <section className={`${todayCard} overflow-hidden`}>
      <h3 className={`${todaySectionTitle} px-4 pt-4 pb-2 sm:px-5`} data-testid={testId}>
        {title}
      </h3>
      {items.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-slate-500 sm:px-5">{empty}</p>
      ) : (
        <ul className="border-t border-slate-100">
          {items.map((i) => (
            <ShortlistRow key={`${i.fixture_id}-${i.market_key}`} item={i} />
          ))}
        </ul>
      )}
    </section>
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
    <div className="space-y-4" data-testid="v4-shortlist">
      <section className={`${todayCard} ${todayCardPadding} space-y-2`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className={todaySectionTitle}>Shortlist di {fmtDayLong(date)}</h2>
            <p className={todaySectionSubtitle}>
              {data.items.length} giocate, una per partita, ordinate per profitto atteso. Le prime {V4_TOP_PLAYS} sono le Top.
            </p>
          </div>
          <span className={`${v4Chip} ${day.cls}`} data-testid="v4-shortlist-status">
            {day.label}
          </span>
        </div>
        {data.sealed_at ? (
          <p className="text-xs text-slate-500" data-testid="v4-shortlist-seal">
            Sigillata alle {fmtTimeRome(data.sealed_at)} · impronta <span className={v4Mono}>{digestShort(data.digest)}</span>
          </p>
        ) : (
          <p className="text-xs text-slate-500">Non ancora sigillata: le giocate possono cambiare fino alle formazioni.</p>
        )}
        {hasObserved ? (
          <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700" role="note">
            {banner}
          </p>
        ) : null}
      </section>

      {data.items.length === 0 ? (
        <V4Empty title="Nessuna giocata in shortlist per questo giorno" hint="Le astensioni sono elencate sotto." />
      ) : (
        <>
          <RowsCard title={`Top · ${top.length}`} testId="v4-shortlist-top-title" items={top} empty="Nessuna giocata Top." />
          <RowsCard
            title={`Altre · ${others.length}`}
            testId="v4-shortlist-others-title"
            items={others}
            empty="Nessuna altra giocata oltre le Top."
          />
        </>
      )}

      <section className={`${todayCard} ${todayCardPadding} space-y-2`}>
        <h3 className={todaySectionTitle}>Astensioni</h3>
        {data.abstentions.length === 0 ? (
          <p className="text-sm text-slate-500">Nessuna partita scartata.</p>
        ) : (
          <ul className="space-y-2">
            {data.abstentions.map((a) => (
              <li key={a.reason}>
                <p className="text-sm text-slate-800">
                  <span className="font-medium">{a.label ? capitalize(a.label) : capitalize(noPlayReasonLabel(a.reason))}</span>
                  <span className={`${v4Mono} text-slate-500`}>
                    {' '}
                    · {a.count} {a.count === 1 ? 'partita' : 'partite'}
                  </span>
                </p>
                {a.examples.length > 0 ? (
                  <p className="text-xs text-slate-500">
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
