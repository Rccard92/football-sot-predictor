import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { AdminHttpError } from '../../lib/api'
import {
  activateUser,
  createUser,
  deactivateUser,
  listLoginEvents,
  listTabs,
  listUserSessions,
  listUsers,
  resetUserPassword,
  revokeUserSessions,
  updateUser,
  type AppUser,
  type LoginEvent,
  type TabInfo,
  type UserInput,
  type UserRole,
  type UserSession,
} from '../../lib/authApi'
import { useAuth } from '../../contexts/AuthContext'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from '../cecchino/cecchinoTodayStyles'

const inputClass =
  'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none'
const btn = 'rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[13px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60'
const btnPrimary = 'rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60'

const EMPTY: UserInput = { first_name: '', last_name: '', email: '', phone: '', role: 'user', tabs: [] }

function fmt(ts: string | null | undefined): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString('it-IT', { timeZone: 'Europe/Rome', dateStyle: 'short', timeStyle: 'short' })
}

function device(ua: string | null): string {
  if (!ua) return 'dispositivo sconosciuto'
  const os = /iPhone|iPad/.test(ua) ? 'iPhone/iPad' : /Android/.test(ua) ? 'Android' : /Windows/.test(ua) ? 'Windows' : /Mac OS/.test(ua) ? 'Mac' : 'altro'
  const browser = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : /Firefox\//.test(ua) ? 'Firefox' : 'browser'
  return `${browser} · ${os}`
}

const REASONS: Record<string, string> = {
  ok: 'accesso',
  emergenza: 'accesso di emergenza',
  password_errata: 'password errata',
  utente_sconosciuto: 'email sconosciuta',
  disattivato: 'account disattivato',
  logout: 'uscito',
  limite_dispositivi: 'scollegato: limite di 2 dispositivi',
  revoca: 'scollegato dall’amministratore',
  password: 'scollegato: password cambiata',
}

function errorText(e: unknown): string {
  return e instanceof AdminHttpError ? e.message : e instanceof Error ? e.message : 'Operazione non riuscita'
}

/** Messaggio pronto da incollare su WhatsApp: la password si vede solo qui, una volta. */
function welcomeMessage(user: AppUser, password: string): string {
  return [
    `Ciao ${user.first_name}, ecco il tuo accesso al Cecchino:`,
    `${window.location.origin}`,
    `Email: ${user.email}`,
    `Password: ${password}`,
    'Al primo accesso ti verrà chiesto di scegliere una password tua.',
  ].join('\n')
}

function PasswordBox({ user, password, onClose }: { user: AppUser; password: string; onClose: () => void }) {
  const message = welcomeMessage(user, password)
  const copy = (text: string) => {
    void navigator.clipboard?.writeText(text).then(
      () => toast.success('Copiato'),
      () => toast.error('Copia non riuscita: seleziona il testo a mano'),
    )
  }
  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
      <p className="text-sm font-semibold text-emerald-900">
        Password per {user.first_name} {user.last_name}
      </p>
      <p className="mt-1 text-[13px] text-emerald-800">
        La vedi solo adesso: copiala e mandala. Al primo accesso dovrà cambiarla.
      </p>
      <p className="mt-2 font-mono text-base tracking-wide text-slate-900">{password}</p>
      <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-white p-3 text-[13px] text-slate-700">{message}</pre>
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" className={btn} onClick={() => copy(message)}>
          Copia messaggio
        </button>
        <button type="button" className={btn} onClick={() => copy(password)}>
          Copia solo password
        </button>
        <button type="button" className={btn} onClick={onClose}>
          Fatto
        </button>
      </div>
    </div>
  )
}

function UserForm({
  initial,
  tabs,
  isSelf,
  busy,
  onSubmit,
  onCancel,
}: {
  initial: UserInput
  tabs: TabInfo[]
  isSelf: boolean
  busy: boolean
  onSubmit: (input: UserInput) => void
  onCancel: () => void
}) {
  const [form, setForm] = useState<UserInput>(initial)
  const set = <K extends keyof UserInput>(key: K, value: UserInput[K]) => setForm((f) => ({ ...f, [key]: value }))
  const groups = useMemo(() => {
    const out = new Map<string, TabInfo[]>()
    for (const t of tabs) out.set(t.group, [...(out.get(t.group) ?? []), t])
    return [...out.entries()]
  }, [tabs])
  const toggleTab = (key: string) =>
    set('tabs', form.tabs.includes(key) ? form.tabs.filter((k) => k !== key) : [...form.tabs, key])

  return (
    <form
      className="space-y-4 rounded-xl border border-slate-200 bg-slate-50/60 p-4"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit(form)
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="text-[13px] font-medium text-slate-600">Nome</span>
          <input className={inputClass} value={form.first_name} onChange={(e) => set('first_name', e.target.value)} required />
        </label>
        <label className="block">
          <span className="text-[13px] font-medium text-slate-600">Cognome</span>
          <input className={inputClass} value={form.last_name} onChange={(e) => set('last_name', e.target.value)} required />
        </label>
        <label className="block">
          <span className="text-[13px] font-medium text-slate-600">Email (serve per accedere)</span>
          <input type="email" className={inputClass} value={form.email} onChange={(e) => set('email', e.target.value)} required />
        </label>
        <label className="block">
          <span className="text-[13px] font-medium text-slate-600">Telefono</span>
          <input type="tel" className={inputClass} value={form.phone} onChange={(e) => set('phone', e.target.value)} />
        </label>
      </div>

      <fieldset>
        <legend className="text-[13px] font-medium text-slate-600">Ruolo</legend>
        <div className="mt-1 flex flex-wrap gap-4 text-sm text-slate-700">
          {(['admin', 'user'] as UserRole[]).map((role) => (
            <label key={role} className="flex items-center gap-2">
              <input
                type="radio"
                name="role"
                checked={form.role === role}
                onChange={() => set('role', role)}
                disabled={isSelf && role === 'user'}
              />
              {role === 'admin' ? 'Amministratore (vede tutto)' : 'Utente (solo le schede scelte)'}
            </label>
          ))}
        </div>
      </fieldset>

      {form.role === 'user' ? (
        <fieldset>
          <legend className="text-[13px] font-medium text-slate-600">
            Schede visibili ({form.tabs.length}) — tutte le altre restano nascoste e bloccate
          </legend>
          <div className="mt-2 grid gap-3 sm:grid-cols-3">
            {groups.map(([group, items]) => (
              <div key={group}>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{group}</p>
                <div className="mt-1 space-y-1">
                  {items.map((t) => (
                    <label key={t.key} className="flex items-center gap-2 text-sm text-slate-700">
                      <input type="checkbox" checked={form.tabs.includes(t.key)} onChange={() => toggleTab(t.key)} />
                      {t.label}
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </fieldset>
      ) : null}

      <div className="flex justify-end gap-2">
        <button type="button" className={btn} onClick={onCancel} disabled={busy}>
          Annulla
        </button>
        <button type="submit" className={btnPrimary} disabled={busy}>
          {busy ? 'Salvo…' : 'Salva'}
        </button>
      </div>
    </form>
  )
}

function UserActivity({ user }: { user: AppUser }) {
  const [sessions, setSessions] = useState<UserSession[] | null>(null)
  const [events, setEvents] = useState<LoginEvent[] | null>(null)
  useEffect(() => {
    listUserSessions(user.id).then((r) => setSessions(r.sessions), () => setSessions([]))
    listLoginEvents(user.id).then((r) => setEvents(r.events.slice(0, 20)), () => setEvents([]))
  }, [user.id, user.active_devices])
  return (
    <div className="grid gap-4 border-t border-slate-100 bg-slate-50/60 p-3 sm:grid-cols-2">
      <div>
        <p className="text-[13px] font-semibold text-slate-700">Dispositivi</p>
        {sessions === null ? (
          <p className="text-[13px] text-slate-500">Carico…</p>
        ) : sessions.length === 0 ? (
          <p className="text-[13px] text-slate-500">Nessun accesso finora.</p>
        ) : (
          <ul className="mt-1 space-y-1 text-[13px] text-slate-600">
            {sessions.slice(0, 8).map((s) => (
              <li key={s.id}>
                <span className={s.active ? 'font-medium text-emerald-700' : 'text-slate-500'}>
                  {s.active ? '● collegato' : '○ ' + (REASONS[s.revoke_reason ?? ''] ?? 'scaduto')}
                </span>{' '}
                · {device(s.user_agent)} · entrato {fmt(s.created_at)} · ultimo uso {fmt(s.last_seen_at)}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <p className="text-[13px] font-semibold text-slate-700">Ultimi tentativi di accesso</p>
        {events === null ? (
          <p className="text-[13px] text-slate-500">Carico…</p>
        ) : events.length === 0 ? (
          <p className="text-[13px] text-slate-500">Nessun tentativo.</p>
        ) : (
          <ul className="mt-1 space-y-1 text-[13px] text-slate-600">
            {events.map((e) => (
              <li key={e.id}>
                <span className={e.success ? 'text-emerald-700' : 'text-rose-700'}>{e.success ? '✓' : '✗'}</span>{' '}
                {fmt(e.created_at)} · {REASONS[e.reason ?? ''] ?? e.reason} · {device(e.user_agent)}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

/** Utenti e accessi (dal 29/10/2026): creazione con password generata, schede visibili, revoca, storico. */
export function UsersAdminPanel() {
  const { me } = useAuth()
  const [users, setUsers] = useState<AppUser[] | null>(null)
  const [tabs, setTabs] = useState<TabInfo[]>([])
  const [failed24h, setFailed24h] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<AppUser | 'new' | null>(null)
  const [busy, setBusy] = useState(false)
  const [issued, setIssued] = useState<{ user: AppUser; password: string } | null>(null)
  const [openActivity, setOpenActivity] = useState<number | null>(null)

  const fetchAll = useCallback(
    () =>
      Promise.all([listUsers(), listTabs(), listLoginEvents()]).then(
        ([u, t, ev]) => {
          setUsers(u.users)
          setTabs(t.tabs)
          setFailed24h(ev.failed_last_24h)
          setError(null)
        },
        (e: unknown) => setError(errorText(e)),
      ),
    [],
  )
  const load = useCallback(() => fetchAll(), [fetchAll])

  useEffect(() => {
    void fetchAll()
  }, [fetchAll])

  const tabLabel = useMemo(() => new Map(tabs.map((t) => [t.key, t.label])), [tabs])
  const selfId = me?.user?.id ?? null

  const run = async (action: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    try {
      await action()
      toast.success(ok)
      await load()
    } catch (e) {
      toast.error(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  const save = async (input: UserInput) => {
    setBusy(true)
    try {
      if (editing === 'new') {
        const res = await createUser(input)
        setIssued(res)
        toast.success('Utente creato')
      } else if (editing) {
        await updateUser(editing.id, input)
        toast.success('Utente aggiornato')
      }
      setEditing(null)
      await load()
    } catch (e) {
      toast.error(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  const resetPassword = async (user: AppUser) => {
    if (!window.confirm(`Generare una nuova password per ${user.first_name} ${user.last_name}? Verrà scollegato da tutti i dispositivi.`)) return
    setBusy(true)
    try {
      setIssued(await resetUserPassword(user.id))
      await load()
    } catch (e) {
      toast.error(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className={`${todayCard} ${todayCardPadding} space-y-4`} data-testid="users-admin-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className={todaySectionTitle}>Utenti e accessi</h2>
          <p className={todaySectionSubtitle}>
            Chi può entrare nel tool e quali schede vede. Gli account non si cancellano: si disattivano.
            {failed24h ? ` · ${failed24h} tentativi falliti nelle ultime 24 ore` : ''}
          </p>
        </div>
        <button type="button" className={btnPrimary} onClick={() => setEditing('new')} disabled={busy || editing !== null}>
          Nuovo utente
        </button>
      </div>

      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      {issued ? <PasswordBox user={issued.user} password={issued.password} onClose={() => setIssued(null)} /> : null}
      {editing ? (
        <UserForm
          key={editing === 'new' ? 'new' : editing.id}
          initial={
            editing === 'new'
              ? EMPTY
              : {
                  first_name: editing.first_name,
                  last_name: editing.last_name,
                  email: editing.email,
                  phone: editing.phone ?? '',
                  role: editing.role,
                  tabs: editing.tabs,
                }
          }
          tabs={tabs}
          isSelf={editing !== 'new' && editing.id === selfId}
          busy={busy}
          onSubmit={(input) => void save(input)}
          onCancel={() => setEditing(null)}
        />
      ) : null}

      {users === null ? (
        error ? null : <p className="text-sm text-slate-500">Carico gli utenti…</p>
      ) : users.length === 0 ? (
        <p className="text-sm text-slate-500">Nessun utente ancora. Crea il primo (te stesso come amministratore).</p>
      ) : (
        <div className="divide-y divide-slate-100 rounded-xl border border-slate-200">
          {users.map((u) => {
            const status = !u.is_active
              ? { label: 'Disattivato', cls: 'bg-slate-100 text-slate-600' }
              : u.must_change_password
                ? { label: 'In attesa del primo accesso', cls: 'bg-amber-50 text-amber-800' }
                : { label: 'Attivo', cls: 'bg-emerald-50 text-emerald-800' }
            const tabsText =
              u.role === 'admin' ? 'Tutte le schede' : u.tabs.length ? u.tabs.map((k) => tabLabel.get(k) ?? k).join(', ') : 'Nessuna scheda'
            return (
              <div key={u.id}>
                <div className="flex flex-wrap items-start justify-between gap-3 p-3">
                  <div className="min-w-0 space-y-0.5">
                    <p className="text-sm font-semibold text-slate-900">
                      {u.first_name} {u.last_name}{' '}
                      <span className={`ml-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${status.cls}`}>{status.label}</span>{' '}
                      <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                        {u.role === 'admin' ? 'Amministratore' : 'Utente'}
                      </span>
                    </p>
                    <p className="text-[13px] text-slate-600">
                      {u.email}
                      {u.phone ? ` · ${u.phone}` : ''}
                    </p>
                    <p className="text-[13px] text-slate-500">
                      Ultimo accesso {fmt(u.last_login_at)} · dispositivi collegati {u.active_devices ?? 0}/2
                    </p>
                    <p className="text-[13px] text-slate-500">{tabsText}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" className={btn} onClick={() => setEditing(u)} disabled={busy || editing !== null}>
                      Modifica
                    </button>
                    <button type="button" className={btn} onClick={() => setOpenActivity(openActivity === u.id ? null : u.id)}>
                      {openActivity === u.id ? 'Chiudi accessi' : 'Accessi'}
                    </button>
                    {u.id !== selfId ? (
                      <>
                        <button type="button" className={btn} onClick={() => void resetPassword(u)} disabled={busy}>
                          Nuova password
                        </button>
                        {u.active_devices ? (
                          <button
                            type="button"
                            className={btn}
                            onClick={() => void run(() => revokeUserSessions(u.id), 'Dispositivi scollegati')}
                            disabled={busy}
                          >
                            Scollega dispositivi
                          </button>
                        ) : null}
                        {u.is_active ? (
                          <button
                            type="button"
                            className={`${btn} text-rose-700`}
                            onClick={() => {
                              if (window.confirm(`Disattivare ${u.first_name} ${u.last_name}? Esce subito da tutti i dispositivi.`)) {
                                void run(() => deactivateUser(u.id), 'Utente disattivato')
                              }
                            }}
                            disabled={busy}
                          >
                            Disattiva
                          </button>
                        ) : (
                          <button type="button" className={btn} onClick={() => void run(() => activateUser(u.id), 'Utente riattivato')} disabled={busy}>
                            Riattiva
                          </button>
                        )}
                      </>
                    ) : null}
                  </div>
                </div>
                {openActivity === u.id ? <UserActivity user={u} /> : null}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
