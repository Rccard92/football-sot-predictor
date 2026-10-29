import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { ChecklistEditor } from '../components/analyst/ChecklistEditor'
import { useAuth } from '../contexts/AuthContext'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from '../components/cecchino/cecchinoTodayStyles'
import { AdminHttpError } from '../lib/api'
import {
  CHECKLIST_LABELS,
  OUTCOME_LABELS,
  createCycle,
  deleteEntry,
  formatEuro,
  getCycle,
  getJournalMeta,
  getJournalReport,
  journalExportUrl,
  listAnalysts,
  listCycles,
  listEntries,
  updateCycle,
  updateEntry,
  type Checklist,
  type Cycle,
  type Filters,
  type JournalEntry,
  type JournalMeta,
  type JournalReport,
  type MethodKey,
  type ReportRow,
} from '../lib/analystJournalApi'

type Tab = 'giocate' | 'progressioni' | 'report'
type Period = 'week' | 'month' | '30d' | '90d' | 'all'

const PERIODS: { key: Period; label: string }[] = [
  { key: 'week', label: 'Questa settimana' },
  { key: 'month', label: 'Questo mese' },
  { key: '30d', label: 'Ultimi 30 giorni' },
  { key: '90d', label: 'Ultimi 90 giorni' },
  { key: 'all', label: 'Tutto' },
]

const btn = 'rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[13px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60'
const btnPrimary = 'rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60'
const inputClass = 'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none'

const OUTCOME_BADGE: Record<string, string> = {
  pending: 'bg-slate-100 text-slate-600',
  won: 'bg-emerald-50 text-emerald-800',
  lost: 'bg-rose-50 text-rose-800',
  void: 'bg-amber-50 text-amber-800',
}

function isoDate(d: Date): string {
  return d.toLocaleDateString('sv-SE', { timeZone: 'Europe/Rome' })
}

function periodFilters(p: Period): Filters {
  const today = new Date()
  if (p === 'all') return {}
  if (p === 'week') {
    const d = new Date(today)
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
    return { date_from: isoDate(d) }
  }
  if (p === 'month') return { date_from: `${isoDate(today).slice(0, 7)}-01` }
  const d = new Date(today)
  d.setDate(d.getDate() - (p === '30d' ? 30 : 90))
  return { date_from: isoDate(d) }
}

function errorText(e: unknown): string {
  return e instanceof AdminHttpError ? e.message : e instanceof Error ? e.message : 'Operazione non riuscita'
}

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? '—' : `${v.toLocaleString('it-IT', { maximumFractionDigits: 1 })}%`
}

function kickoffText(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('it-IT', { timeZone: 'Europe/Rome', weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function money(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${v > 0 ? '+' : ''}${formatEuro(v)}`
}

/** Diario analisi (dal 30/10/2026): sostituisce il file "IL CECCHINO (Report)". */
export function DiarioAnalisiPage() {
  const [tab, setTab] = useState<Tab>('giocate')
  const [period, setPeriod] = useState<Period>('month')
  const [meta, setMeta] = useState<JournalMeta | null>(null)
  const [analysts, setAnalysts] = useState<{ id: number; name: string }[]>([])
  const [userId, setUserId] = useState<number | null>(null)

  useEffect(() => {
    getJournalMeta().then(setMeta, () => undefined)
    listAnalysts().then((r) => setAnalysts(r.analysts), () => undefined)
  }, [])

  const filters = useMemo<Filters>(() => ({ ...periodFilters(period), user_id: userId }), [period, userId])

  return (
    <div className="space-y-5 pb-8">
      <header className="flex flex-wrap items-end justify-between gap-3 pt-2">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Diario analisi</h1>
          <p className="mt-1 text-sm text-slate-600">
            Le giocate scelte da Cecchino Today, Bet Builder e Bet Builder V3: scheda pronostico, esiti automatici,
            progressioni di cassa e report.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {meta?.is_admin && analysts.length ? (
            <select
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              value={userId ?? ''}
              onChange={(e) => setUserId(e.target.value ? Number(e.target.value) : null)}
              aria-label="Analista"
            >
              <option value="">Tutti gli analisti</option>
              {analysts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          ) : null}
          <select className="rounded-lg border border-slate-300 px-3 py-2 text-sm" value={period} onChange={(e) => setPeriod(e.target.value as Period)} aria-label="Periodo">
            {PERIODS.map((p) => (
              <option key={p.key} value={p.key}>
                {p.label}
              </option>
            ))}
          </select>
          <a className={btn} href={journalExportUrl(filters)}>
            Esporta Excel
          </a>
        </div>
      </header>

      <div className="inline-flex overflow-hidden rounded-xl border border-slate-200 bg-slate-100/80 p-1" role="tablist">
        {(
          [
            ['giocate', 'Giocate'],
            ['progressioni', 'Progressioni'],
            ['report', 'Report'],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`rounded-lg px-4 py-1.5 text-sm font-semibold ${tab === key ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'giocate' && meta ? <EntriesTab meta={meta} filters={filters} /> : null}
      {tab === 'progressioni' && meta ? <CyclesTab meta={meta} userId={userId} /> : null}
      {tab === 'report' ? <ReportTab filters={filters} /> : null}
    </div>
  )
}

// --- giocate --------------------------------------------------------------------------------------

function EntriesTab({ meta, filters }: { meta: JournalMeta; filters: Filters }) {
  const [entries, setEntries] = useState<JournalEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<number | null>(null)

  const fetchEntries = useCallback(
    () =>
      listEntries(filters).then(
        (r) => {
          setEntries(r.entries)
          setError(null)
        },
        (e: unknown) => setError(errorText(e)),
      ),
    [filters],
  )
  useEffect(() => {
    void fetchEntries()
  }, [fetchEntries])

  const weeks = useMemo(() => {
    const out = new Map<string, JournalEntry[]>()
    for (const e of entries ?? []) out.set(e.week, [...(out.get(e.week) ?? []), e])
    return [...out.entries()]
  }, [entries])

  if (error) return <p className="text-sm text-rose-700">{error}</p>
  if (entries === null) return <p className="text-sm text-slate-500">Carico le giocate…</p>
  if (!entries.length) {
    return (
      <div className={`${todayCard} ${todayCardPadding} text-sm text-slate-600`}>
        Nessuna giocata nel periodo. Le aggiungi con «+ Aggiungi al diario» da Cecchino Today, Bet Builder o Bet Builder V3.
      </div>
    )
  }
  const open = entries.find((e) => e.id === openId) ?? null
  return (
    <div className="space-y-4">
      {weeks.map(([week, rows]) => {
        const settled = rows.filter((r) => r.outcome === 'won' || r.outcome === 'lost')
        const won = settled.filter((r) => r.outcome === 'won').length
        const profit = rows.reduce((s, r) => s + (r.profit ?? 0), 0)
        return (
          <section key={week} className={`${todayCard} overflow-hidden`}>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/70 px-4 py-2">
              <p className="text-sm font-semibold text-slate-800">Settimana {week.split('-W')[1]} · {week.split('-W')[0]}</p>
              <p className="text-[13px] text-slate-600">
                {rows.length} giocate · {won}/{settled.length} vinte · {money(profit)}
              </p>
            </div>
            <div className="divide-y divide-slate-100">
              {rows.map((e) => (
                <button key={e.id} type="button" onClick={() => setOpenId(e.id)} className="grid w-full gap-1 px-4 py-2.5 text-left hover:bg-slate-50 sm:grid-cols-[110px_minmax(0,1fr)_110px_70px_90px_110px_90px] sm:items-center sm:gap-3">
                  <span className="text-[13px] text-slate-500">{kickoffText(e.kickoff)}</span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-slate-900">
                      {e.home_team} – {e.away_team}
                    </span>
                    <span className="block truncate text-[13px] text-slate-500">
                      {e.league_name} · {e.source_label}
                      {meta.is_admin && e.user_name ? ` · ${e.user_name}` : ''}
                    </span>
                  </span>
                  <span className="text-sm font-semibold text-slate-800">{e.market_label}</span>
                  <span className="text-sm tabular-nums text-slate-700">@ {e.quota}</span>
                  <span className="text-sm tabular-nums text-slate-700">{e.stake ? formatEuro(e.stake) : '—'}</span>
                  <span>
                    <span className={`rounded-full px-2 py-0.5 text-[12px] font-medium ${OUTCOME_BADGE[e.outcome]}`}>{OUTCOME_LABELS[e.outcome]}</span>
                    {e.result_ft ? <span className="ml-1.5 text-[13px] tabular-nums text-slate-500">{e.result_ft}{e.result_ht ? ` (${e.result_ht})` : ''}</span> : null}
                  </span>
                  <span className={`text-sm font-semibold tabular-nums ${(e.profit ?? 0) > 0 ? 'text-emerald-700' : (e.profit ?? 0) < 0 ? 'text-rose-700' : 'text-slate-500'}`}>
                    {e.profit !== null ? money(e.profit) : e.profit_units !== null ? `${e.profit_units > 0 ? '+' : ''}${e.profit_units} u` : ''}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )
      })}
      {open ? (
        <EntryDrawer
          entry={open}
          meta={meta}
          onClose={() => setOpenId(null)}
          onChanged={() => void fetchEntries()}
        />
      ) : null}
    </div>
  )
}

function EntryDrawer({ entry, meta, onClose, onChanged }: { entry: JournalEntry; meta: JournalMeta; onClose: () => void; onChanged: () => void }) {
  const { me } = useAuth()
  // solo il proprietario modifica; l'amministratore legge i diari degli altri
  const mine = Boolean(meta.can_write && me?.user && me.user.id === entry.user_id)
  const [checklist, setChecklist] = useState<Checklist>(entry.checklist)
  const [analysisNote, setAnalysisNote] = useState(entry.analysis_note ?? '')
  const [notes, setNotes] = useState(entry.notes ?? '')
  const [minutes, setMinutes] = useState(entry.minutes_spent ? String(entry.minutes_spent) : '')
  const [quota, setQuota] = useState(String(entry.quota))
  const [stake, setStake] = useState(entry.stake ? String(entry.stake) : '')
  const [busy, setBusy] = useState(false)

  const save = async () => {
    setBusy(true)
    try {
      const patch: Record<string, unknown> = { notes, minutes_spent: minutes ? Number(minutes) : null }
      if (!entry.locked) {
        patch.checklist = checklist
        patch.analysis_note = analysisNote
        patch.quota = Number(quota.replace(',', '.'))
        patch.stake = stake ? Number(stake.replace(',', '.')) : null
      }
      await updateEntry(entry.id, patch)
      toast.success('Salvato')
      onChanged()
      onClose()
    } catch (e) {
      toast.error(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!window.confirm('Togliere questa giocata dal diario?')) return
    setBusy(true)
    try {
      await deleteEntry(entry.id)
      toast.success('Giocata tolta')
      onChanged()
      onClose()
    } catch (e) {
      toast.error(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  const t = entry.tool
  const toolBits = [
    t.engine ? `motore ${t.engine}` : null,
    t.probability !== undefined && t.probability !== null ? `probabilità ${Math.round(t.probability > 1 ? t.probability : t.probability * 100)}%` : null,
    t.prob_cecchino ? `prob. Cecchino ${(t.prob_cecchino * 100).toFixed(0)}%` : null,
    t.index_score ? `indice ${Math.round(t.index_score)}` : null,
    t.quota_book ? `quota book ${t.quota_book}` : null,
  ].filter(Boolean)

  return (
    <div className="fixed inset-0 z-[65] flex justify-end bg-slate-900/40" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="h-full w-full max-w-xl space-y-4 overflow-y-auto bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[13px] text-slate-500">{kickoffText(entry.kickoff)} · {entry.league_name}</p>
            <h2 className="text-base font-semibold text-slate-900">
              {entry.home_team} – {entry.away_team}
            </h2>
            <p className="text-sm text-slate-700">
              <strong>{entry.market_label}</strong> @ {entry.quota} · {entry.source_label}
              {entry.user_name ? ` · ${entry.user_name}` : ''}
            </p>
          </div>
          <button type="button" className={btn} onClick={onClose}>
            Chiudi
          </button>
        </div>

        <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 text-sm text-slate-700">
          <p>
            Esito: <span className={`rounded-full px-2 py-0.5 text-[12px] font-medium ${OUTCOME_BADGE[entry.outcome]}`}>{OUTCOME_LABELS[entry.outcome]}</span>
            {entry.result_ft ? ` · finale ${entry.result_ft}` : ''}
            {entry.result_ht ? ` · primo tempo ${entry.result_ht}` : ''}
            {entry.profit !== null ? ` · ${money(entry.profit)}` : ''}
          </p>
          {toolBits.length ? <p className="mt-1 text-[13px] text-slate-500">Il tool, quando l&apos;hai scelta: {toolBits.join(' · ')}</p> : null}
          {entry.locked ? <p className="mt-1 text-[13px] text-slate-500">Partita iniziata: si possono cambiare solo note e minuti.</p> : null}
        </div>

        {!entry.locked && mine ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="text-[13px] font-medium text-slate-600">Quota</span>
              <input className={inputClass} value={quota} onChange={(e) => setQuota(e.target.value)} />
            </label>
            <label className="block">
              <span className="text-[13px] font-medium text-slate-600">Puntata (€)</span>
              <input className={inputClass} value={stake} onChange={(e) => setStake(e.target.value)} />
            </label>
          </div>
        ) : null}

        <div>
          <p className="text-sm font-semibold text-slate-800">Scheda pronostico</p>
          <div className="mt-2">
            <ChecklistEditor items={meta.checklist} value={checklist} disabled={entry.locked || !mine} onChange={setChecklist} />
          </div>
        </div>
        <label className="block">
          <span className="text-[13px] font-medium text-slate-600">Descrizione modalità di intervento</span>
          <textarea className={`${inputClass} min-h-[64px]`} value={analysisNote} disabled={entry.locked || !mine} onChange={(e) => setAnalysisNote(e.target.value)} />
        </label>
        <div className="grid gap-3 sm:grid-cols-[1fr_140px]">
          <label className="block">
            <span className="text-[13px] font-medium text-slate-600">Note</span>
            <textarea className={`${inputClass} min-h-[64px]`} value={notes} disabled={!mine} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <label className="block">
            <span className="text-[13px] font-medium text-slate-600">Minuti di analisi</span>
            <input className={inputClass} value={minutes} disabled={!mine} onChange={(e) => setMinutes(e.target.value.replace(/\D/g, ''))} />
          </label>
        </div>
        {mine ? (
          <div className="flex flex-wrap justify-between gap-2">
            {!entry.locked ? (
              <button type="button" className={`${btn} text-rose-700`} onClick={() => void remove()} disabled={busy}>
                Togli dal diario
              </button>
            ) : (
              <span />
            )}
            <button type="button" className={btnPrimary} onClick={() => void save()} disabled={busy}>
              {busy ? 'Salvo…' : 'Salva'}
            </button>
          </div>
        ) : null}
      </aside>
    </div>
  )
}

// --- progressioni ---------------------------------------------------------------------------------

const SETTING_FIELDS: Record<MethodKey, { key: string; label: string; kind: 'euro' | 'pct' | 'int' | 'num' | 'bool' }[]> = {
  cecchino: [
    { key: 'bankroll', label: 'Cassa', kind: 'euro' },
    { key: 'target_pct', label: 'Target profitto (desiderato)', kind: 'pct' },
    { key: 'strike', label: 'Strike (resa) sul range quote', kind: 'pct' },
    { key: 'bets', label: 'Numero di scommesse previste', kind: 'int' },
    { key: 'quota_min', label: 'Quota minima', kind: 'num' },
    { key: 'quota_max', label: 'Quota massima', kind: 'num' },
  ],
  ceccxino: [
    { key: 'bankroll', label: 'Cassa iniziale', kind: 'euro' },
    { key: 'base_pct', label: 'Puntata base (% cassa)', kind: 'pct' },
    { key: 'step_down', label: 'Dopo una vinta scendi di (€)', kind: 'num' },
    { key: 'stop_loss_pct', label: 'Stop loss', kind: 'pct' },
    { key: 'stop_win_pct', label: 'Stop win', kind: 'pct' },
    { key: 'decimals', label: 'Puntate con decimali', kind: 'bool' },
  ],
  meraviglia: [
    { key: 'bankroll', label: 'Cassa iniziale del mese', kind: 'euro' },
    { key: 'stake_pct', label: '% puntata', kind: 'pct' },
    { key: 'monthly_withdrawal', label: 'Prelievo mensile (€)', kind: 'euro' },
  ],
}

function CyclesTab({ meta, userId }: { meta: JournalMeta; userId: number | null }) {
  const [cycles, setCycles] = useState<Cycle[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const fetchCycles = useCallback(
    () =>
      listCycles({ user_id: userId }).then(
        (r) => {
          setCycles(r.cycles)
          setError(null)
        },
        (e: unknown) => setError(errorText(e)),
      ),
    [userId],
  )
  useEffect(() => {
    void fetchCycles()
  }, [fetchCycles])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-600">
          Ogni progressione segue un metodo (Cecchino, CeccXino, 8ª Meraviglia): il tool calcola la puntata della prossima giocata
          come nel file Excel, tu puoi sempre puntare un importo diverso.
        </p>
        {meta.can_write ? (
          <button type="button" className={btnPrimary} onClick={() => setCreating(true)} disabled={creating}>
            Nuova progressione
          </button>
        ) : null}
      </div>
      {creating ? (
        <NewCycleForm
          meta={meta}
          onCancel={() => setCreating(false)}
          onCreated={() => {
            setCreating(false)
            void fetchCycles()
          }}
        />
      ) : null}
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      {cycles === null ? (
        <p className="text-sm text-slate-500">Carico le progressioni…</p>
      ) : cycles.length === 0 ? (
        <div className={`${todayCard} ${todayCardPadding} text-sm text-slate-600`}>Nessuna progressione: creane una per avere la puntata calcolata dal metodo.</div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {cycles.map((c) => (
            <CycleCard key={c.id} cycle={c} canWrite={meta.can_write} onChanged={() => void fetchCycles()} />
          ))}
        </div>
      )}
    </div>
  )
}

function NewCycleForm({ meta, onCancel, onCreated }: { meta: JournalMeta; onCancel: () => void; onCreated: () => void }) {
  const [method, setMethod] = useState<MethodKey>('cecchino')
  const defaults = meta.methods.find((m) => m.key === method)?.defaults ?? {}
  const [values, setValues] = useState<Record<string, string | boolean>>({})
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  const shown = (key: string, kind: string): string | boolean => {
    if (key in values) return values[key]
    const d = defaults[key]
    if (kind === 'bool') return Boolean(d)
    if (kind === 'pct') return String(Math.round(Number(d) * 1000) / 10)
    return String(d ?? '')
  }

  const submit = async () => {
    const settings: Record<string, number | boolean> = {}
    for (const f of SETTING_FIELDS[method]) {
      const v = shown(f.key, f.kind)
      settings[f.key] = f.kind === 'bool' ? Boolean(v) : f.kind === 'pct' ? Number(String(v).replace(',', '.')) / 100 : Number(String(v).replace(',', '.'))
    }
    setBusy(true)
    try {
      await createCycle({ name, method, settings })
      toast.success('Progressione creata')
      onCreated()
    } catch (e) {
      toast.error(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`${todayCard} ${todayCardPadding} space-y-3`}>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="text-[13px] font-medium text-slate-600">Metodo</span>
          <select
            className={inputClass}
            value={method}
            onChange={(e) => {
              setMethod(e.target.value as MethodKey)
              setValues({})
            }}
          >
            {meta.methods.map((m) => (
              <option key={m.key} value={m.key}>
                {m.label} (max {m.max_bets} giocate)
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-[13px] font-medium text-slate-600">Nome</span>
          <input className={inputClass} placeholder="es. Novembre" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        {SETTING_FIELDS[method].map((f) =>
          f.kind === 'bool' ? (
            <label key={f.key} className="flex items-center gap-2 pt-6 text-sm text-slate-700">
              <input type="checkbox" checked={Boolean(shown(f.key, f.kind))} onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.checked }))} />
              {f.label}
            </label>
          ) : (
            <label key={f.key} className="block">
              <span className="text-[13px] font-medium text-slate-600">
                {f.label}
                {f.kind === 'pct' ? ' (%)' : f.kind === 'euro' ? ' (€)' : ''}
              </span>
              <input className={inputClass} inputMode="decimal" value={String(shown(f.key, f.kind))} onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))} />
            </label>
          ),
        )}
      </div>
      <div className="flex justify-end gap-2">
        <button type="button" className={btn} onClick={onCancel} disabled={busy}>
          Annulla
        </button>
        <button type="button" className={btnPrimary} onClick={() => void submit()} disabled={busy}>
          {busy ? 'Creo…' : 'Crea progressione'}
        </button>
      </div>
    </div>
  )
}

function CycleCard({ cycle, canWrite, onChanged }: { cycle: Cycle; canWrite: boolean; onChanged: () => void }) {
  const s = cycle.state
  const info = s.info as Record<string, number | number[] | undefined>
  const [quota, setQuota] = useState('')
  const [suggestion, setSuggestion] = useState<Cycle['suggestion'] | null>(null)
  const [entries, setEntries] = useState<JournalEntry[] | null>(null)
  const q = Number(quota.replace(',', '.'))

  useEffect(() => {
    if (!(q > 1)) return
    let alive = true
    const t = window.setTimeout(() => {
      getCycle(cycle.id, q).then((r) => alive && setSuggestion(r.cycle.suggestion ?? null), () => undefined)
    }, 300)
    return () => {
      alive = false
      window.clearTimeout(t)
    }
  }, [cycle.id, q])

  const toggle = async () => {
    try {
      await updateCycle(cycle.id, { status: cycle.status === 'aperta' ? 'chiusa' : 'aperta' })
      onChanged()
    } catch (e) {
      toast.error(errorText(e))
    }
  }

  const details: string[] = []
  if (cycle.method === 'cecchino') {
    details.push(`obiettivo ${formatEuro(Number(info.target_profit))}`, `devi vincere ancora ${info.wins_needed}`, `puoi perdere ${info.losses_allowed}`, `quota di riferimento ${info.ref_quota}`)
  } else if (cycle.method === 'ceccxino') {
    details.push(`puntata base ${formatEuro(Number(info.base_stake))}`, `stop loss a ${formatEuro(Number(info.stop_loss_at))}`, `stop win a ${formatEuro(Number(info.stop_win_at))}`)
  } else {
    details.push(`puntata ${(Number(info.stake_pct) * 100).toFixed(1)}% della cassa + recupero delle perse`)
  }

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-3`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className={todaySectionTitle}>{cycle.name}</h3>
          <p className={todaySectionSubtitle}>
            {cycle.method_label} · {s.status_label}
            {cycle.status === 'chiusa' ? ' · chiusa' : ''}
            {cycle.user_name ? ` · ${cycle.user_name}` : ''}
          </p>
        </div>
        {canWrite ? (
          <button type="button" className={btn} onClick={() => void toggle()}>
            {cycle.status === 'aperta' ? 'Chiudi' : 'Riapri'}
          </button>
        ) : null}
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Tile label="Cassa" value={formatEuro(s.bankroll)} sub={`partenza ${formatEuro(s.bankroll_start)}`} />
        <Tile label="Profitto" value={money(s.profit)} tone={s.profit > 0 ? 'pos' : s.profit < 0 ? 'neg' : undefined} />
        <Tile label="Vinte / perse" value={`${s.won} / ${s.lost}`} sub={`${s.bets_played} di ${s.max_bets} giocate`} />
        <Tile label="In corso" value={String(cycle.pending)} sub={cycle.pending ? `${formatEuro(cycle.pending_stake)} in gioco` : undefined} />
      </div>
      <p className="text-[13px] text-slate-600">{details.join(' · ')}</p>
      {cycle.status === 'aperta' ? (
        <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-slate-50/70 p-3">
          <label className="block">
            <span className="text-[13px] font-medium text-slate-600">Prossima giocata a quota</span>
            <input className="mt-1 w-28 rounded-lg border border-slate-300 px-3 py-2 text-sm" inputMode="decimal" value={quota} onChange={(e) => setQuota(e.target.value)} placeholder="es. 1.80" />
          </label>
          <p className="pb-2 text-sm text-slate-800">
            {q > 1 && suggestion ? (
              suggestion.stake ? (
                <>
                  Punta <strong>{formatEuro(suggestion.stake)}</strong>
                  {suggestion.warning ? <span className="block text-[13px] text-amber-700">{suggestion.warning}</span> : null}
                  {suggestion.note ? <span className="block text-[13px] text-slate-500">{suggestion.note}</span> : null}
                </>
              ) : (
                suggestion.reason
              )
            ) : (
              <span className="text-slate-500">Scrivi la quota per vedere la puntata del metodo</span>
            )}
          </p>
        </div>
      ) : null}
      <button
        type="button"
        className="text-[13px] font-semibold text-slate-700"
        onClick={() => (entries ? setEntries(null) : getCycle(cycle.id).then((r) => setEntries(r.entries), () => setEntries([])))}
      >
        {entries ? '▾ Nascondi giocate' : `▸ Giocate (${cycle.entries_total})`}
      </button>
      {entries ? (
        <ul className="divide-y divide-slate-100 text-[13px] text-slate-700">
          {entries.map((e, i) => (
            <li key={e.id} className="flex flex-wrap justify-between gap-2 py-1.5">
              <span>
                {i + 1}. {e.home_team} – {e.away_team} · {e.market_label} @ {e.quota}
              </span>
              <span className="tabular-nums">
                {e.stake ? formatEuro(e.stake) : '—'} · {OUTCOME_LABELS[e.outcome]} {e.profit !== null ? `· ${money(e.profit)}` : ''}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}

function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: 'pos' | 'neg' }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2">
      <p className="text-[12px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`text-base font-semibold tabular-nums ${tone === 'pos' ? 'text-emerald-700' : tone === 'neg' ? 'text-rose-700' : 'text-slate-900'}`}>{value}</p>
      {sub ? <p className="text-[12px] text-slate-500">{sub}</p> : null}
    </div>
  )
}

// --- report ---------------------------------------------------------------------------------------

function ReportTab({ filters }: { filters: Filters }) {
  const [report, setReport] = useState<JournalReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    getJournalReport(filters).then(
      (r) => alive && setReport(r),
      (e: unknown) => alive && setError(errorText(e)),
    )
    return () => {
      alive = false
    }
  }, [filters])

  if (error) return <p className="text-sm text-rose-700">{error}</p>
  if (!report) return <p className="text-sm text-slate-500">Calcolo i report…</p>
  const t = report.total
  if (!t.entries) return <div className={`${todayCard} ${todayCardPadding} text-sm text-slate-600`}>Nessuna giocata nel periodo.</div>

  const months = [...new Set(report.month_groups.map((r) => r.month))].sort().reverse()
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-8">
        <Tile label="Giocate" value={String(t.entries)} sub={`${t.settled} chiuse`} />
        <Tile label="Resa" value={pct(t.win_pct)} sub={`pari a ${pct(t.breakeven_pct)}`} />
        <Tile label="Quota media" value={t.avg_quota ? String(t.avg_quota) : '—'} />
        <Tile label="Profitto" value={money(t.profit)} tone={t.profit > 0 ? 'pos' : t.profit < 0 ? 'neg' : undefined} />
        <Tile label="ROI" value={pct(t.roi_pct)} sub={`a 1 unità ${pct(t.roi_units_pct)}`} />
        <Tile label="Puntato" value={formatEuro(t.staked)} />
        <Tile label="Ore di analisi" value={String(t.hours)} />
        <Tile label="Guadagno orario" value={t.profit_per_hour !== null ? money(t.profit_per_hour) : '—'} />
      </div>

      <ReportTable
        title="Report segni"
        subtitle="Come il foglio REPORT SEGNI: analisi prese e sbagliate per tipo di giocata, mese per mese."
        rows={months.flatMap((m) => report.month_groups.filter((r) => r.month === m).map((r) => ({ key: `${m}-${r.group}`, first: monthLabel(m), second: r.group, row: r })))}
        firstLabel="Mese"
        secondLabel="Tipo"
      />
      <ReportTable
        title="Gestione cassa per mese"
        subtitle="Come il foglio GESTIONE CASSA: vinte, perse, tempo, guadagno orario e rendimento."
        rows={report.months.map((r) => ({ key: r.month, first: monthLabel(r.month), row: r }))}
        firstLabel="Mese"
        showMoney
      />
      <ReportTable
        title="Analista contro tool"
        subtitle="Resa reale delle giocate scelte contro la probabilità che il tool dava a quelle stesse giocate, per pagina di origine."
        rows={report.sources.map((r) => ({ key: r.source, first: r.label, row: r }))}
        firstLabel="Origine"
        showTool
      />
      <ReportTable
        title="Per pronostico"
        rows={report.markets.map((r) => ({ key: r.market_key, first: r.label, second: r.group ?? '', row: r }))}
        firstLabel="Pronostico"
        secondLabel="Tipo"
        showMoney
      />
      <ReportTable
        title="Scheda pronostico"
        subtitle="Per ogni voce: come sono andate le giocate quando l'hai segnata favorevole, neutra o contraria."
        rows={report.checklist.map((r) => ({ key: `${r.key}-${r.value}`, first: r.label, second: CHECKLIST_LABELS[r.value], row: r }))}
        firstLabel="Voce"
        secondLabel="Valutazione"
      />
    </div>
  )
}

function monthLabel(m: string): string {
  const [y, mm] = m.split('-').map(Number)
  return new Date(y, mm - 1, 1).toLocaleDateString('it-IT', { month: 'long', year: 'numeric' })
}

function ReportTable({
  title,
  subtitle,
  rows,
  firstLabel,
  secondLabel,
  showMoney,
  showTool,
}: {
  title: string
  subtitle?: string
  rows: { key: string; first: string; second?: string; row: ReportRow }[]
  firstLabel: string
  secondLabel?: string
  showMoney?: boolean
  showTool?: boolean
}) {
  if (!rows.length) return null
  return (
    <section className={`${todayCard} overflow-hidden`}>
      <div className="px-4 pt-4">
        <h2 className={todaySectionTitle}>{title}</h2>
        {subtitle ? <p className={todaySectionSubtitle}>{subtitle}</p> : null}
      </div>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="bg-slate-50 text-[12px] uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 text-left font-medium">{firstLabel}</th>
              {secondLabel ? <th className="px-3 py-2 text-left font-medium">{secondLabel}</th> : null}
              <th className="px-3 py-2 text-right font-medium">Prese</th>
              <th className="px-3 py-2 text-right font-medium">Sbagliate</th>
              <th className="px-3 py-2 text-right font-medium">Resa</th>
              <th className="px-3 py-2 text-right font-medium">Quota media</th>
              {showTool ? <th className="px-3 py-2 text-right font-medium">Prob. tool</th> : null}
              <th className="px-3 py-2 text-right font-medium">A 1 unità</th>
              {showMoney ? (
                <>
                  <th className="px-3 py-2 text-right font-medium">Profitto</th>
                  <th className="px-3 py-2 text-right font-medium">ROI</th>
                  <th className="px-3 py-2 text-right font-medium">Ore</th>
                  <th className="px-4 py-2 text-right font-medium">€/ora</th>
                </>
              ) : null}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map(({ key, first, second, row }) => (
              <tr key={key}>
                <td className="px-4 py-2 capitalize text-slate-800">{first}</td>
                {secondLabel ? <td className="px-3 py-2 text-slate-600">{second}</td> : null}
                <td className="px-3 py-2 text-right tabular-nums">{row.won}</td>
                <td className="px-3 py-2 text-right tabular-nums">{row.lost}</td>
                <td className="px-3 py-2 text-right tabular-nums font-semibold">{pct(row.win_pct)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{row.avg_quota ?? '—'}</td>
                {showTool ? <td className="px-3 py-2 text-right tabular-nums">{pct(row.tool_prob_pct)}</td> : null}
                <td className={`px-3 py-2 text-right tabular-nums ${row.profit_units > 0 ? 'text-emerald-700' : row.profit_units < 0 ? 'text-rose-700' : ''}`}>
                  {row.settled ? `${row.profit_units > 0 ? '+' : ''}${row.profit_units} u` : '—'}
                </td>
                {showMoney ? (
                  <>
                    <td className="px-3 py-2 text-right tabular-nums">{row.staked ? money(row.profit) : '—'}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{pct(row.roi_pct)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{row.hours}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{row.profit_per_hour !== null ? money(row.profit_per_hour) : '—'}</td>
                  </>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
