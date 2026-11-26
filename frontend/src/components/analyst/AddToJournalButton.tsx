import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { useOptionalAuth } from '../../contexts/AuthContext'
import { AdminHttpError } from '../../lib/api'
import {
  checkPlay,
  createEntry,
  formatEuro,
  getCycle,
  getFixtureInfo,
  getJournalMeta,
  listCycles,
  savePaperPlay,
  uploadEntryPhoto,
  type AnswerKey,
  type AnswerValue,
  type Answers,
  type Cycle,
  type FixtureInfo,
  type JournalMeta,
  type JournalSource,
  type PlayCheck,
  type ToolSnapshot,
} from '../../lib/analystJournalApi'
import { C, hhmm, q2, signLabel } from './diarioFormat'
import { OddsAge } from './OddsAge'

const JOURNAL_TAB = 'diario-analisi'
/** bookmaker piu' usati (si puo' scrivere anche un altro) */
const BOOKMAKERS = ['Bet365', 'Sisal', 'Snai', 'Eurobet', 'Goldbet', 'Lottomatica', 'Planetwin365', 'Betfair', 'William Hill', 'Unibet', 'Pinnacle']
const LAST_BOOK_KEY = 'diario-ultimo-bookmaker'
const ANSWERS: { key: AnswerKey; label: string; none: string }[] = [
  { key: 'assenze', label: 'Assenze pesanti confermate', none: 'non verificato' },
  { key: 'allenatore', label: 'Cambio allenatore o crisi', none: 'non verificato' },
  { key: 'motivazione', label: 'Motivazione particolare', none: 'non verificata' },
]
const RISK_MIN = 15
const EXCEPTION_MIN = 15
const MAX_PHOTOS = 5
const MAX_PHOTO_BYTES = 5 * 1024 * 1024
const CAPTION_MIN = 5
const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp']

function lastBookmaker(): string {
  try {
    return window.localStorage.getItem(LAST_BOOK_KEY) ?? ''
  } catch {
    return ''
  }
}

function rememberBookmaker(name: string) {
  try {
    window.localStorage.setItem(LAST_BOOK_KEY, name)
  } catch {
    // niente: e' solo una comodita'
  }
}
const inputClass = 'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none'

type Props = {
  todayFixtureId: number
  source: JournalSource
  marketKey?: string | null
  quota?: number | null
  tool?: ToolSnapshot
  className?: string
  compact?: boolean
}

/** "Aggiungi al diario": visibile a chi ha la scheda Diario analisi (analisti e amministratori, anche con l'accesso di emergenza). */
export function AddToJournalButton({ todayFixtureId, source, marketKey, quota, tool, className, compact }: Props) {
  const auth = useOptionalAuth()
  const [open, setOpen] = useState(false)
  if (!auth?.me || !auth.canSee(JOURNAL_TAB)) return null
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
      {open ? <JournalDialog todayFixtureId={todayFixtureId} source={source} marketKey={marketKey ?? null} quota={quota ?? null} tool={tool} onClose={() => setOpen(false)} /> : null}
    </>
  )
}

type StagedPhoto = { file: File; caption: string; preview: string }

/** «Prima di salvare» (capitolato del 24/11/2026, modifiche 4, 8 e 18): segno, quota presa, bookmaker, progressione,
 *  puntata; tre domande obbligatorie; «Cosa potrebbe smentire questa giocata?»; foto facoltative. Un segno bloccato
 *  (o fuori fascia) si salva solo come eccezione, con il motivo scritto. */
export function JournalDialog({
  todayFixtureId,
  source,
  marketKey,
  quota,
  tool,
  onClose,
}: {
  todayFixtureId: number
  source: JournalSource
  marketKey: string | null
  quota?: number | null
  tool?: ToolSnapshot
  onClose: () => void
}) {
  const openedAt = useRef(0)
  const papered = useRef<Set<string>>(new Set())
  const [meta, setMeta] = useState<JournalMeta | null>(null)
  const [info, setInfo] = useState<FixtureInfo | null>(null)
  const [cycles, setCycles] = useState<Cycle[]>([])
  const [error, setError] = useState<string | null>(null)
  const [market, setMarket] = useState(marketKey ?? '')
  // quota presa (09/11/2026): la scrive l'analista, non si riempie con la quota del tool
  const [quotaText, setQuotaText] = useState('')
  const [bookmaker, setBookmaker] = useState(lastBookmaker)
  const [cycleId, setCycleId] = useState<number | null>(null)
  const [stakeText, setStakeText] = useState('')
  const [suggestion, setSuggestion] = useState<Cycle['suggestion'] | null>(null)
  const [answers, setAnswers] = useState<Answers>({})
  const [risk, setRisk] = useState('')
  const [exceptionReason, setExceptionReason] = useState('')
  const [photos, setPhotos] = useState<StagedPhoto[]>([])
  const [photoError, setPhotoError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [check, setCheck] = useState<PlayCheck | null>(null)

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

  // le anteprime si liberano solo alla chiusura (prima resterebbero vuote quelle ancora mostrate)
  const previews = useRef<string[]>([])
  useEffect(() => {
    previews.current = photos.map((p) => p.preview)
  }, [photos])
  useEffect(() => () => previews.current.forEach((u) => URL.revokeObjectURL(u)), [])

  const marketRow = useMemo(() => info?.markets.find((m) => m.key === market) ?? null, [info, market])
  const quotaValue = Number(quotaText.replace(',', '.'))

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

  // stato del segno su Q, quota presa diversa dal tool, avvisi della testata
  useEffect(() => {
    if (!market) return
    let alive = true
    const t = window.setTimeout(() => {
      checkPlay({ today_fixture_id: todayFixtureId, market_key: market, quota: quotaValue > 1 ? quotaValue : null }).then(
        (r) => alive && setCheck(r),
        () => alive && setCheck(null),
      )
    }, 300)
    return () => {
      alive = false
      window.clearTimeout(t)
    }
  }, [todayFixtureId, market, quotaValue])

  const shown = market ? check : null
  const sign = shown?.sign ?? null
  const exception = sign?.state === 'blocked' || sign?.state === 'out'

  // un segno bloccato scelto si salva sulla carta (modifica 11): se poi diventa un'eccezione resta collegato
  useEffect(() => {
    if (sign?.state !== 'blocked' || !market || papered.current.has(market)) return
    papered.current.add(market)
    void savePaperPlay(todayFixtureId, market).catch(() => undefined)
  }, [sign?.state, market, todayFixtureId])

  const addPhotos = (files: FileList | null) => {
    setPhotoError(null)
    if (!files) return
    const next = [...photos]
    for (const f of Array.from(files)) {
      if (next.length >= MAX_PHOTOS) {
        setPhotoError(`Al massimo ${MAX_PHOTOS} foto per giocata`)
        break
      }
      if (!PHOTO_TYPES.includes(f.type)) {
        setPhotoError('Formato non ammesso: solo JPG, PNG o WEBP')
        continue
      }
      if (f.size > MAX_PHOTO_BYTES) {
        setPhotoError('Foto troppo grande: massimo 5 MB')
        continue
      }
      next.push({ file: f, caption: '', preview: URL.createObjectURL(f) })
    }
    setPhotos(next)
  }

  const save = async () => {
    if (!market) return setError('Scegli il pronostico')
    if (!(quotaValue > 1)) return setError('Scrivi la quota presa')
    if (!bookmaker.trim()) return setError('Scrivi il bookmaker della quota presa')
    const stake = stakeText ? Number(stakeText.replace(',', '.')) : null
    if (stake !== null && !(stake > 0)) return setError('Puntata non valida')
    if (ANSWERS.some((a) => !answers[a.key])) return setError('Rispondi alle tre domande (sì, no o non verificato)')
    if (risk.trim().length < RISK_MIN) return setError(`Scrivi cosa potrebbe smentire questa giocata (almeno ${RISK_MIN} caratteri)`)
    if (exception && exceptionReason.trim().length < EXCEPTION_MIN) return setError(`Scrivi perché la vuoi registrare lo stesso (almeno ${EXCEPTION_MIN} caratteri)`)
    if (photos.some((p) => p.caption.trim().length < CAPTION_MIN)) return setError(`Ogni foto ha bisogno della didascalia (almeno ${CAPTION_MIN} caratteri)`)
    const minutes = Math.max(1, Math.round((Date.now() - openedAt.current) / 60000))
    setBusy(true)
    setError(null)
    try {
      const { entry } = await createEntry({
        today_fixture_id: todayFixtureId,
        market_key: market,
        quota: quotaValue,
        bookmaker: bookmaker.trim(),
        source,
        stake,
        stake_suggested: cycleId && suggestion?.stake ? suggestion.stake : null,
        cycle_id: cycleId,
        tool: { ...tool, quota_tool: quota ?? undefined },
        answers,
        risk_note: risk.trim(),
        exception,
        exception_reason: exception ? exceptionReason.trim() : undefined,
        minutes_spent: minutes,
      })
      rememberBookmaker(bookmaker.trim())
      let failed = 0
      for (const p of photos) {
        try {
          await uploadEntryPhoto(entry.id, p.file, p.caption.trim())
        } catch {
          failed += 1
        }
      }
      if (failed) toast.error(`Giocata salvata, ma ${failed} foto non sono state caricate: riprova dalla giocata`)
      toast.success(exception ? 'Eccezione registrata' : 'Aggiunta al diario')
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
  const values = meta?.answer_values ?? { si: 'sì', no: 'no', nv: 'non verificato' }
  const motivationAlerts = (shown?.alerts ?? []).filter((a) => a.code !== 'ravvicinata')

  return (
    <div
      className="fixed inset-0 z-[65] flex items-start justify-center overflow-y-auto bg-slate-900/50 p-3 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Prima di salvare"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="w-full max-w-2xl space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900">{exception ? 'Registra eccezione' : 'Prima di salvare'}</h2>
            {fx ? (
              <p className="text-sm text-slate-600">
                {fx.home_team} – {fx.away_team} · {fx.league_name}
                {fx.kickoff ? ` · ${new Date(fx.kickoff).toLocaleString('it-IT', { timeZone: 'Europe/Rome', dateStyle: 'short', timeStyle: 'short' })}` : ''}
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
            <span className="text-[13px] font-medium text-slate-600">Segno</span>
            <select className={inputClass} value={market} onChange={(e) => setMarket(e.target.value)}>
              <option value="">Scegli…</option>
              {groups.map(([group, items]) => (
                <optgroup key={group} label={group}>
                  {items.map((m) => (
                    <option key={m.key} value={m.key}>
                      {signLabel(m.label)}
                      {m.quota_book ? ` · ${q2(m.quota_book)}` : ''}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-2">
            <label className="block">
              <span className="text-[13px] font-medium text-slate-600">Quota presa *</span>
              <input className={inputClass} inputMode="decimal" placeholder="es. 1,85" value={quotaText} onChange={(e) => setQuotaText(e.target.value)} />
            </label>
            <label className="block">
              <span className="text-[13px] font-medium text-slate-600">Bookmaker *</span>
              <input className={inputClass} list="diario-bookmakers" placeholder="es. Bet365" value={bookmaker} onChange={(e) => setBookmaker(e.target.value)} maxLength={40} />
              <datalist id="diario-bookmakers">
                {BOOKMAKERS.map((b) => (
                  <option key={b} value={b} />
                ))}
              </datalist>
            </label>
            <div className="col-span-2">
              {sign?.q ? (
                <span className="block text-[13px] text-slate-500">
                  Quota del tool <b className="tabular-nums text-slate-700">{q2(sign.q)}</b> ({sign.q_source === 't75' ? 'seconda lettura' : 'mattino'} delle {hhmm(sign.q_at)}, salvata a parte)
                </span>
              ) : marketRow?.quota_book || quota ? (
                <span className="block text-[13px] text-slate-500">
                  Quota del tool <b className="tabular-nums text-slate-700">{q2(marketRow?.quota_book ?? quota)}</b> (salvata a parte per il confronto)
                </span>
              ) : null}
              <OddsAge iso={fx?.odds_checked_at} />
              {shown?.quota_gap ? (
                <span className="mt-1 block rounded-md px-2 py-1 text-[13px]" style={{ color: C.warn.text, background: C.warn.bg }} role="status">
                  {shown.quota_gap.text}
                </span>
              ) : null}
            </div>
          </div>
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

        {shown ? <SignStateBox check={shown} reason={exceptionReason} onReason={setExceptionReason} /> : null}

        <section className="space-y-2 rounded-xl border border-slate-200 p-3">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-slate-500">Prima di salvare</p>
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            {ANSWERS.map((a) => (
              <div key={a.key}>
                <p className="text-[13px] text-slate-700">{a.label}</p>
                <div className="mt-0.5 inline-flex overflow-hidden rounded-lg border border-slate-200" role="group" aria-label={a.label}>
                  {(['si', 'no', 'nv'] as AnswerValue[]).map((v) => (
                    <button
                      key={v}
                      type="button"
                      aria-pressed={answers[a.key] === v}
                      onClick={() => setAnswers((x) => ({ ...x, [a.key]: v }))}
                      className={`px-2.5 py-1 text-[13px] font-medium ${answers[a.key] === v ? 'bg-[#2457B3] text-white' : 'bg-white text-slate-700 hover:bg-slate-50'}`}
                    >
                      {v === 'nv' ? a.none : values[v]}
                    </button>
                  ))}
                </div>
                {a.key === 'motivazione' && motivationAlerts.length ? (
                  <div className="mt-1 space-y-0.5">
                    {motivationAlerts.map((x) => (
                      <p key={x.code} className="rounded-md px-2 py-0.5 text-[12px]" style={{ color: C.warn.text, background: C.warn.bg }}>
                        {x.text}
                      </p>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
          <label className="block">
            <span className="text-[13px] font-semibold text-slate-800">Cosa potrebbe smentire questa giocata?</span>{' '}
            <span className="text-[12px] text-slate-400">(obbligatorio, una frase)</span>
            <textarea
              className={`${inputClass} min-h-[64px]`}
              placeholder="es. «Il Catanzaro ha giocato 4 gare su 5 contro avversarie più forti: il pari può essere meno probabile di quanto dice la forma»"
              value={risk}
              onChange={(e) => setRisk(e.target.value)}
            />
          </label>
          <div>
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-[13px] font-medium text-slate-700 hover:bg-slate-50">
              Allega foto (facoltativo)
              <input type="file" accept="image/jpeg,image/png,image/webp" multiple className="sr-only" onChange={(e) => addPhotos(e.target.files)} />
            </label>
            <p className="mt-1 text-[12px] text-slate-400">Niente foto con nomi, saldo o dati del conto: ritaglia prima di caricare.</p>
            {photoError ? <p className="mt-1 text-[13px] text-rose-700">{photoError}</p> : null}
            {photos.length ? (
              <div className="mt-2 space-y-2">
                {photos.map((p, i) => (
                  <div key={p.preview} className="flex items-center gap-2">
                    <img src={p.preview} alt="" className="h-12 w-12 rounded object-cover" />
                    <input
                      className="flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                      placeholder="didascalia (es. formazione ufficiale)"
                      value={p.caption}
                      maxLength={200}
                      onChange={(e) => setPhotos((xs) => xs.map((x, j) => (j === i ? { ...x, caption: e.target.value } : x)))}
                    />
                    <button type="button" className="text-[13px] text-slate-500 underline" onClick={() => {
                        URL.revokeObjectURL(p.preview)
                        setPhotos((xs) => xs.filter((_, j) => j !== i))
                      }}
                    >
                      togli
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </section>

        {error ? <p className="text-sm text-rose-700">{error}</p> : null}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50" disabled={busy}>
            Annulla
          </button>
          <button
            type="button"
            onClick={() => void save()}
            disabled={busy || !info || fx?.started}
            className={`rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-60 ${exception ? 'bg-[#B03030] hover:bg-[#962828]' : 'bg-slate-900 hover:bg-slate-800'}`}
          >
            {busy ? 'Salvo…' : exception ? 'Registra eccezione' : 'Salva nel diario'}
          </button>
        </div>
      </div>
    </div>
  )
}

/** Stato del segno scelto (modifiche 3 e 4): giocabile, da verificare, oppure fuori regola con il motivo da scrivere. */
function SignStateBox({ check, reason, onReason }: { check: PlayCheck; reason: string; onReason: (v: string) => void }) {
  const s = check.sign
  const extra = (
    <>
      {check.goal_alert && check.goal_form ? (
        <p className="rounded-xl px-3 py-2 text-[13px]" style={{ color: C.warn.text, background: C.warn.bg }} role="status">
          Avviso Under: {check.goal_form.goals} gol in {check.goal_form.games} gare ({String(check.goal_form.avg).replace('.', ',')} a partita). È solo un avviso.
        </p>
      ) : null}
      {check.editable === false && check.not_editable_reason ? (
        <p className="rounded-xl bg-amber-50 px-3 py-2 text-[13px] text-amber-800">{check.not_editable_reason}: nella Tabella del Diario questa partita non si aggiunge.</p>
      ) : null}
    </>
  )
  if (!s) return extra
  if (s.state === 'blocked' || s.state === 'out') {
    return (
      <div className="space-y-2">
        <div className="space-y-2 rounded-xl border-2 border-[#B03030] p-3" role="alert">
          <p className="font-semibold" style={{ color: C.loss.text }}>
            Questa giocata è fuori regola
          </p>
          <p className="text-[13px] text-slate-700">
            {signLabel(s.label)} a {q2(s.q)} ·{' '}
            {s.reasons.map((r) => (
              <span key={r.code} className="mr-1 inline-block rounded-md px-1.5 py-0.5 text-[12px] font-medium" style={{ color: C.loss.text, background: C.loss.bg }}>
                {r.text}
              </span>
            ))}
          </p>
          <label className="block">
            <span className="text-[13px] font-semibold text-slate-800">Perché la vuoi registrare lo stesso?</span> <span className="text-[12px] text-slate-400">(obbligatorio)</span>
            <textarea
              className="mt-1 min-h-[56px] w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              placeholder="es. «formazione ufficiale con 3 attaccanti titolari, uscita dopo la lettura del mattino»"
              value={reason}
              onChange={(e) => onReason(e.target.value)}
            />
          </label>
          <p className="text-[12px] text-slate-500">Sarà contata a parte, nelle «eccezioni», e non nel rendimento delle regole.</p>
        </div>
        {extra}
      </div>
    )
  }
  return (
    <div className="space-y-1.5">
      {s.state === 'check' ? (
        <p className="rounded-xl px-3 py-2 text-sm" style={{ color: C.warn.text, background: C.warn.bg }}>
          Da verificare: {s.reasons[0]?.text ?? 'controlla il modello'}. Si può salvare.
        </p>
      ) : (
        <p className="rounded-xl px-3 py-2 text-sm" style={{ color: C.win.text, background: C.win.bg }}>
          Giocabile: quota nella fascia e nessuna regola di blocco.
        </p>
      )}
      {s.notes.map((n) => (
        <p key={n.code} className="text-[12px]" style={{ color: C.warn.text }}>
          avviso · {n.text}
        </p>
      ))}
      {extra}
    </div>
  )
}
