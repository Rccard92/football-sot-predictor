import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { getMe, logout as apiLogout, type AuthMe } from '../lib/authApi'
import { AUTH_REQUIRED_EVENT, announceAdminAuthChanged } from '../lib/adminAuthEvents'
import { canSeeTab } from '../config/tabAccess'

type AuthContextValue = {
  loading: boolean
  me: AuthMe | null
  isAdmin: boolean
  allowedTabs: string[]
  /** true quando il tool e' protetto e non c'e' una sessione valida */
  needsLogin: boolean
  /** true finche' l'utente non sceglie una password sua (primo accesso o reset) */
  needsPasswordChange: boolean
  refresh: () => Promise<void>
  logout: () => Promise<void>
  canSee: (tabKey: string | null) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true)
  const [me, setMe] = useState<AuthMe | null>(null)

  const refresh = useCallback(async () => {
    try {
      setMe(await getMe())
    } catch {
      // backend irraggiungibile: niente blocco qui, le pagine mostrano il loro errore
      setMe(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let alive = true
    getMe()
      .then(
        (m) => alive && setMe(m),
        () => alive && setMe(null),
      )
      .finally(() => alive && setLoading(false))
    const onRequired = () => void refresh()
    window.addEventListener(AUTH_REQUIRED_EVENT, onRequired)
    return () => {
      alive = false
      window.removeEventListener(AUTH_REQUIRED_EVENT, onRequired)
    }
  }, [refresh])

  const logout = useCallback(async () => {
    try {
      await apiLogout()
    } finally {
      announceAdminAuthChanged(false)
      await refresh()
    }
  }, [refresh])

  const value = useMemo<AuthContextValue>(() => {
    const authenticated = Boolean(me?.authenticated)
    // senza protezione attiva (o backend non raggiungibile) chi non ha fatto l'accesso vede tutto come prima
    const open = !authenticated && !me?.enforced
    const isAdmin = open || Boolean(me?.is_admin)
    const allowedTabs = me?.allowed_tabs ?? []
    return {
      loading,
      me,
      isAdmin,
      allowedTabs,
      needsLogin: Boolean(me?.enforced) && !authenticated,
      needsPasswordChange: authenticated && Boolean(me?.must_change_password),
      refresh,
      logout,
      canSee: (tabKey) => canSeeTab(tabKey, isAdmin, allowedTabs),
    }
  }, [loading, me, refresh, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth va usato dentro AuthProvider')
  return ctx
}
