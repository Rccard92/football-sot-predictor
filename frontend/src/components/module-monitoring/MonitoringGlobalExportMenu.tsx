import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { toast } from 'sonner'
import {
  downloadModuleAnalysisPack,
  formatEstimatedSize,
  formatExportCompletenessLabel,
  getModuleExportStatus,
  type ModuleExportStatus,
  type MonitoringModuleKeyApi,
} from '../../lib/cecchinoModuleMonitoringApi'
import { MONITORING_MODULES } from './moduleMonitoringRegistry'
import { monitoringStatusLabel, MOTION_FAST } from './moduleMonitoringUi'

type Props = {
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  moduleStatuses?: Record<string, string | null | undefined>
  sourceCohort?: string
}

type Pos = { top: number; left: number; openUp: boolean }

const MENU_WIDTH = 360
const MOBILE_MQ = '(max-width: 639px)'

export function MonitoringGlobalExportMenu({
  dateFrom,
  dateTo,
  competitionId,
  moduleStatuses,
  sourceCohort = 'all',
}: Props) {
  const [open, setOpen] = useState(false)
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [isMobile, setIsMobile] = useState(false)
  const [pos, setPos] = useState<Pos>({ top: 0, left: 0, openUp: false })
  const [exportStatuses, setExportStatuses] = useState<
    Record<string, ModuleExportStatus | null>
  >({})
  const [statusLoading, setStatusLoading] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const firstItemRef = useRef<HTMLButtonElement>(null)
  const menuId = useId()

  const updatePosition = useCallback(() => {
    const el = triggerRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const spaceBelow = window.innerHeight - r.bottom
    const openUp = spaceBelow < 360 && r.top > spaceBelow
    let left = r.right - MENU_WIDTH
    left = Math.max(8, Math.min(left, window.innerWidth - MENU_WIDTH - 8))
    setPos({ top: openUp ? r.top - 8 : r.bottom + 8, left, openUp })
  }, [])

  useEffect(() => {
    const mq = window.matchMedia(MOBILE_MQ)
    const apply = () => setIsMobile(mq.matches)
    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [])

  useLayoutEffect(() => {
    if (!open || isMobile) return
    updatePosition()
  }, [open, isMobile, updatePosition])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setStatusLoading(true)
    const filters = {
      date_from: dateFrom,
      date_to: dateTo,
      competition_id: competitionId ?? undefined,
      include_rows: true,
      source_cohort: sourceCohort,
    }
    void Promise.all(
      MONITORING_MODULES.map(async (m) => {
        try {
          const st = await getModuleExportStatus(m.key as MonitoringModuleKeyApi, filters)
          return [m.key, st] as const
        } catch {
          return [m.key, null] as const
        }
      }),
    )
      .then((pairs) => {
        if (cancelled) return
        setExportStatuses(Object.fromEntries(pairs))
      })
      .finally(() => {
        if (!cancelled) setStatusLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, dateFrom, dateTo, competitionId, sourceCohort])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    const onPointer = (e: MouseEvent) => {
      const t = e.target as Node
      if (triggerRef.current?.contains(t) || menuRef.current?.contains(t)) return
      setOpen(false)
      triggerRef.current?.focus()
    }
    const onScroll = () => {
      if (!isMobile) updatePosition()
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onPointer)
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', onScroll, true)
    const t = window.setTimeout(() => firstItemRef.current?.focus(), 30)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onPointer)
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', onScroll, true)
      window.clearTimeout(t)
    }
  }, [open, isMobile, updatePosition])

  async function downloadOne(key: MonitoringModuleKeyApi) {
    if (busyKey) return
    setBusyKey(key)
    toast.message(`Preparazione pacchetto ${key}…`)
    try {
      await downloadModuleAnalysisPack(key, {
        date_from: dateFrom,
        date_to: dateTo,
        competition_id: competitionId ?? undefined,
        include_rows: true,
        source_cohort: sourceCohort,
      })
      const st = exportStatuses[key]
      const label = formatExportCompletenessLabel(st)
      if (st?.completeness === 'complete') {
        toast.success(`Download pronto · forensic v4 · ${label}`)
      } else {
        toast.warning(`Download completato · forensic v4 non completo · ${label}`)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export fallito')
    } finally {
      setBusyKey(null)
    }
  }

  const panel = (
    <motion.div
      ref={menuRef}
      id={menuId}
      role="menu"
      aria-label="Esporta analisi moduli"
      initial={{ opacity: 0, y: isMobile ? 12 : 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: isMobile ? 8 : 4 }}
      transition={MOTION_FAST}
      className={
        isMobile
          ? 'fixed inset-x-3 bottom-3 z-[100] max-h-[85dvh] overflow-y-auto rounded-3xl border border-slate-200 bg-white p-4 shadow-xl'
          : 'fixed z-[100] w-[360px] rounded-2xl border border-slate-200 bg-white p-3 shadow-xl'
      }
      style={
        isMobile
          ? undefined
          : {
              top: pos.openUp ? undefined : pos.top,
              bottom: pos.openUp ? window.innerHeight - pos.top : undefined,
              left: pos.left,
            }
      }
    >
      {isMobile ? (
        <div className="relative mb-3">
          <div className="mx-auto h-1 w-10 rounded-full bg-slate-300" aria-hidden />
          <button
            type="button"
            className="absolute right-0 top-0 text-sm text-slate-500"
            onClick={() => {
              setOpen(false)
              triggerRef.current?.focus()
            }}
          >
            Chiudi
          </button>
        </div>
      ) : null}
      <h3 className="text-sm font-semibold text-slate-900">Esporta analisi moduli</h3>
      <p className="mt-1 text-xs text-slate-500">
        Scegli un modulo. Un download per scelta — non quattro automatici.
      </p>
      <p className="mt-1 text-xs text-slate-500">
        Periodo {dateFrom} → {dateTo}
        {competitionId != null ? ` · competition ${competitionId}` : ' · tutte'}
      </p>
      {statusLoading ? (
        <p className="mt-2 text-xs text-slate-500">Verifica completezza pacchetti…</p>
      ) : null}
      <ul className="mt-3 space-y-1.5">
        {MONITORING_MODULES.map((m, idx) => {
          const stApi = moduleStatuses?.[m.key]
          const label = stApi ? monitoringStatusLabel(stApi) : m.operationalStatus
          const exp = exportStatuses[m.key]
          const completeness = formatExportCompletenessLabel(exp)
          const size = formatEstimatedSize(exp?.estimated_size_bytes)
          return (
            <li key={m.key}>
              <button
                ref={idx === 0 ? firstItemRef : undefined}
                type="button"
                role="menuitem"
                disabled={busyKey != null}
                aria-label={`${m.label} ${stApi || m.key}`}
                onClick={() => void downloadOne(m.key as MonitoringModuleKeyApi)}
                className="w-full rounded-xl px-3 py-2.5 text-left hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-600 disabled:opacity-60"
              >
                <span className="block text-sm font-medium text-slate-900">{m.label}</span>
                <span className="mt-0.5 block text-xs text-slate-500">{label}</span>
                <span className="mt-0.5 block text-xs text-amber-800">
                  {completeness}
                  {size ? ` · ~${size}` : ''}
                </span>
                <span className="mt-1 block text-xs font-medium text-cyan-700">
                  {busyKey === m.key ? 'Download in corso…' : 'Scarica pacchetto'}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </motion.div>
  )

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label="Scarica analisi moduli"
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((v) => !v)}
        className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-600"
      >
        Scarica analisi
      </button>
      {typeof document !== 'undefined'
        ? createPortal(
            <AnimatePresence>
              {open ? (
                <>
                  {isMobile ? (
                    <motion.button
                      type="button"
                      aria-label="Chiudi menu export"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="fixed inset-0 z-[99] bg-slate-900/30"
                      onClick={() => {
                        setOpen(false)
                        triggerRef.current?.focus()
                      }}
                    />
                  ) : null}
                  {panel}
                </>
              ) : null}
            </AnimatePresence>,
            document.body,
          )
        : null}
    </>
  )
}
