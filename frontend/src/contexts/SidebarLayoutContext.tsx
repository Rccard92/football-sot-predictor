import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

const STORAGE_KEY = 'sot_sidebar_collapsed'

type SidebarLayoutContextValue = {
  collapsed: boolean
  setCollapsed: (value: boolean) => void
  toggleCollapsed: () => void
  mobileOpen: boolean
  setMobileOpen: (value: boolean) => void
  openMobile: () => void
  closeMobile: () => void
}

const SidebarLayoutContext = createContext<SidebarLayoutContextValue | null>(null)

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

export function SidebarLayoutProvider({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsedState] = useState(readCollapsed)
  const [mobileOpen, setMobileOpen] = useState(false)

  const setCollapsed = useCallback((value: boolean) => {
    setCollapsedState(value)
    try {
      localStorage.setItem(STORAGE_KEY, String(value))
    } catch {
      /* ignore */
    }
  }, [])

  const toggleCollapsed = useCallback(() => {
    setCollapsedState((prev) => {
      const next = !prev
      try {
        localStorage.setItem(STORAGE_KEY, String(next))
      } catch {
        /* ignore */
      }
      return next
    })
  }, [])

  const openMobile = useCallback(() => setMobileOpen(true), [])
  const closeMobile = useCallback(() => setMobileOpen(false), [])

  useEffect(() => {
    if (!mobileOpen) {
      document.body.style.overflow = ''
      return
    }
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [mobileOpen])

  useEffect(() => {
    if (!mobileOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeMobile()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mobileOpen, closeMobile])

  const value = useMemo(
    () => ({
      collapsed,
      setCollapsed,
      toggleCollapsed,
      mobileOpen,
      setMobileOpen,
      openMobile,
      closeMobile,
    }),
    [collapsed, setCollapsed, toggleCollapsed, mobileOpen, openMobile, closeMobile],
  )

  return <SidebarLayoutContext.Provider value={value}>{children}</SidebarLayoutContext.Provider>
}

export function useSidebarLayout(): SidebarLayoutContextValue {
  const ctx = useContext(SidebarLayoutContext)
  if (!ctx) {
    throw new Error('useSidebarLayout must be used within SidebarLayoutProvider')
  }
  return ctx
}
