import { useEffect, useRef, useState } from 'react'
import { AdminHttpError } from '../../lib/api'
import {
  getCecchinoLabDatasets,
  previewCecchinoLabCsv,
  replaceCecchinoLabDataset,
  replaceDatasetConfirmMessage,
  type CecchinoLabDataset,
  type CecchinoLabPreview,
} from '../../lib/cecchinoLabApi'
import { qualityLabel } from './labTheme'
import { qualityBadgeClass } from '../../lib/cecchinoLabApi'

type Props = {
  refreshKey: number
  onOpenMatches: (datasetId: number) => void
  onReplaced?: () => void
}

type ReplacePhase = 'idle' | 'preview' | 'confirm' | 'loading'

export function DatasetsTab({ refreshKey, onOpenMatches, onReplaced }: Props) {
  const [items, setItems] = useState<CecchinoLabDataset[]>([])
  const [loading, setLoading] = useState(true)
  const [country, setCountry] = useState('')
  const [competition, setCompetition] = useState('')
  const [season, setSeason] = useState('')
  const [quality, setQuality] = useState('')

  const [replaceTarget, setReplaceTarget] = useState<CecchinoLabDataset | null>(null)
  const [replaceFile, setReplaceFile] = useState<File | null>(null)
  const [replacePreview, setReplacePreview] = useState<CecchinoLabPreview | null>(null)
  const [replacePhase, setReplacePhase] = useState<ReplacePhase>('idle')
  const [replaceError, setReplaceError] = useState<string | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getCecchinoLabDatasets({
      country: country || undefined,
      competition: competition || undefined,
      season: season || undefined,
      quality_status: quality || undefined,
    })
      .then((res) => {
        if (!cancelled) setItems(res.items)
      })
      .catch(() => {
        if (!cancelled) setItems([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [refreshKey, country, competition, season, quality])

  const closeReplace = () => {
    setReplaceTarget(null)
    setReplaceFile(null)
    setReplacePreview(null)
    setReplacePhase('idle')
    setReplaceError(null)
    setConfirmed(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const startReplace = (d: CecchinoLabDataset) => {
    setReplaceTarget(d)
    setReplaceFile(null)
    setReplacePreview(null)
    setReplacePhase('idle')
    setReplaceError(null)
    setConfirmed(false)
    setTimeout(() => fileInputRef.current?.click(), 0)
  }

  const onFilePicked = async (file: File | null) => {
    if (!file || !replaceTarget) return
    setReplaceFile(file)
    setReplaceError(null)
    setReplacePhase('preview')
    setConfirmed(false)
    try {
      const competitionKey = competitionKeyFromDataset(replaceTarget)
      if (!competitionKey) {
        setReplaceError('Impossibile risolvere il campionato del dataset.')
        setReplacePhase('idle')
        return
      }
      const preview = await previewCecchinoLabCsv(file, {
        competition_key: competitionKey,
        season_label: replaceTarget.season_label,
      })
      setReplacePreview(preview)
      setReplacePhase('confirm')
    } catch (e: unknown) {
      const msg =
        e instanceof AdminHttpError
          ? e.message
          : e instanceof Error
            ? e.message
            : 'Errore preview sostituzione'
      setReplaceError(msg)
      setReplacePhase('idle')
    }
  }

  const runReplace = async () => {
    if (!replaceTarget || !replaceFile || !confirmed) return
    setReplacePhase('loading')
    setReplaceError(null)
    try {
      await replaceCecchinoLabDataset(replaceTarget.id, replaceFile)
      closeReplace()
      onReplaced?.()
    } catch (e: unknown) {
      const msg =
        e instanceof AdminHttpError
          ? e.message
          : e instanceof Error
            ? e.message
            : 'Errore sostituzione CSV'
      setReplaceError(msg)
      setReplacePhase('confirm')
    }
  }

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={(e) => void onFilePicked(e.target.files?.[0] ?? null)}
      />

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <input className="lab-input" placeholder="Paese" value={country} onChange={(e) => setCountry(e.target.value)} />
        <input className="lab-input" placeholder="Campionato" value={competition} onChange={(e) => setCompetition(e.target.value)} />
        <input className="lab-input" placeholder="Stagione" value={season} onChange={(e) => setSeason(e.target.value)} />
        <select className="lab-input" value={quality} onChange={(e) => setQuality(e.target.value)}>
          <option value="">Qualità: tutte</option>
          <option value="complete">complete</option>
          <option value="complete_with_warnings">complete_with_warnings</option>
          <option value="partial">partial</option>
          <option value="error">error</option>
          <option value="unknown">unknown</option>
        </select>
      </div>

      {loading ? (
        <p className="text-sm" style={{ color: 'var(--lab-muted)' }}>Caricamento dataset…</p>
      ) : items.length === 0 ? (
        <div className="lab-card p-10 text-center text-sm" style={{ color: 'var(--lab-muted)' }}>
          Nessun dataset. Importa un CSV per iniziare.
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {items.map((d) => (
            <div key={d.id} className="lab-card p-4">
              <button
                type="button"
                className="w-full text-left transition hover:opacity-90"
                onClick={() => onOpenMatches(d.id)}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-lg font-semibold">{d.competition_name}</div>
                    <div className="text-sm" style={{ color: 'var(--lab-muted)' }}>
                      {d.country} · {d.season_label}
                      {d.division_code ? ` · ${d.division_code}` : ''}
                    </div>
                  </div>
                  <span className={`rounded-md px-2 py-0.5 text-xs ${qualityBadgeClass(d.data_quality_status)}`}>
                    {qualityLabel(d.data_quality_status)}
                  </span>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <div style={{ color: 'var(--lab-muted)' }}>Partite</div>
                    <div className="font-semibold tabular-nums">{d.matches_count}</div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--lab-muted)' }}>Anomalie</div>
                    <div className="font-semibold tabular-nums">{d.anomalies_count ?? '—'}</div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--lab-muted)' }}>1X2</div>
                    <div className="tabular-nums">{d.bet365_1x2_coverage_pct ?? '—'}%</div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--lab-muted)' }}>O/U 2.5</div>
                    <div className="tabular-nums">{d.bet365_ou25_coverage_pct ?? '—'}%</div>
                  </div>
                </div>
              </button>
              <div className="mt-3 flex justify-end border-t pt-3" style={{ borderColor: 'var(--lab-border)' }}>
                <button
                  type="button"
                  className="text-xs font-medium underline-offset-2 hover:underline"
                  style={{ color: 'var(--lab-muted)' }}
                  onClick={(e) => {
                    e.stopPropagation()
                    startReplace(d)
                  }}
                >
                  Sostituisci CSV
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {replaceTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="lab-card max-h-[90vh] w-full max-w-lg overflow-auto p-5">
            <h3 className="text-lg font-semibold">Sostituisci CSV</h3>
            <p className="mt-2 text-sm" style={{ color: 'var(--lab-muted)' }}>
              {replaceDatasetConfirmMessage(replaceTarget.competition_name, replaceTarget.season_label)}
            </p>

            {replacePhase === 'idle' && !replaceError && (
              <p className="mt-4 text-sm" style={{ color: 'var(--lab-muted)' }}>
                Seleziona un file CSV…
              </p>
            )}

            {replacePhase === 'preview' && (
              <p className="mt-4 text-sm" style={{ color: 'var(--lab-cyan)' }}>
                Analisi del file…
              </p>
            )}

            {replacePhase === 'loading' && (
              <p className="mt-4 text-sm" style={{ color: 'var(--lab-cyan)' }}>
                Sostituzione in corso…
              </p>
            )}

            {replaceError && (
              <p className="mt-3 text-sm" style={{ color: 'var(--lab-err)' }}>
                {replaceError}
              </p>
            )}

            {replacePreview && replacePhase !== 'loading' && (
              <div className="mt-4 space-y-2 text-sm">
                <div className="grid grid-cols-2 gap-2">
                  <div>Dataset: {replaceTarget.competition_name}</div>
                  <div>Partite attuali: {replaceTarget.matches_count}</div>
                  <div>Righe nuovo file: {replacePreview.rows_total}</div>
                  <div>Importabili: {replacePreview.summary.rows_importable ?? '—'}</div>
                  <div style={{ color: 'var(--lab-err)' }}>Errori: {replacePreview.errors_count}</div>
                  <div style={{ color: 'var(--lab-warn)' }}>Warning: {replacePreview.warnings_count}</div>
                  <div style={{ color: 'var(--lab-muted)' }}>Info: {replacePreview.info_count ?? 0}</div>
                </div>
                <label className="mt-3 flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                    className="mt-1"
                  />
                  <span>Confermo di voler sostituire solo questo dataset.</span>
                </label>
              </div>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button type="button" className="lab-btn" style={{ opacity: 0.7 }} onClick={closeReplace} disabled={replacePhase === 'loading'}>
                Annulla
              </button>
              {replacePreview && (
                <button
                  type="button"
                  className="lab-btn"
                  disabled={!confirmed || replacePhase === 'loading' || !replacePreview.summary.importable}
                  onClick={() => void runReplace()}
                >
                  {replacePhase === 'loading' ? 'Attendere…' : 'Conferma sostituzione'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/** Map dataset division_code → competition catalog key used by preview/import. */
function competitionKeyFromDataset(d: CecchinoLabDataset): string | null {
  const map: Record<string, string> = {
    E0: 'premier_league',
    E1: 'championship',
    E2: 'league_one',
    E3: 'league_two',
    I1: 'serie_a',
    I2: 'serie_b',
    SP1: 'la_liga',
    SP2: 'la_liga_2',
    D1: 'bundesliga',
    D2: 'bundesliga_2',
    F1: 'ligue_1',
    F2: 'ligue_2',
    N1: 'eredivisie',
    P1: 'primeira_liga',
    B1: 'jupiler_pro_league',
    T1: 'super_lig',
  }
  if (d.division_code && map[d.division_code]) return map[d.division_code]
  return null
}
