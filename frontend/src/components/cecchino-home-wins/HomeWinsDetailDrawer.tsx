import { CecchinoTodayKpiPanel } from '../cecchino/CecchinoTodayKpiPanel'
import type { CecchinoKpiV2Panel, CecchinoPurchasabilityPreviewItem } from '../../lib/cecchinoTodayApi'
import type { HomeWinsDetailResponse } from '../../lib/cecchinoHomeWinsApi'
import { HomeWinsBalanceSnapshotPanel } from './HomeWinsBalanceSnapshotPanel'
import { HomeWinsGoalIntensitySnapshotPanel } from './HomeWinsGoalIntensitySnapshotPanel'

type Props = {
  detail: HomeWinsDetailResponse | null
  loading?: boolean
  onClose: () => void
}

function asKpiPanel(raw: unknown): CecchinoKpiV2Panel | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  if (obj.status === 'unavailable') return null
  if (!Array.isArray(obj.rows)) return null
  return raw as CecchinoKpiV2Panel
}

function purchMap(
  preview: unknown,
): Record<string, CecchinoPurchasabilityPreviewItem> | undefined {
  if (!preview || typeof preview !== 'object') return undefined
  const items = (preview as { items?: unknown }).items
  if (!Array.isArray(items)) return undefined
  const out: Record<string, CecchinoPurchasabilityPreviewItem> = {}
  for (const item of items) {
    if (item && typeof item === 'object' && 'market_key' in item) {
      const mk = String((item as { market_key: string }).market_key)
      out[mk] = item as CecchinoPurchasabilityPreviewItem
    }
  }
  return out
}

export function HomeWinsDetailDrawer({ detail, loading, onClose }: Props) {
  if (!detail && !loading) return null

  const identity = (detail?.identity || {}) as Record<string, unknown>
  const outcome = (detail?.post_match_outcome || {}) as Record<string, unknown>
  const integrity = (detail?.source_integrity || {}) as Record<string, unknown>
  const pre = detail?.pre_match_snapshot
  const kpi = asKpiPanel(pre?.kpi_panel)
  const purch = purchMap(pre?.purchasability_preview)

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/30 backdrop-blur-[1px]">
      <button type="button" className="flex-1 cursor-default" aria-label="Chiudi" onClick={onClose} />
      <aside className="flex h-full w-full max-w-3xl flex-col overflow-hidden border-l border-slate-200 bg-[#F8F9FB] shadow-2xl">
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 bg-white px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Dettaglio esito reale 1
            </p>
            <h2 className="mt-1 text-lg font-semibold text-slate-900">
              {String(identity.home_team || '—')} – {String(identity.away_team || '—')}
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              {String(identity.league || '')} · FT {String(outcome.ft_home ?? '—')}-
              {String(outcome.ft_away ?? '—')}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Chiudi
          </button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {loading ? (
            <p className="text-sm text-slate-500">Caricamento dettaglio…</p>
          ) : (
            <>
              <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="text-base font-semibold text-slate-900">Identità e risultato</h3>
                <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-slate-500">Scan date</dt>
                    <dd className="font-medium text-slate-900">{String(identity.scan_date || '—')}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Eligibility</dt>
                    <dd className="font-medium text-slate-900">
                      {String(identity.eligibility_status || '—')}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Completezza</dt>
                    <dd className="font-medium text-slate-900">
                      {String(integrity.completeness_status || '—')}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Result source</dt>
                    <dd className="font-medium text-slate-900">
                      {String(outcome.result_source || '—')}
                    </dd>
                  </div>
                </dl>
                <p className="mt-3 text-xs text-slate-500">
                  Segnale 1 non usato per la selezione (
                  {String(
                    (detail?.selection_contract as { signal_1_used_for_selection?: boolean })
                      ?.signal_1_used_for_selection === false
                      ? 'false'
                      : 'n/d',
                  )}
                  ).
                </p>
              </section>

              {kpi ? (
                <CecchinoTodayKpiPanel panel={kpi} purchasabilityByMarketKey={purch} />
              ) : (
                <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <h3 className="text-base font-semibold text-slate-900">Pannello KPI</h3>
                  <p className="mt-2 text-sm text-slate-600">
                    Dato non disponibile nello snapshot storico
                  </p>
                </section>
              )}

              <HomeWinsBalanceSnapshotPanel snapshot={pre?.balance_v5_monitoring} />
              <HomeWinsGoalIntensitySnapshotPanel snapshot={pre?.goal_intensity_v5_preview} />

              <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="text-base font-semibold text-slate-900">Acquistabilità</h3>
                {purch ? (
                  <ul className="mt-2 space-y-1 text-sm text-slate-700">
                    {Object.entries(purch).map(([k, v]) => (
                      <li key={k}>
                        {k}: score {v.score ?? '—'} · {v.class ?? v.status ?? '—'}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-sm text-slate-600">
                    Dato non disponibile nello snapshot storico
                  </p>
                )}
              </section>

              {(detail?.warnings || []).length > 0 ? (
                <section className="rounded-xl border border-amber-200 bg-amber-50/60 p-4">
                  <h3 className="text-sm font-semibold text-amber-900">Avvisi qualità snapshot</h3>
                  <ul className="mt-2 list-disc pl-5 text-sm text-amber-800">
                    {(detail?.warnings || []).map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </section>
              ) : null}
            </>
          )}
        </div>
      </aside>
    </div>
  )
}
