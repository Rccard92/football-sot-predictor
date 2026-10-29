import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { useOptionalAuth } from '../../contexts/AuthContext'
import { AdminHttpError } from '../../lib/api'
import {
  createEntry,
  formatEuro,
  getCycle,
  getFixtureInfo,
  getJournalMeta,
  listCycles,
  type Checklist,
  type Cycle,
  type FixtureInfo,
  type JournalMeta,
  type JournalSource,
  type ToolSnapshot,
} from '../../lib/analystJournalApi'
import { ChecklistEditor } from './ChecklistEditor'

const JOURNAL_TAB = 'diario-analisi'
const inputClass =
  'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none'

type Props = {
  todayFixtureId: number
  source: JournalSource
  marketKey?: string | null
  quota?: number | null
  tool?: ToolSnapshot
  className?: string
  compact?: boolean
}

/** "Aggiungi al diario": visibile solo a chi ha la scheda Diario analisi e un account. */
export function AddToJournalButton({ todayFixtureId, source, marketKey, quota, tool, className, compact }: Props) {
  const auth = useOptionalAuth()
  const [open, setOpen] = useState(false)
  if (!auth?.me?.user || !auth.canSee(JOURNAL_TAB)) return null
  return (
    <>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          setOpen(true)
        }}
        data-testid="add-to-journal"
        className={
          className ??
          `inline-flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 font-semibold text-indigo-800 hover:bg-indigo-100 ${
            compact ? 'px-2.5 py-1.5 text-[13px]' : 'px-3 py-2 text-sm'
          }`
        }
      >
        + Aggiungi al diario
      </button>
      {open ? (
        <AddToJournalDialog
          todayFixtureId={todayFixtureId}
          source={source}
          marketKey={marketKey ?? null}
          quota={quota ?? null}
          tool={tool}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  )
}

function AddToJournalDialog({
  todayFixtureId,
  source,
  marketKey,
  quota,
  tool,
  onClose,
}: Omit<Props, 'className' | 'compact'> & { marketKey: string | null; quota: number | null; onClose: () => void }) {
  const openedAt = useRef(0)
  const [meta, setMeta] = useState<JournalMeta | null>(null)
  const [info, setInfo] = useState<FixtureInfo | null>(null)
  const [cycles, setCycles] = useState<Cycle[]>([])
  const [error, setError] = useState<string | null>(null)
  const [market, setMarket] = useState(marketKey ?? '')
  const [quotaText, setQuotaText] = useState(quota ? String(quota) : '')
  const [cycleId, setCycleId] = useState<number | null>(null)
  const [stakeText, setStakeText] = useState('')
  const [suggestion, setSuggestion] = useState<Cycle['suggestion'] | null>(null)
  const [checklist, setChecklist] = useState<Checklist>({})
  const [analysisNote, setAnalysisNote] = useState('')
  const [notes, setNotes] = useState('')
  const [minutesText, setMinutesText] = useState('')
  const [showChecklist, setShowChecklist] = useState(true)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    openedAt.current = Date.now()
    Promise.all([getJournalMeta(), getFixtureInfo(todayFixtureId, marketKey ?? undefined), listCycles({ status: 'aperta' })]).then(
      ([m, f, c]) => {
        setMeta(m)
        setInfo(f)
        setCycles(c.cycles)
        if (c.cycles.length === 1) setCycleId(c.cycles[0].id)
      },
      (e: unknown) => setError(e instanceof AdminHttpError ? e.message : 'Dati della partita non disponibili'),
    )
  }, [todayFixtureId, marketKey])

  const marketRow = useMemo(() => info?.markets.find((m) => m.key === market) ?? null, [info, market])
  const quotaValue = Number(quotaText.replace(',', '.'))

  // la quota del book di Today se la pagina di origine non l'ha passata
  const onMarketChange = (key: string) => {
    setMarket(key)
    const row = info?.markets.find((m) => m.key === key)
    if (row?.quota_book && (key !== marketKey || !quota)) setQuotaText(String(row.quota_book))
  }

  useEffect(() => {
    if (!cycleId || !(quotaValue > 1)) return
    let alive = true
    const t = window.setTimeout(() => {
      getCycle(cycleId, quotaValue).then(
        (r) => alive && setSuggestion(r.cycle.suggestion ?? null),
        () => alive && setSuggestion(null),
      )
    }, 300)
    return () => {
      alive = false
      window.clearTimeout(t)
    }
  }, [cycleId, quotaValue])

  const save = async () => {
    if (!market) return setError('Scegli il pronostico')
    if (!(quotaValue > 1)) return setError('Inserisci una quota valida')
    const stake = stakeText ? Number(stakeText.replace(',', '.')) : null
    if (stake !== null && !(stake > 0)) return setError('Puntata non valida')
    const minutes = minutesText ? Number(minutesText) : Math.max(1, Math.round((Date.now() - openedAt.current) / 60000))
    setBusy(true)
    setError(null)
    try {
      await createEntry({
        today_fixture_id: todayFixtureId,
        market_key: market,
        quota: quotaValue,
        source,
        stake,
        stake_suggested: cycleId && suggestion?.stake ? suggestion.stake : null,
        cycle_id: cycleId,
        tool: { ...tool, quota_tool: quota ?? undefined },
        checklist,
        analysis_note: analysisNote,
        notes,
        minutes_spent: Number.isFinite(minutes) ? minutes : null,
      })
      toast.success('Aggiunta al diario')
      onClose()
    } catch (e) {
      setError(e instanceof AdminHttpError ? e.message : 'Salvataggio non riuscito')
    } finally {
      setBusy(false)
    }
  }

  const fx = info?.fixture
  const already = info?.my_entries ?? []
  const groups = useMemo(() => {
    const out = new Map<string, NonNullable<FixtureInfo['markets']>>()
    for (const m of info?.markets ?? []) out.set(m.group, [...(out.get(m.group) ?? []), m])
    return [...out.entries()]
  }, [info])

  return (
    <div
      className="fixed inset-0 z-[65] flex items-start justify-center overflow-y-auto bg-slate-900/50 p-3 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Aggiungi al diario"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="w-full max-w-2xl space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Aggiungi al diario</h2>
            {fx ? (
              <p className="text-sm text-slate-600">
                {fx.home_team} – {fx.away_team} · {fx.league_name}
                {fx.kickoff
                  ? ` · ${new Date(fx.kickoff).toLocaleString('it-IT', { timeZone: 'Europe/Rome', dateStyle: 'short', timeStyle: 'short' })}`
                  : ''}
              </p>
            ) : (
              <p className="text-sm text-slate-500">Carico la partita…</p>
            )}
          </div>
          <button type="button" onClick={onClose} className="rounded-lg border border-slate-200 px-2.5 py-1 text-sm text-slate-600 hover:bg-slate-50">
            Chiudi
          </button>
        </div>

        {fx?.started ? <p className="text-sm text-rose-700">La partita è già iniziata: non si può più aggiungere.</p> : null}
        {already.length ? (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
            Già nel tuo diario per questa partita: {already.map((e) => `${e.market_label} @ ${e.quota}`).join(', ')}
          </p>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="text-[13px] font-medium text-slate-600">Pronostico</span>
            <select className={inputClass} value={market} onChange={(e) => onMarketChange(e.target.value)}>
              <option value="">Scegli…</option>
              {groups.map(([group, items]) => (
                <optgroup key={group} label={group}>
                  {items.map((m) => (
                    <option key={m.key} value={m.key}>
                      {m.label}
                      {m.quota_book ? ` · ${m.quota_book}` : ''}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-[13px] font-medium text-slate-600">Quota presa</span>
            <input className={inputClass} inputMode="decimal" value={quotaText} onChange={(e) => setQuotaText(e.target.value)} />
            {marketRow?.prob_cecchino ? (
              <span className="mt-1 block text-[13px] text-slate-500">
                Probabilità del tool {(marketRow.prob_cecchino * 100).toFixed(0)}%
                {tool?.probability ? ` · in pagina ${Math.round(tool.probability > 1 ? tool.probability : tool.probability * 100)}%` : ''}
              </span>
            ) : null}
          </label>
          <label className="block">
            <span className="text-[13px] font-medium text-slate-600">Progressione (metodo di cassa)</span>
            <select className={inputClass} value={cycleId ?? ''} onChange={(e) => setCycleId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">Nessuna</option>
              {cycles.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} · {c.method_label} · cassa {formatEuro(c.state.bankroll)}
                </option>
              ))}
            </select>
            {!cycles.length ? <span className="mt-1 block text-[13px] text-slate-500">Nessuna progressione aperta: la crei nel Diario.</span> : null}
          </label>
          <label className="block">
            <span className="text-[13px] font-medium text-slate-600">Puntata (€)</span>
            <input className={inputClass} inputMode="decimal" value={stakeText} onChange={(e) => setStakeText(e.target.value)} />
            {cycleId && suggestion ? (
              <span className="mt-1 block text-[13px] text-slate-600">
                {suggestion.stake ? (
                  <>
                    Il metodo dice <strong>{formatEuro(suggestion.stake)}</strong>{' '}
                    <button type="button" className="font-semibold text-indigo-700 underline" onClick={() => setStakeText(String(suggestion.stake))}>
                      usa
                    </button>
                  </>
                ) : (
                  suggestion.reason
                )}
                {suggestion.warning ? <span className="block text-amber-700">{suggestion.warning}</span> : null}
                {suggestion.note ? <span className="block text-slate-500">{suggestion.note}</span> : null}
              </span>
            ) : null}
          </label>
        </div>

        <div>
          <button type="button" className="text-sm font-semibold text-slate-800" onClick={() => setShowChecklist((v) => !v)}>
            {showChecklist ? '▾' : '▸'} Scheda pronostico
          </button>
          {showChecklist && meta ? (
            <div className="mt-2">
              <ChecklistEditor items={meta.checklist} value={checklist} hints={info?.hints} onChange={setChecklist} />
            </div>
          ) : null}
        </div>

        <label className="block">
          <span className="text-[13px] font-medium text-slate-600">Descrizione modalità di intervento</span>
          <textarea className={`${inputClass} min-h-[64px]`} value={analysisNote} onChange={(e) => setAnalysisNote(e.target.value)} />
        </label>
        <div className="grid gap-3 sm:grid-cols-[1fr_140px]">
          <label className="block">
            <span className="text-[13px] font-medium text-slate-600">Note</span>
            <input className={inputClass} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <label className="block">
            <span className="text-[13px] font-medium text-slate-600">Minuti di analisi</span>
            <input className={inputClass} inputMode="numeric" placeholder="automatico" value={minutesText} onChange={(e) => setMinutesText(e.target.value.replace(/\D/g, ''))} />
          </label>
        </div>

        {error ? <p className="text-sm text-rose-700">{error}</p> : null}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50" disabled={busy}>
            Annulla
          </button>
          <button
            type="button"
            onClick={() => void save()}
            disabled={busy || !info || fx?.started}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {busy ? 'Salvo…' : 'Salva nel diario'}
          </button>
        </div>
      </div>
    </div>
  )
}
