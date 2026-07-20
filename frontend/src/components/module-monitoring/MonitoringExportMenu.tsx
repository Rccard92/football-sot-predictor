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
  downloadModuleRowsCsv,
  downloadModuleSummaryJson,
  formatEstimatedSize,
  formatExportCompletenessLabel,
  getModuleExportStatus,
  type ModuleExportStatus,
  type MonitoringModuleKeyApi,
} from '../../lib/cecchinoModuleMonitoringApi'
import { getMonitoringModule } from './moduleMonitoringRegistry'
import { MOTION_FAST } from './moduleMonitoringUi'

type BusyAction = 'zip' | 'csv' | 'json' | null

type Props = {
  moduleKey: MonitoringModuleKeyApi
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  marketKey?: string
  includeRows?: boolean
  showRowsCsv?: boolean
  sourceCohort?: string
}

type Pos = { top: number; left: number; openUp: boolean }

const MENU_WIDTH = 320
const MOBILE_MQ = '(max-width: 639px)'

export function MonitoringExportMenu({
  moduleKey,
  dateFrom,
  dateTo,
  competitionId,
  marketKey,
  includeRows = true,
  showRowsCsv,
  sourceCohort = 'all',
}: Props) {
  const mod = getMonitoringModule(moduleKey)
  const canRows =
    showRowsCsv ?? mod.exportCapabilities.includes('rows-csv')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<BusyAction>(null)
  const [isMobile, setIsMobile] = useState(false)
  const [pos, setPos] = useState<Pos>({ top: 0, left: 0, openUp: false })
  const [exportStatus, setExportStatus] = useState<ModuleExportStatus | null>(null)
  const [statusLoading, setStatusLoading] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const firstItemRef = useRef<HTMLButtonElement>(null)
  const menuId = useId()

  const filters = {
    date_from: dateFrom,
    date_to: dateTo,
    competition_id: competitionId ?? undefined,
    market_key: marketKey || undefined,
    include_rows: includeRows,
    source_cohort: sourceCohort,
  }

  const completenessLabel = formatExportCompletenessLabel(exportStatus)
  const sizeLabel = formatEstimatedSize(exportStatus?.estimated_size_bytes)
  const isPartial =
    exportStatus != null &&
    exportStatus.completeness !== 'complete' &&
    exportStatus.completeness !== 'blocked'

  const updatePosition = useCallback(() => {
    const el = triggerRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const spaceBelow = window.innerHeight - r.bottom
    const openUp = spaceBelow < 280 && r.top > spaceBelow
    let left = r.right - MENU_WIDTH
    left = Math.max(8, Math.min(left, window.innerWidth - MENU_WIDTH - 8))
    const top = openUp ? r.top - 8 : r.bottom + 8
    setPos({ top, left, openUp })
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
    void getModuleExportStatus(moduleKey, filters)
      .then((st) => {
        if (!cancelled) setExportStatus(st)
      })
      .catch(() => {
        if (!cancelled) setExportStatus(null)
      })
      .finally(() => {
        if (!cancelled) setStatusLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on open + filters
  }, [open, moduleKey, dateFrom, dateTo, competitionId, marketKey, includeRows])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    const onScroll = () => {
      if (isMobile) return
      updatePosition()
    }
    const onResize = () => {
      if (!isMobile) updatePosition()
    }
    const onPointer = (e: MouseEvent) => {
      const t = e.target as Node
      if (triggerRef.current?.contains(t)) return
      if (menuRef.current?.contains(t)) return
      setOpen(false)
      triggerRef.current?.focus()
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onPointer)
    window.addEventListener('resize', onResize)
    window.addEventListener('scroll', onScroll, true)
    const t = window.setTimeout(() => firstItemRef.current?.focus(), 30)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onPointer)
      window.removeEventListener('resize', onResize)
      window.removeEventListener('scroll', onScroll, true)
      window.clearTimeout(t)
    }
  }, [open, isMobile, updatePosition])

  async function run(
    action: BusyAction,
    fn: () => Promise<void>,
    startMsg: string,
  ) {
    if (busy) return
    setBusy(action)
    toast.message(startMsg)
    try {
      await fn()
      const label = formatExportCompletenessLabel(exportStatus)
      if (exportStatus?.completeness === 'complete') {
        toast.success(`Download pronto · ${label}`)
      } else if (exportStatus?.completeness === 'blocked') {
        toast.warning(`Download completato · ${label}`)
      } else {
        toast.warning(`Download completato · pacchetto non completo · ${label}`)
      }
      setOpen(false)
      triggerRef.current?.focus()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export fallito')
    } finally {
      setBusy(null)
    }
  }

  const panel = (
    <motion.div
      ref={menuRef}
      id={menuId}
      role="menu"
      aria-label={`Esporta ${mod.label}`}
      initial={{ opacity: 0, y: isMobile ? 12 : 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: isMobile ? 8 : 4 }}
      transition={MOTION_FAST}
      className={
        isMobile
          ? 'fixed inset-x-3 bottom-3 z-[100] max-h-[85dvh] overflow-y-auto rounded-3xl border border-slate-200 bg-white p-4 shadow-xl'
          : 'fixed z-[100] w-[320px] rounded-2xl border border-slate-200 bg-white p-3 shadow-xl'
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
        <div className="mb-3 flex items-center justify-between">
          <div className="mx-auto h-1 w-10 rounded-full bg-slate-300" aria-hidden />
          <button
            type="button"
            className="absolute right-4 top-3 text-sm text-slate-500"
            onClick={() => {
              setOpen(false)
              triggerRef.current?.focus()
            }}
          >
            Chiudi
          </button>
        </div>
      ) : null}
      <h3 className="text-sm font-semibold text-slate-900">Esporta {mod.label}</h3>
      <p className="mt-1 text-xs text-slate-500">
        Periodo {dateFrom} → {dateTo}
        {competitionId != null ? ` · competition ${competitionId}` : ' · tutte'}
      </p>
      <div
        className={`mt-2 rounded-xl border px-2.5 py-2 text-xs ${
          isPartial || exportStatus?.completeness === 'empty'
            ? 'border-amber-200 bg-amber-50 text-amber-900'
            : exportStatus?.completeness === 'blocked'
              ? 'border-rose-200 bg-rose-50 text-rose-900'
              : 'border-slate-200 bg-slate-50 text-slate-700'
        }`}
      >
        {statusLoading
          ? 'Verifica completezza…'
          : `${completenessLabel}${sizeLabel ? ` · ~${sizeLabel}` : ''}`}
        {exportStatus?.source_cohorts ? (
          <div className="mt-1 text-[11px] opacity-80">
            Coorti:{' '}
            {Object.entries(exportStatus.source_cohorts)
              .map(([k, v]) => `${k}=${v}`)
              .join(' · ') || '—'}
          </div>
        ) : null}
      </div>
      <ul className="mt-3 space-y-1">
        <li>
          <button
            ref={firstItemRef}
            type="button"
            role="menuitem"
            disabled={busy != null}
            onClick={() =>
              void run(
                'zip',
                () => downloadModuleAnalysisPack(moduleKey, filters),
                'Preparazione pacchetto…',
              )
            }
            className="w-full rounded-xl px-3 py-2.5 text-left hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-600 disabled:opacity-60"
          >
            <span className="block text-sm font-medium text-slate-900">
              Scarica pacchetto per ChatGPT
              {busy === 'zip' ? '…' : ''}
            </span>
            <span className="mt-0.5 block text-xs text-slate-500">
              ZIP con handoff, manifest v2, summary e dataset modulo.
            </span>
          </button>
        </li>
        {canRows ? (
          <li>
            <button
              type="button"
              role="menuitem"
              disabled={busy != null}
              onClick={() =>
                void run(
                  'csv',
                  () => downloadModuleRowsCsv(moduleKey, filters),
                  'Preparazione CSV…',
                )
              }
              className="w-full rounded-xl px-3 py-2.5 text-left hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-600 disabled:opacity-60"
            >
              <span className="block text-sm font-medium text-slate-900">
                Scarica CSV righe
                {busy === 'csv' ? '…' : ''}
              </span>
              <span className="mt-0.5 block text-xs text-slate-500">
                CSV UTF-8 (BOM) del dataset tabellare del modulo.
              </span>
            </button>
          </li>
        ) : null}
        <li>
          <button
            type="button"
            role="menuitem"
            disabled={busy != null}
            onClick={() =>
              void run(
                'json',
                () => downloadModuleSummaryJson(moduleKey, filters),
                'Preparazione riepilogo…',
              )
            }
            className="w-full rounded-xl px-3 py-2.5 text-left hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-600 disabled:opacity-60"
          >
            <span className="block text-sm font-medium text-slate-900">
              Scarica riepilogo JSON
              {busy === 'json' ? '…' : ''}
            </span>
            <span className="mt-0.5 block text-xs text-slate-500">
              JSON strict con metriche aggregate.
            </span>
          </button>
        </li>
      </ul>
    </motion.div>
  )

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={`Scarica analisi ${mod.label}`}
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
