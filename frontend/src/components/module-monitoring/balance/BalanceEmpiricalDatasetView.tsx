import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import {
  BALANCE_EMPIRICAL_SYNC_CONFIRM,
  getBalanceEmpiricalCardinality,
  getBalanceEmpiricalHealth,
  getBalanceEmpiricalTargetContract,
  planBalanceEmpiricalSync,
  runBalanceEmpiricalSync,
  type BalanceEmpiricalCardinality,
  type BalanceEmpiricalHealth,
  type BalanceEmpiricalSyncResult,
} from '../../../lib/cecchinoModuleMonitoringApi'
import { MonitoringMetricCard } from '../MonitoringMetricCard'
import { CARD_BASE } from '../moduleMonitoringUi'

type Props = {
  dateFrom: string
  dateTo: string
  competitionId?: number | null
  cohortFilter?: string
}

export function BalanceEmpiricalDatasetView({
  dateFrom,
  dateTo,
  competitionId,
  cohortFilter = 'all',
}: Props) {
  const [health, setHealth] = useState<BalanceEmpiricalHealth | null>(null)
  const [cardinality, setCardinality] = useState<BalanceEmpiricalCardinality | null>(null)
  const [contractVersion, setContractVersion] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<'plan' | 'run' | null>(null)
  const [plan, setPlan] = useState<BalanceEmpiricalSyncResult | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      try {
        const filters = {
          date_from: dateFrom,
          date_to: dateTo,
          competition_id: competitionId ?? undefined,
          source_cohort: cohortFilter,
        }
        const [h, c, contract] = await Promise.all([
          getBalanceEmpiricalHealth(filters),
          getBalanceEmpiricalCardinality(filters),
          getBalanceEmpiricalTargetContract(),
        ])
        if (cancelled) return
        setHealth(h)
        setCardinality(c)
        setContractVersion(
          typeof contract.version === 'string' ? contract.version : null,
        )
      } catch (err) {
        if (!cancelled) {
          toast.error(err instanceof Error ? err.message : 'Caricamento dataset fallito')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [dateFrom, dateTo, competitionId, cohortFilter])

  async function analyze() {
    setBusy('plan')
    try {
      const payload = await planBalanceEmpiricalSync({
        date_from: dateFrom,
        date_to: dateTo,
        competition_id: competitionId ?? null,
        source_cohort: cohortFilter,
      })
      setPlan(payload)
      toast.success('Dry-run sync completato')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Dry-run fallito')
    } finally {
      setBusy(null)
    }
  }

  async function confirmRun() {
    setBusy('run')
    try {
      const payload = await runBalanceEmpiricalSync({
        date_from: dateFrom,
        date_to: dateTo,
        competition_id: competitionId ?? null,
        source_cohort: cohortFilter,
        confirm: BALANCE_EMPIRICAL_SYNC_CONFIRM,
      })
      setPlan(payload)
      setConfirmOpen(false)
      toast.success('Sync empirico Balance completato')
      const filters = {
        date_from: dateFrom,
        date_to: dateTo,
        competition_id: competitionId ?? undefined,
        source_cohort: cohortFilter,
      }
      const [h, c] = await Promise.all([
        getBalanceEmpiricalHealth(filters),
        getBalanceEmpiricalCardinality(filters),
      ])
      setHealth(h)
      setCardinality(c)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Sync fallito')
    } finally {
      setBusy(null)
    }
  }

  const card = cardinality || (health?.cardinality as BalanceEmpiricalCardinality | undefined)
  const cohorts = Object.entries(card?.by_source_cohort || {})
  const statuses = Object.entries(card?.by_evaluation_status || {})

  return (
    <div className="space-y-4">
      <div className={`${CARD_BASE} space-y-2 p-4`}>
        <h3 className="text-sm font-semibold text-slate-900">Dataset empirico in raccolta</h3>
        <p className="text-sm text-slate-600">
          Persistenza e settlement delle snapshot Balance già calcolate. Non modifica formule,
          soglie, classi o Signals. Lo storico diagnostic non promuove. Win-rate,
          calibrazione e test statistici sono disponibili dall’analisi completa
          (Overview → Avvia analisi completa / job Step 2B).
        </p>
        {(health?.notes || []).map((n) => (
          <p key={n} className="text-xs text-amber-800">
            {n}
          </p>
        ))}
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Caricamento stato dataset…</p>
      ) : (
        <>
          <section className="space-y-2">
            <h4 className="text-xs font-bold uppercase tracking-wide text-slate-500">
              Stato dataset
            </h4>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <MonitoringMetricCard label="Fixture" value={String(card?.fixtures ?? 0)} />
              <MonitoringMetricCard label="Righe correnti" value={String(card?.rows ?? 0)} />
              <MonitoringMetricCard label="Settled" value={String(card?.settled ?? 0)} />
              <MonitoringMetricCard label="Pending" value={String(card?.pending ?? 0)} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <MonitoringMetricCard
                label="Prospettiche"
                value={String(card?.prospective ?? 0)}
              />
              <MonitoringMetricCard
                label="Diagnostiche"
                value={String(card?.diagnostic ?? 0)}
              />
              <MonitoringMetricCard
                label="Timestamp verificati"
                value={String(health?.timestamp_verified ?? 0)}
              />
              <MonitoringMetricCard
                label="Promotion eligible"
                value={String(card?.promotion_eligible ?? 0)}
              />
            </div>
            <p className="text-xs text-slate-500">
              Dataset {health?.dataset_version || '—'} · Contract{' '}
              {contractVersion || health?.target_contract_version || '—'}
            </p>
          </section>

          <section className="space-y-2">
            <h4 className="text-xs font-bold uppercase tracking-wide text-slate-500">
              Coorti
            </h4>
            {cohorts.length === 0 ? (
              <p className="text-sm text-slate-500">Nessuna riga empirica nel periodo.</p>
            ) : (
              <ul className="space-y-1 text-sm text-slate-700">
                {cohorts.map(([k, v]) => (
                  <li key={k}>
                    {k}: {v}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-2">
            <h4 className="text-xs font-bold uppercase tracking-wide text-slate-500">
              Qualità temporale / governance
            </h4>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <MonitoringMetricCard
                label="Snapshot pre-match"
                value={String(health?.pre_match_snapshots ?? 0)}
              />
              <MonitoringMetricCard
                label="Timestamp non verificati"
                value={String(health?.timestamp_unverified ?? 0)}
              />
              <MonitoringMetricCard
                label="Book verificati"
                value={String(health?.book_verified ?? 0)}
              />
            </div>
            {statuses.length > 0 ? (
              <ul className="space-y-1 text-sm text-slate-700">
                {statuses.map(([k, v]) => (
                  <li key={k}>
                    {k}: {v}
                  </li>
                ))}
              </ul>
            ) : null}
            <p className="text-xs text-slate-600">
              Governance: dataset empirico in raccolta — nessuna promozione automatica.
            </p>
          </section>
        </>
      )}

      <div className={`${CARD_BASE} space-y-3 p-4`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h4 className="text-sm font-semibold text-slate-900">Sync dataset empirico</h4>
            <p className="mt-0.5 text-xs text-slate-500">
              Dry-run → conferma → run. Nessuna chiamata API esterna; non muta{' '}
              <code className="text-[11px]">cecchino_output_json</code>.
            </p>
          </div>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => void analyze()}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          >
            {busy === 'plan' ? 'Analisi…' : 'Dry-run sync'}
          </button>
        </div>
        {plan ? (
          <div className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-xs text-slate-700">
            <p>
              dry_run={String(plan.dry_run)} · fixtures={String(plan.source_fixtures ?? '—')} ·
              new={String(plan.rows_new ?? '—')} · updatable={String(plan.rows_updatable ?? '—')} ·
              skipped={String(plan.rows_skipped ?? '—')} · settled={String(plan.settled ?? '—')} ·
              failed={String(plan.failed ?? '—')}
            </p>
            {plan.dry_run !== false ? (
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => setConfirmOpen(true)}
                className="mt-2 rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
              >
                Esegui sync
              </button>
            ) : null}
          </div>
        ) : null}
        {confirmOpen ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-3 text-sm text-amber-950">
            <p>
              Confermi lo sync empirico Balance v5 sul periodo selezionato? Token richiesto:{' '}
              <code className="text-xs">{BALANCE_EMPIRICAL_SYNC_CONFIRM}</code>
            </p>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => void confirmRun()}
                className="rounded-lg bg-amber-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                {busy === 'run' ? 'Esecuzione…' : 'Conferma run'}
              </button>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => setConfirmOpen(false)}
                className="rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-sm"
              >
                Annulla
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
