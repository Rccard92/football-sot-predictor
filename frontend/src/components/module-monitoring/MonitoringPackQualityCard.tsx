import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  ANALYSIS_PACKS_AUDIT_TIMEOUT_MS,
  downloadModuleAnalysisPack,
  getAnalysisPacksAudit,
  type MonitoringModuleKeyApi,
  type PackAuditItem,
} from '../../lib/cecchinoModuleMonitoringApi'
import {
  AUDIT_TIMEOUT_USER_MESSAGE,
  createAuditRequestGuard,
  isAuditTimeoutError,
} from './auditRequestGuard'
import { getMonitoringModule } from './moduleMonitoringRegistry'
import { CARD_BASE } from './moduleMonitoringUi'

type Props = {
  dateFrom: string
  dateTo: string
  competitionId: string
  sourceCohort?: string
}

function tone(status: string | undefined): string {
  if (status === 'pass' || status === 'complete') return 'text-emerald-700 bg-emerald-50 border-emerald-200'
  if (status === 'fail' || status === 'blocked' || status === 'failed') {
    return 'text-rose-800 bg-rose-50 border-rose-200'
  }
  return 'text-amber-900 bg-amber-50 border-amber-200'
}

export function MonitoringPackQualityCard({
  dateFrom,
  dateTo,
  competitionId,
  sourceCohort = 'all',
}: Props) {
  const [items, setItems] = useState<PackAuditItem[]>([])
  const [loading, setLoading] = useState(false)
  const [checkedAt, setCheckedAt] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [filtersStale, setFiltersStale] = useState(false)
  const [loadingLong, setLoadingLong] = useState(false)
  const [loadingSince, setLoadingSince] = useState<number | null>(null)

  const guardRef = useRef(createAuditRequestGuard())
  const verifiedFiltersRef = useRef<string | null>(null)

  const filterKey = `${dateFrom}|${dateTo}|${competitionId}|${sourceCohort}`

  useEffect(() => {
    const verified = verifiedFiltersRef.current
    if (verified != null && verified !== filterKey && (items.length > 0 || checkedAt)) {
      setFiltersStale(true)
    }
  }, [filterKey, items.length, checkedAt])

  useEffect(() => {
    if (!loading || loadingSince == null) {
      setLoadingLong(false)
      return
    }
    const tick = () => {
      setLoadingLong(Date.now() - loadingSince >= 30_000)
    }
    tick()
    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [loading, loadingSince])

  useEffect(() => {
    const guard = guardRef.current
    return () => {
      guard.abort()
    }
  }, [])

  const load = useCallback(async () => {
    const guard = guardRef.current
    const started = guard.begin()
    if (!started) return

    const { requestId, signal } = started
    setLoading(true)
    setLoadingSince(Date.now())
    setLoadingLong(false)
    setLoadError(null)

    try {
      const payload = await getAnalysisPacksAudit(
        {
          date_from: dateFrom,
          date_to: dateTo,
          competition_id: competitionId ? Number(competitionId) : undefined,
          source_cohort: sourceCohort,
        },
        { timeoutMs: ANALYSIS_PACKS_AUDIT_TIMEOUT_MS, signal },
      )
      if (!guard.isCurrent(requestId)) return
      setItems(payload.modules || [])
      setCheckedAt(new Date().toISOString())
      verifiedFiltersRef.current = filterKey
      setFiltersStale(false)
      setLoadError(null)
      toast.success('Verifica pacchetti completata')
    } catch (err) {
      if (!guard.isCurrent(requestId)) return
      if (signal.aborted && !isAuditTimeoutError(err)) {
        return
      }
      const message = isAuditTimeoutError(err)
        ? AUDIT_TIMEOUT_USER_MESSAGE
        : 'Verifica pacchetti non riuscita'
      setLoadError(message)
      toast.error(message)
    } finally {
      guard.end(requestId)
      if (guard.isCurrent(requestId) || !guard.isInFlight()) {
        setLoading(false)
        setLoadingSince(null)
        setLoadingLong(false)
      }
    }
  }, [dateFrom, dateTo, competitionId, sourceCohort, filterKey])

  return (
    <section className={`${CARD_BASE} p-4`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Qualità pacchetti analisi</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Completezza forensic v5 — file, colonne, righe e stati tecnico/scientifico separati.
          </p>
          {checkedAt ? (
            <p className="mt-1 text-[11px] text-slate-400">
              Ultima verifica {new Date(checkedAt).toLocaleString('it-IT')}
            </p>
          ) : null}
          {filtersStale ? (
            <p className="mt-1 inline-flex rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-900">
              Filtri modificati — riverifica necessaria
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {loadError ? (
            <button
              type="button"
              disabled={loading}
              onClick={() => void load()}
              className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-sm font-medium text-rose-900 hover:bg-rose-100 disabled:opacity-60"
            >
              Riprova
            </button>
          ) : null}
          <button
            type="button"
            disabled={loading}
            onClick={() => void load()}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
          >
            {loading ? 'Verifica…' : 'Riverifica'}
          </button>
        </div>
      </div>
      {loading ? (
        <div className="mt-2 rounded-lg border border-cyan-200 bg-cyan-50/80 px-3 py-2 text-xs text-cyan-950">
          <p className="font-semibold">Verifica forensic in corso…</p>
          <p className="mt-0.5 text-cyan-800">
            Il controllo di file, colonne, righe e hash può richiedere alcuni minuti.
          </p>
          {loadingLong ? (
            <p className="mt-1 font-medium text-amber-900">
              Verifica ancora in corso — non chiudere la pagina.
            </p>
          ) : null}
        </div>
      ) : null}
      {loadError ? (
        <p className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">
          {loadError} I risultati precedenti restano visibili finché disponibili.
        </p>
      ) : null}
      <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {items.map((it) => {
          const def = getMonitoringModule(it.module_key)
          const audit = it.export_audit
          const moduleFailed =
            it.status === 'failed' || audit?.error_code === 'module_audit_failed'
          const tech =
            audit?.technical_status ||
            it.technical_status ||
            audit?.status ||
            it.completeness ||
            'partial'
          const sci = audit?.scientific_status || it.scientific_status || tech
          const required = audit?.required_files || []
          const actualSet = new Set(audit?.actual_files || [])
          const filesOk = required.filter((f) => actualSet.has(f)).length
          const filesExp = required.length || null
          const src = audit?.source_row_count
          const exp = audit?.exported_row_count ?? it.rows
          return (
            <article
              key={it.module_key}
              className={`rounded-xl border px-3 py-2.5 ${tone(moduleFailed ? 'failed' : sci)}`}
            >
              <div className="text-sm font-semibold">{def.label}</div>
              {moduleFailed ? (
                <p className="mt-1 text-xs text-rose-800">Audit non disponibile</p>
              ) : (
                <div className="mt-1 flex flex-wrap gap-2 text-[10px] font-semibold uppercase tracking-wide">
                  <span>tech: {tech}</span>
                  <span>sci: {sci}</span>
                </div>
              )}
              <dl className="mt-2 space-y-0.5 text-[11px]">
                <div className="flex justify-between gap-2">
                  <dt>File</dt>
                  <dd>
                    {filesOk}/{filesExp ?? '—'}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Righe</dt>
                  <dd>
                    {moduleFailed ? '—' : `${src ?? '—'} → ${exp ?? '—'}`}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Troncamento</dt>
                  <dd>{audit?.truncated ? 'Sì' : 'No'}</dd>
                </div>
              </dl>
              {(audit?.missing_files || []).length ? (
                <p className="mt-1 text-[10px] opacity-80">
                  Mancanti: {(audit?.missing_files || []).slice(0, 3).join(', ')}
                </p>
              ) : null}
              {!moduleFailed ? (
                <button
                  type="button"
                  className="mt-2 text-xs font-semibold underline"
                  onClick={() =>
                    void downloadModuleAnalysisPack(it.module_key as MonitoringModuleKeyApi, {
                      date_from: dateFrom,
                      date_to: dateTo,
                      competition_id: competitionId ? Number(competitionId) : undefined,
                      include_rows: true,
                      source_cohort: sourceCohort,
                    }).then(
                      () => {
                        const trunc = audit?.truncated ? ' · troncato' : ''
                        if (sci === 'pass' || sci === 'complete') {
                          toast.success(
                            `Download ${def.label} · v5 tech=${tech} sci=${sci}${trunc}`,
                          )
                        } else {
                          toast.warning(
                            `Download ${def.label} · v5 tech=${tech} sci=${sci}${trunc}`,
                          )
                        }
                      },
                      () => toast.error('Download fallito'),
                    )
                  }
                >
                  Scarica ZIP
                </button>
              ) : null}
            </article>
          )
        })}
        {!items.length && !loading && !loadError ? (
          <p className="text-sm text-slate-500">
            Nessun audit disponibile. Clicca «Riverifica» per avviare il controllo forensic.
          </p>
        ) : null}
      </div>
    </section>
  )
}
