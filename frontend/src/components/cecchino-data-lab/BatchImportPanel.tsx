import { useCallback, useMemo, useRef, useState, Fragment } from 'react'
import { motion } from 'framer-motion'
import { toast } from 'sonner'
import {
  batchImportStatusBadgeClass,
  batchImportStatusLabel,
  importCecchinoLabCsv,
  isBatchItemReady,
  LAB_SEASON_OPTIONS,
  previewCecchinoLabBatch,
  type CecchinoLabBatchPreview,
  type CecchinoLabBatchPreviewItem,
} from '../../lib/cecchinoLabApi'
import { AdminHttpError } from '../../lib/api'

type Props = {
  onBatchDone: () => void
  onGoDatasets: () => void
  onGoOverview: () => void
  onImportingChange?: (importing: boolean) => void
}

type BatchFile = {
  clientFileId: string
  file: File
}

type FileRunStatus = 'pending' | 'uploading' | 'completed' | 'failed' | 'skipped'

type RunState = {
  clientFileId: string
  filename: string
  competitionName: string | null
  status: FileRunStatus
  rowsImported: number
  errorMessage: string | null
}

function newClientFileId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `f-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function statusBadgeForItem(item: CecchinoLabBatchPreviewItem): string {
  if (item.mapping_status === 'unknown_division' || item.mapping_status === 'missing_division') {
    return 'Divisione sconosciuta'
  }
  return batchImportStatusLabel(item.import_status)
}

function coveragePct(coverage: Record<string, number>, key: string): string {
  const v = coverage?.[key]
  if (v == null || Number.isNaN(v)) return '—'
  return `${v}%`
}

export function BatchImportPanel({
  onBatchDone,
  onGoDatasets,
  onGoOverview,
  onImportingChange,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const importingRef = useRef(false)
  const [dragOver, setDragOver] = useState(false)
  const [seasonLabel, setSeasonLabel] = useState('')
  const [batchFiles, setBatchFiles] = useState<BatchFile[]>([])
  const [preview, setPreview] = useState<CecchinoLabBatchPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [importing, setImporting] = useState(false)
  const [runStates, setRunStates] = useState<RunState[]>([])
  const [doneSummary, setDoneSummary] = useState<{
    completed: number
    failed: number
    skipped: number
    rowsImported: number
    errors: number
    warnings: number
  } | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const fileByClientId = useMemo(() => {
    const m = new Map<string, File>()
    for (const bf of batchFiles) m.set(bf.clientFileId, bf.file)
    return m
  }, [batchFiles])

  const invalidatePreview = useCallback(() => {
    setPreview(null)
    setRunStates([])
    setDoneSummary(null)
    setExpandedId(null)
    setConfirmOpen(false)
  }, [])

  const addFiles = useCallback(
    (list: FileList | File[]) => {
      if (importingRef.current) return
      const csvs = Array.from(list).filter((f) => f.name.toLowerCase().endsWith('.csv'))
      if (!csvs.length) {
        toast.error('Seleziona solo file .csv')
        return
      }
      setBatchFiles((prev) => {
        const next = [...prev]
        for (const file of csvs) {
          next.push({ clientFileId: newClientFileId(), file })
        }
        return next
      })
      invalidatePreview()
    },
    [invalidatePreview],
  )

  const removeFile = (clientFileId: string) => {
    if (importingRef.current) return
    setBatchFiles((prev) => prev.filter((f) => f.clientFileId !== clientFileId))
    invalidatePreview()
  }

  const onSeasonChange = (value: string) => {
    if (importingRef.current) return
    setSeasonLabel(value)
    invalidatePreview()
  }

  const runAnalyze = async () => {
    if (!seasonLabel) {
      toast.error('Seleziona la stagione')
      return
    }
    if (!batchFiles.length) {
      toast.error('Carica almeno un file CSV')
      return
    }
    setBusy(true)
    try {
      // Backend usa indici 0..n-1 come client_file_id nella richiesta multipart
      const filesInOrder = batchFiles.map((bf) => bf.file)
      const result = await previewCecchinoLabBatch(filesInOrder, seasonLabel)
      // Rimappa client_file_id backend (indice) → UUID frontend
      const remapped: CecchinoLabBatchPreview = {
        ...result,
        items: result.items.map((item, idx) => ({
          ...item,
          client_file_id: batchFiles[idx]?.clientFileId ?? item.client_file_id,
        })),
      }
      setPreview(remapped)
      setDoneSummary(null)
      setRunStates([])
      toast.success(`Analisi completata: ${remapped.files_total} file`)
    } catch (e) {
      toast.error(e instanceof AdminHttpError ? e.message : 'Errore analisi batch')
    } finally {
      setBusy(false)
    }
  }

  const readyItems = useMemo(
    () => (preview?.items ?? []).filter((i) => isBatchItemReady(i.import_status)),
    [preview],
  )

  const recognizedCompetitions = useMemo(() => {
    const names = new Set<string>()
    for (const it of preview?.items ?? []) {
      if (it.competition_name) names.add(it.competition_name)
    }
    return names.size
  }, [preview])

  const runSequentialImport = async (itemsToImport: CecchinoLabBatchPreviewItem[]) => {
    if (importingRef.current || !seasonLabel || !itemsToImport.length) return
    importingRef.current = true
    setImporting(true)
    onImportingChange?.(true)
    setConfirmOpen(false)
    setDoneSummary(null)

    const initial: RunState[] = itemsToImport.map((it) => ({
      clientFileId: it.client_file_id,
      filename: it.filename,
      competitionName: it.competition_name,
      status: 'pending',
      rowsImported: 0,
      errorMessage: null,
    }))
    setRunStates(initial)

    let completed = 0
    let failed = 0
    let rowsImported = 0
    let errors = 0
    let warnings = 0

    for (let i = 0; i < itemsToImport.length; i++) {
      const item = itemsToImport[i]
      const file = fileByClientId.get(item.client_file_id)
      setRunStates((prev) =>
        prev.map((s) =>
          s.clientFileId === item.client_file_id ? { ...s, status: 'uploading' } : s,
        ),
      )
      toast.message(`Importazione ${i + 1} di ${itemsToImport.length}: ${item.competition_name ?? item.filename}`)

      if (!file || !item.competition_key) {
        failed += 1
        setRunStates((prev) =>
          prev.map((s) =>
            s.clientFileId === item.client_file_id
              ? { ...s, status: 'failed', errorMessage: 'File o competition_key mancante' }
              : s,
          ),
        )
        continue
      }

      try {
        const res = await importCecchinoLabCsv(file, {
          competition_key: item.competition_key,
          season_label: seasonLabel,
        })
        completed += 1
        rowsImported += res.rows_imported ?? 0
        errors += res.errors_count ?? 0
        warnings += res.warnings_count ?? 0
        setRunStates((prev) =>
          prev.map((s) =>
            s.clientFileId === item.client_file_id
              ? { ...s, status: 'completed', rowsImported: res.rows_imported ?? 0 }
              : s,
          ),
        )
      } catch (e) {
        failed += 1
        const msg = e instanceof AdminHttpError ? e.message : e instanceof Error ? e.message : 'Errore import'
        setRunStates((prev) =>
          prev.map((s) =>
            s.clientFileId === item.client_file_id
              ? { ...s, status: 'failed', errorMessage: msg }
              : s,
          ),
        )
      }
    }

    const skipped = (preview?.items.length ?? 0) - itemsToImport.length
    setDoneSummary({
      completed,
      failed,
      skipped: Math.max(0, skipped),
      rowsImported,
      errors,
      warnings,
    })
    importingRef.current = false
    setImporting(false)
    onImportingChange?.(false)
    onBatchDone()
    if (failed === 0) {
      toast.success(`Import batch completato: ${completed} file, ${rowsImported} partite`)
    } else {
      toast.message(`Batch terminato: ${completed} ok, ${failed} falliti`)
    }
  }

  const retryFailed = () => {
    if (!preview || importingRef.current) return
    const failedIds = new Set(
      runStates.filter((s) => s.status === 'failed').map((s) => s.clientFileId),
    )
    const toRetry = readyItems.filter((i) => failedIds.has(i.client_file_id))
    if (!toRetry.length) {
      toast.message('Nessun file fallito da riprovare')
      return
    }
    void runSequentialImport(toRetry)
  }

  const runStatusLabel = (s: FileRunStatus): string => {
    switch (s) {
      case 'pending':
        return 'in attesa'
      case 'uploading':
        return 'in corso'
      case 'completed':
        return 'completata'
      case 'failed':
        return 'fallita'
      case 'skipped':
        return 'saltata'
      default:
        return s
    }
  }

  return (
    <div className="space-y-6">
      <div className="lab-card grid gap-4 p-4 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block" style={{ color: 'var(--lab-muted)' }}>
            Stagione
          </span>
          <select
            className="lab-input"
            value={seasonLabel}
            onChange={(e) => onSeasonChange(e.target.value)}
            disabled={busy || importing}
          >
            <option value="">Seleziona stagione…</option>
            {LAB_SEASON_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-end text-sm" style={{ color: 'var(--lab-muted)' }}>
          Il campionato viene rilevato automaticamente dalla colonna Div di ogni CSV.
        </div>
      </div>

      <div
        className={`lab-drop flex flex-col items-center justify-center gap-3 px-6 py-14 ${dragOver ? 'lab-drop-active' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          if (!importing) setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          if (!importing && e.dataTransfer.files?.length) addFiles(e.dataTransfer.files)
        }}
      >
        <div className="text-lg font-semibold">Trascina più CSV Football-Data</div>
        <p className="text-sm" style={{ color: 'var(--lab-muted)' }}>
          Stagione unica per tutti i file · mapping automatico via Div · max 20 file
        </p>
        <button
          type="button"
          className="lab-btn-ghost"
          onClick={() => inputRef.current?.click()}
          disabled={busy || importing}
        >
          Seleziona file
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          multiple
          className="hidden"
          onChange={(e) => e.target.files && addFiles(e.target.files)}
        />
      </div>

      {batchFiles.length > 0 && (
        <div className="lab-card p-4">
          <h3 className="mb-2 text-sm font-semibold">File caricati ({batchFiles.length})</h3>
          <ul className="space-y-1 text-sm">
            {batchFiles.map((bf) => (
              <li
                key={bf.clientFileId}
                className="flex items-center justify-between gap-2 rounded-lg px-3 py-2"
                style={{ background: 'rgba(0,0,0,0.2)' }}
              >
                <span className="truncate">{bf.file.name}</span>
                <span className="flex items-center gap-3 shrink-0">
                  <span style={{ color: 'var(--lab-muted)' }}>
                    {(bf.file.size / 1024).toFixed(1)} KB
                  </span>
                  <button
                    type="button"
                    className="text-xs underline-offset-2 hover:underline"
                    style={{ color: 'var(--lab-err)' }}
                    disabled={busy || importing}
                    onClick={() => removeFile(bf.clientFileId)}
                  >
                    Rimuovi
                  </button>
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex justify-end">
            <button
              type="button"
              className="lab-btn"
              disabled={busy || importing || !seasonLabel || !batchFiles.length}
              onClick={() => void runAnalyze()}
            >
              {busy ? 'Analisi…' : 'Analizza e associa'}
            </button>
          </div>
        </div>
      )}

      {preview && !doneSummary && (
        <motion.div
          className="space-y-4"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
            <SummaryCard label="File selezionati" value={preview.files_total} />
            <SummaryCard label="Campionati riconosciuti" value={recognizedCompetitions} />
            <SummaryCard label="Partite rilevate" value={preview.rows_total} />
            <SummaryCard label="File pronti" value={preview.ready_count} ok />
            <SummaryCard label="Con warning" value={preview.warning_count} warn />
            <SummaryCard label="Già presenti" value={preview.already_imported_count} />
            <SummaryCard label="Bloccati" value={preview.blocked_count} err />
          </div>

          <div className="lab-table-wrap overflow-x-auto">
            <table className="lab-table text-sm">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Div</th>
                  <th>Campionato</th>
                  <th>Paese</th>
                  <th>Righe</th>
                  <th>1X2</th>
                  <th>O/U 2.5</th>
                  <th>Err</th>
                  <th>Warn</th>
                  <th>Info</th>
                  <th>Stato</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {preview.items.map((item) => (
                  <Fragment key={item.client_file_id}>
                    <tr>
                      <td>
                        <button
                          type="button"
                          className="text-left underline-offset-2 hover:underline"
                          onClick={() =>
                            setExpandedId((id) =>
                              id === item.client_file_id ? null : item.client_file_id,
                            )
                          }
                        >
                          {item.filename}
                        </button>
                      </td>
                      <td>{item.division_code ?? '—'}</td>
                      <td>{item.competition_name ?? '—'}</td>
                      <td>{item.country ?? '—'}</td>
                      <td className="tabular-nums">{item.rows_total ?? '—'}</td>
                      <td className="tabular-nums">{coveragePct(item.bet365_coverage, '1x2_pre_pct')}</td>
                      <td className="tabular-nums">{coveragePct(item.bet365_coverage, 'ou25_pre_pct')}</td>
                      <td className="tabular-nums">{item.errors_count}</td>
                      <td className="tabular-nums">{item.warnings_count}</td>
                      <td className="tabular-nums">{item.info_count}</td>
                      <td>
                        <span className={`rounded px-2 text-xs ${batchImportStatusBadgeClass(item.import_status)}`}>
                          {statusBadgeForItem(item)}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="text-xs underline-offset-2 hover:underline"
                          style={{ color: 'var(--lab-err)' }}
                          disabled={importing}
                          onClick={() => removeFile(item.client_file_id)}
                        >
                          Rimuovi
                        </button>
                      </td>
                    </tr>
                    {expandedId === item.client_file_id && (
                      <tr>
                        <td colSpan={12} className="bg-[rgba(0,0,0,0.2)] p-3 text-xs">
                          <div className="grid gap-2 sm:grid-cols-2">
                            <div>
                              <div className="font-semibold mb-1">Colonne riconosciute</div>
                              <div style={{ color: 'var(--lab-muted)' }}>
                                {item.recognized_columns.join(', ') || '—'}
                              </div>
                            </div>
                            <div>
                              <div className="font-semibold mb-1">Preservate nel raw</div>
                              <div style={{ color: 'var(--lab-muted)' }}>
                                {item.unexpected_columns.join(', ') || '—'}
                              </div>
                            </div>
                            <div>
                              <div className="font-semibold mb-1">Blocking reason</div>
                              <div style={{ color: 'var(--lab-muted)' }}>
                                {item.blocking_reason || '—'}
                              </div>
                            </div>
                            <div>
                              <div className="font-semibold mb-1">Coverage</div>
                              <div style={{ color: 'var(--lab-muted)' }}>
                                1X2 {coveragePct(item.bet365_coverage, '1x2_pre_pct')} · O/U{' '}
                                {coveragePct(item.bet365_coverage, 'ou25_pre_pct')}
                              </div>
                            </div>
                          </div>
                          {item.issues.length > 0 && (
                            <ul className="mt-2 max-h-32 overflow-auto space-y-0.5">
                              {item.issues.slice(0, 20).map((iss, i) => (
                                <li key={i}>
                                  [{iss.severity}] {iss.message}
                                </li>
                              ))}
                            </ul>
                          )}
                          {item.preview_rows.length > 0 && (
                            <div className="lab-table-wrap mt-2 max-h-40 overflow-auto">
                              <table className="lab-table">
                                <thead>
                                  <tr>
                                    {Object.keys(item.preview_rows[0])
                                      .filter((k) => k !== '__extra_columns__')
                                      .slice(0, 8)
                                      .map((h) => (
                                        <th key={h}>{h}</th>
                                      ))}
                                  </tr>
                                </thead>
                                <tbody>
                                  {item.preview_rows.slice(0, 3).map((row, ri) => (
                                    <tr key={ri}>
                                      {Object.keys(item.preview_rows[0])
                                        .filter((k) => k !== '__extra_columns__')
                                        .slice(0, 8)
                                        .map((h) => (
                                          <td key={h}>{row[h] ?? '—'}</td>
                                        ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {runStates.length > 0 && (
            <div className="lab-card p-4">
              <h3 className="mb-2 text-sm font-semibold">
                Avanzamento
                {importing
                  ? ` — Importazione ${runStates.filter((s) => s.status === 'completed' || s.status === 'failed').length + 1} di ${runStates.length}`
                  : ''}
              </h3>
              <ul className="space-y-1 text-sm">
                {runStates.map((s) => (
                  <li key={s.clientFileId} className="flex justify-between gap-2">
                    <span>
                      {s.competitionName ?? s.filename} — {runStatusLabel(s.status)}
                    </span>
                    {s.errorMessage && (
                      <span style={{ color: 'var(--lab-err)' }}>{s.errorMessage}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex flex-wrap justify-end gap-2">
            <button
              type="button"
              className="lab-btn"
              disabled={importing || readyItems.length === 0}
              onClick={() => setConfirmOpen(true)}
            >
              {readyItems.length === 0
                ? 'Nessun file pronto'
                : `Importa ${readyItems.length} file · ${preview.rows_importable.toLocaleString('it-IT')} partite`}
            </button>
          </div>
        </motion.div>
      )}

      {doneSummary && (
        <div className="lab-card mx-auto max-w-lg space-y-3 p-6 text-center">
          <h2 className="text-xl font-semibold" style={{ color: 'var(--lab-ok)' }}>
            Batch completato
          </h2>
          <p className="text-sm" style={{ color: 'var(--lab-muted)' }}>
            {doneSummary.completed} completati · {doneSummary.failed} falliti · {doneSummary.skipped}{' '}
            saltati · {doneSummary.rowsImported} partite · {doneSummary.errors} errori ·{' '}
            {doneSummary.warnings} warning
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            {doneSummary.failed > 0 && (
              <button type="button" className="lab-btn" onClick={retryFailed} disabled={importing}>
                Riprova falliti
              </button>
            )}
            <button type="button" className="lab-btn" onClick={onGoDatasets}>
              Vai ai Dataset
            </button>
            <button type="button" className="lab-btn-ghost" onClick={onGoOverview}>
              Vai all&apos;Overview
            </button>
          </div>
        </div>
      )}

      {confirmOpen && preview && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="lab-card w-full max-w-md space-y-4 p-5">
            <h3 className="text-lg font-semibold">Conferma import multiplo</h3>
            <p className="text-sm" style={{ color: 'var(--lab-muted)' }}>
              Stagione: <strong style={{ color: 'var(--lab-text)' }}>{seasonLabel}</strong>
              <br />
              File pronti: <strong style={{ color: 'var(--lab-text)' }}>{readyItems.length}</strong>
              <br />
              Partite importabili:{' '}
              <strong style={{ color: 'var(--lab-text)' }}>
                {preview.rows_importable.toLocaleString('it-IT')}
              </strong>
            </p>
            <p className="text-xs" style={{ color: 'var(--lab-muted)' }}>
              I file verranno importati uno alla volta. Un fallimento non annulla quelli già completati.
              I file bloccati o già presenti restano esclusi.
            </p>
            <div className="flex justify-end gap-2">
              <button type="button" className="lab-btn" style={{ opacity: 0.7 }} onClick={() => setConfirmOpen(false)}>
                Annulla
              </button>
              <button
                type="button"
                className="lab-btn"
                onClick={() => void runSequentialImport(readyItems)}
              >
                Conferma e importa
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function SummaryCard({
  label,
  value,
  ok,
  warn,
  err,
}: {
  label: string
  value: number
  ok?: boolean
  warn?: boolean
  err?: boolean
}) {
  const color = err ? 'var(--lab-err)' : warn ? 'var(--lab-warn)' : ok ? 'var(--lab-ok)' : 'var(--lab-cyan)'
  return (
    <div className="lab-card p-3">
      <div className="text-xs" style={{ color: 'var(--lab-muted)' }}>
        {label}
      </div>
      <div className="mt-1 text-xl font-semibold tabular-nums" style={{ color }}>
        {value}
      </div>
    </div>
  )
}
