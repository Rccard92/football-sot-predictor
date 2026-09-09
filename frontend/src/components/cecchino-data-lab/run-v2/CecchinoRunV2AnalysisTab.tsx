import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  formatRunV2Date,
  isRunV2Completed,
  listRunsV2,
  runV2ScopeLabel,
  runV2StatusLabel,
  type CecchinoRunV2,
} from '../../../lib/cecchinoRunV2Api'
import { CecchinoRunV2DetailPanel } from './CecchinoRunV2DetailPanel'
import { RunV2Stat } from './RunV2Stat'

/**
 * Vista preparatoria: rende una RUN V2 selezionabile per il futuro Pattern Lab V2.
 * Nessun collegamento al Pattern Lab V1, per non contaminare le analisi esistenti.
 */
export function CecchinoRunV2AnalysisTab() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [runs, setRuns] = useState<CecchinoRunV2[]>([])
  const [loading, setLoading] = useState(true)
  const [detailOpen, setDetailOpen] = useState(false)

  const selectedId = useMemo(() => {
    const raw = searchParams.get('run_v2_id')
    const parsed = raw ? Number(raw) : NaN
    return Number.isFinite(parsed) ? parsed : null
  }, [searchParams])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setRuns(await listRunsV2())
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Errore caricamento RUN V2')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const selectable = useMemo(() => runs.filter((r) => isRunV2Completed(r)), [runs])
  const selected = useMemo(
    () => runs.find((r) => r.run_id === selectedId) ?? null,
    [runs, selectedId],
  )

  const selectRun = (runId: number | null) => {
    const next = new URLSearchParams(searchParams)
    if (runId == null) next.delete('run_v2_id')
    else next.set('run_v2_id', String(runId))
    setSearchParams(next, { replace: true })
    setDetailOpen(false)
  }

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <section className="lab-card rounded-xl p-4">
        <div
          className="text-xs font-semibold uppercase tracking-[0.2em]"
          style={{ color: 'var(--lab-cyan)' }}
        >
          Cecchino RUN V2
        </div>
        <h2 className="mt-1 text-lg font-semibold">Analisi V2 — area preparatoria</h2>
        <p className="mt-1 max-w-3xl text-sm" style={{ color: 'var(--lab-muted)' }}>
          Qui si sceglie la RUN V2 su cui lavorerà il futuro Pattern Mining V2. Il Pattern Lab
          V1 resta separato e continua a ragionare solo sulle scansioni storiche V1: le due
          analisi non si mescolano.
        </p>

        <label className="mt-4 block max-w-md text-sm">
          RUN V2 selezionata
          <select
            className="lab-input mt-1 block w-full rounded-md px-3 py-2"
            data-testid="run-v2-analysis-select"
            value={selectedId ?? ''}
            onChange={(e) => selectRun(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">— nessuna —</option>
            {selectable.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                RUN #{r.run_id} · {formatRunV2Date(r.created_at)} · {runV2ScopeLabel(r)} ·{' '}
                {r.matches_processed} match
              </option>
            ))}
          </select>
        </label>
        {!loading && !selectable.length && (
          <p className="mt-2 text-sm" style={{ color: 'var(--lab-muted)' }}>
            Nessuna RUN V2 completata: avviane una dalla sezione Scansioni storiche.
          </p>
        )}
      </section>

      {selected && (
        <section className="lab-card rounded-xl p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="font-semibold">
                RUN V2 #{selected.run_id} — {runV2StatusLabel(selected.effective_status)}
              </h3>
              <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
                {selected.run_version} · creata il {formatRunV2Date(selected.created_at)}
              </p>
            </div>
            <button
              type="button"
              className="lab-btn rounded-md px-3 py-1.5 text-sm"
              data-testid="run-v2-analysis-toggle-detail"
              onClick={() => setDetailOpen((v) => !v)}
            >
              {detailOpen ? 'Nascondi dettaglio' : 'Mostra dettaglio ed export'}
            </button>
          </div>

          <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <RunV2Stat
              label="Match processati"
              value={`${selected.matches_processed}/${selected.matches_total}`}
            />
            <RunV2Stat label="Righe mercato" value={String(selected.market_rows_written)} />
            <RunV2Stat
              label="Competizioni"
              value={String(selected.summary?.competitions?.length ?? 0)}
            />
            <RunV2Stat
              label="Leakage violations"
              value={String(selected.leakage_violations)}
              tone={selected.leakage_violations > 0 ? 'danger' : 'ok'}
            />
          </div>

          <p className="mt-4 text-sm" style={{ color: 'var(--lab-muted)' }}>
            Il Pattern Mining V2 arriverà in un task successivo. Nel frattempo la RUN è
            analizzabile tramite i cinque artefatti di export, rigenerati dal database.
          </p>
        </section>
      )}

      {selected && detailOpen && (
        <CecchinoRunV2DetailPanel run={selected} onClose={() => setDetailOpen(false)} />
      )}
    </div>
  )
}
