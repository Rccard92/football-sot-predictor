import { useCallback, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  importCecchinoLabCsv,
  previewCecchinoLabCsv,
  type CecchinoLabImportResult,
  type CecchinoLabPreview,
  type ImportMeta,
} from '../../lib/cecchinoLabApi'
import { AdminHttpError } from '../../lib/api'

type Props = {
  onImported: (datasetId: number) => void
}

type Phase = 'select' | 'preview' | 'done'

export function ImportWizardTab({ onImported }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [phase, setPhase] = useState<Phase>('select')
  const [dragOver, setDragOver] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [meta, setMeta] = useState<ImportMeta>({
    competition_name: '',
    country: '',
    season_label: '',
    timezone: 'Europe/Rome',
    division_code: '',
  })
  const [preview, setPreview] = useState<CecchinoLabPreview | null>(null)
  const [activeFile, setActiveFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<CecchinoLabImportResult | null>(null)

  const onFiles = useCallback((list: FileList | File[]) => {
    const arr = Array.from(list).filter((f) => f.name.toLowerCase().endsWith('.csv'))
    setFiles(arr)
  }, [])

  const runPreview = async () => {
    if (!files.length) {
      toast.error('Seleziona almeno un CSV')
      return
    }
    if (!meta.competition_name.trim() || !meta.country.trim() || !meta.season_label.trim()) {
      toast.error('Compila campionato, paese e stagione')
      return
    }
    setBusy(true)
    try {
      const file = files[0]
      setActiveFile(file)
      const p = await previewCecchinoLabCsv(file, meta)
      setPreview(p)
      setPhase('preview')
      if (files.length > 1) {
        toast.message(`Anteprima del primo file (${files.length} selezionati). Gli altri verranno importati in sequenza.`)
      }
    } catch (e) {
      toast.error(e instanceof AdminHttpError ? e.message : 'Errore anteprima')
    } finally {
      setBusy(false)
    }
  }

  const runImport = async () => {
    if (!activeFile || !preview?.summary.importable) return
    const ok = window.confirm(
      `Confermi l'import di "${activeFile.name}" nel database?\n` +
        `Righe importabili: ${preview.summary.rows_importable ?? preview.rows_total}\n` +
        `Token richiesto: IMPORT_CECCHINO_LAB_CSV`,
    )
    if (!ok) return
    setBusy(true)
    try {
      let last: CecchinoLabImportResult | null = null
      for (const file of files) {
        toast.message(`Import in corso: ${file.name}`)
        last = await importCecchinoLabCsv(file, meta)
      }
      setResult(last)
      setPhase('done')
      toast.success(`Import completato: ${last?.rows_imported ?? 0} righe`)
      if (last?.dataset_id) onImported(last.dataset_id)
    } catch (e) {
      toast.error(e instanceof AdminHttpError ? e.message : 'Errore import')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6 p-4 sm:p-6">
      {phase === 'select' && (
        <>
          <div
            className={`lab-drop flex flex-col items-center justify-center gap-3 px-6 py-14 ${dragOver ? 'lab-drop-active' : ''}`}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              if (e.dataTransfer.files?.length) onFiles(e.dataTransfer.files)
            }}
          >
            <div className="text-lg font-semibold">Trascina i CSV Football-Data</div>
            <p className="text-sm" style={{ color: 'var(--lab-muted)' }}>
              UTF-8 / CP1252 · quote Bet365 normalizzate · altri bookmaker solo in raw
            </p>
            <button type="button" className="lab-btn-ghost" onClick={() => inputRef.current?.click()} disabled={busy}>
              Seleziona file
            </button>
            <input
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              multiple
              className="hidden"
              onChange={(e) => e.target.files && onFiles(e.target.files)}
            />
            {files.length > 0 && (
              <ul className="mt-2 w-full max-w-lg space-y-1 text-left text-sm">
                {files.map((f) => (
                  <li key={f.name} className="flex justify-between rounded-lg px-3 py-2" style={{ background: 'rgba(0,0,0,0.2)' }}>
                    <span>{f.name}</span>
                    <span style={{ color: 'var(--lab-muted)' }}>{(f.size / 1024).toFixed(1)} KB</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="lab-card grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
            {(
              [
                ['competition_name', 'Campionato', 'Premier League'],
                ['country', 'Paese', 'England'],
                ['division_code', 'Codice divisione', 'E0'],
                ['season_label', 'Stagione', '2024/25'],
                ['timezone', 'Timezone', 'Europe/Rome'],
              ] as const
            ).map(([key, label, placeholder]) => (
              <label key={key} className="block text-sm">
                <span className="mb-1 block" style={{ color: 'var(--lab-muted)' }}>
                  {label}
                </span>
                <input
                  className="lab-input"
                  placeholder={placeholder}
                  value={meta[key] ?? ''}
                  onChange={(e) => setMeta((m) => ({ ...m, [key]: e.target.value }))}
                  disabled={busy}
                />
              </label>
            ))}
          </div>

          <div className="flex justify-end">
            <button type="button" className="lab-btn" onClick={runPreview} disabled={busy || !files.length}>
              {busy ? 'Analisi…' : 'Anteprima'}
            </button>
          </div>
        </>
      )}

      {phase === 'preview' && preview && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="lab-card p-4">
              <div className="text-xs" style={{ color: 'var(--lab-muted)' }}>Righe</div>
              <div className="text-2xl font-semibold">{preview.rows_total}</div>
            </div>
            <div className="lab-card p-4">
              <div className="text-xs" style={{ color: 'var(--lab-muted)' }}>Importabili</div>
              <div className="text-2xl font-semibold" style={{ color: 'var(--lab-ok)' }}>
                {preview.summary.rows_importable ?? '—'}
              </div>
            </div>
            <div className="lab-card p-4">
              <div className="text-xs" style={{ color: 'var(--lab-muted)' }}>Warning</div>
              <div className="text-2xl font-semibold" style={{ color: 'var(--lab-warn)' }}>
                {preview.warnings_count}
              </div>
            </div>
            <div className="lab-card p-4">
              <div className="text-xs" style={{ color: 'var(--lab-muted)' }}>Errori</div>
              <div className="text-2xl font-semibold" style={{ color: 'var(--lab-err)' }}>
                {preview.errors_count}
              </div>
            </div>
          </div>

          <div className="lab-card p-4">
            <h3 className="mb-2 text-sm font-semibold">Coverage Bet365</h3>
            <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
              <div>1X2 pre: {preview.bet365_coverage['1x2_pre_pct'] ?? 0}%</div>
              <div>1X2 close: {preview.bet365_coverage['1x2_closing_pct'] ?? 0}%</div>
              <div>O/U pre: {preview.bet365_coverage['ou25_pre_pct'] ?? 0}%</div>
              <div>O/U close: {preview.bet365_coverage['ou25_closing_pct'] ?? 0}%</div>
            </div>
          </div>

          <div className="lab-card p-4">
            <h3 className="mb-2 text-sm font-semibold">Colonne</h3>
            <p className="text-xs" style={{ color: 'var(--lab-muted)' }}>
              Riconosciute: {preview.recognized_columns.length} · Inattese: {preview.unexpected_columns.length} ·
              Mancanti: {preview.missing_required_columns.join(', ') || 'nessuna'}
            </p>
            <div className="lab-table-wrap mt-3 max-h-56">
              <table className="lab-table">
                <thead>
                  <tr>
                    {preview.headers.slice(0, 12).map((h) => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.preview_rows.slice(0, 5).map((row, i) => (
                    <tr key={i}>
                      {preview.headers.slice(0, 12).map((h) => (
                        <td key={h}>{row[h] ?? '—'}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {preview.issues.length > 0 && (
            <div className="lab-card max-h-64 overflow-auto p-4">
              <h3 className="mb-2 text-sm font-semibold">Issue rilevate</h3>
              <ul className="space-y-1 text-sm">
                {preview.issues.slice(0, 40).map((iss, i) => (
                  <li key={i} style={{ color: iss.severity === 'error' ? 'var(--lab-err)' : iss.severity === 'warning' ? 'var(--lab-warn)' : 'var(--lab-muted)' }}>
                    [{iss.severity}] {iss.message}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex flex-wrap justify-between gap-2">
            <button type="button" className="lab-btn-ghost" disabled={busy} onClick={() => setPhase('select')}>
              Indietro
            </button>
            <button
              type="button"
              className="lab-btn"
              disabled={busy || !preview.summary.importable}
              onClick={runImport}
            >
              {busy ? 'Import in corso…' : 'Importa nel database'}
            </button>
          </div>
        </div>
      )}

      {phase === 'done' && result && (
        <div className="lab-card mx-auto max-w-lg space-y-3 p-6 text-center">
          <h2 className="text-xl font-semibold" style={{ color: 'var(--lab-ok)' }}>
            Import completato
          </h2>
          <p className="text-sm" style={{ color: 'var(--lab-muted)' }}>
            {result.rows_imported} importate · {result.rows_skipped} scartate · {result.warnings_count} warning ·{' '}
            {result.errors_count} errori
          </p>
          <button type="button" className="lab-btn" onClick={() => onImported(result.dataset_id)}>
            Vai al dataset #{result.dataset_id}
          </button>
          <button
            type="button"
            className="lab-btn-ghost ml-2"
            onClick={() => {
              setPhase('select')
              setPreview(null)
              setResult(null)
              setFiles([])
            }}
          >
            Nuovo import
          </button>
        </div>
      )}
    </div>
  )
}
