import { useState } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { requestAdminLogin } from '../../lib/adminAuthEvents'
import { ChangePasswordDialog } from './ChangePasswordDialog'

const buttonBase = 'flex w-full items-center rounded-xl border text-xs font-medium transition-colors'

/** In fondo al menu: chi ha fatto l'accesso, cambio password ed esci (prende il posto di "Accedi come admin"). */
export function UserMenu({ collapsed }: { collapsed: boolean }) {
  const { me, logout } = useAuth()
  const [changing, setChanging] = useState(false)

  if (!me?.authenticated) {
    const label = 'Accedi'
    return (
      <button
        type="button"
        onClick={() => requestAdminLogin('Accedi con il tuo account.')}
        aria-label={label}
        title={label}
        data-testid="user-menu-login"
        className={`mb-2 ${buttonBase} border-slate-200/80 bg-white text-slate-600 hover:bg-slate-50 ${
          collapsed ? 'justify-center p-2.5' : 'gap-2 px-3 py-2'
        }`}
      >
        <span aria-hidden>○</span>
        {!collapsed ? <span>{label}</span> : null}
      </button>
    )
  }

  const user = me.user
  const name = user ? `${user.first_name} ${user.last_name}` : 'Accesso di emergenza'
  const role = me.is_admin ? 'Amministratore' : 'Utente'
  return (
    <div className="mb-2 space-y-1" data-testid="user-menu">
      {!collapsed ? (
        <div className="px-3 py-1">
          <p className="truncate text-[13px] font-semibold text-slate-800" title={user?.email ?? name}>
            {name}
          </p>
          <p className="text-[11px] text-slate-500">{role}</p>
        </div>
      ) : null}
      {user && !collapsed ? (
        <button
          type="button"
          onClick={() => setChanging(true)}
          className={`${buttonBase} gap-2 border-slate-200/80 bg-white px-3 py-2 text-slate-600 hover:bg-slate-50`}
        >
          Cambia password
        </button>
      ) : null}
      <button
        type="button"
        onClick={() => void logout()}
        aria-label="Esci"
        title={collapsed ? `${name} · esci` : 'Esci'}
        className={`${buttonBase} border-slate-200/80 bg-white text-slate-600 hover:bg-slate-50 ${
          collapsed ? 'justify-center p-2.5' : 'gap-2 px-3 py-2'
        }`}
      >
        <span aria-hidden>⏻</span>
        {!collapsed ? <span>Esci</span> : null}
      </button>
      {changing ? <ChangePasswordDialog required={false} onClose={() => setChanging(false)} /> : null}
    </div>
  )
}
