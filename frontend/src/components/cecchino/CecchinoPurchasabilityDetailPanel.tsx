import type { CecchinoPurchasabilityV31Item } from '../../lib/cecchinoTodayApi'
import { formatEdgePct, formatV3Number } from './cecchinoKpiUiUtils'
import {
  buildPurchasabilityReasonBullets,
  getMarketDisplayLabel,
  getPurchasabilityClassLabel,
  getPurchasabilityScore,
  purchasabilityBadgeClass,
} from './cecchinoPurchasabilityUiUtils'

type Props = {
  item: CecchinoPurchasabilityV31Item
  panelId: string
}

function fmtQuota(v: unknown): string {
  if (v == null || v === '') return '—'
  const n = Number(v)
  return Number.isNaN(n) ? '—' : n.toFixed(2)
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null
}

export function CecchinoPurchasabilityDetailPanel({ item, panelId }: Props) {
  const score = getPurchasabilityScore(item)
  const classLabel = getPurchasabilityClassLabel(item)
  const label = getMarketDisplayLabel(item)
  const reasons = buildPurchasabilityReasonBullets(item)
  const inp = asRecord(item.input)
  const theoretical = asRecord(item.theoretical)
  const historical = asRecord(item.historical)
  const gate = asRecord(item.gate)

  return (
    <div
      id={`${panelId}-panel-${item.market_key}`}
      role="tabpanel"
      aria-labelledby={`${panelId}-tab-${item.market_key}`}
      className="rounded-xl border border-slate-200 bg-white p-4"
      data-testid="cecchino-purchasability-detail"
      data-market-key={item.market_key}
    >
      <div className="space-y-1">
        <h4 className="text-lg font-semibold text-slate-900">{label}</h4>
        <p className="text-sm text-slate-600">
          Acquistabilità{' '}
          <span className="font-semibold text-slate-900">{score ?? '—'}</span> / 100
        </p>
        {classLabel ? (
          <span className={purchasabilityBadgeClass(classLabel)}>{classLabel}</span>
        ) : null}
      </div>

      {item.reading_detailed || item.reading_short ? (
        <p className="mt-3 text-sm leading-relaxed text-slate-700">
          {item.reading_detailed ?? item.reading_short}
        </p>
      ) : null}

      {reasons.length > 0 ? (
        <section className="mt-4" data-testid="purch-reason-bullets">
          <h5 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Perché questo valore
          </h5>
          <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-slate-800">
            {reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <details className="mt-4 rounded-lg border border-slate-200 px-3 py-2">
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-slate-500">
          Dettagli tecnici
        </summary>
        <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-slate-500">Quota Book</dt>
            <dd className="font-medium tabular-nums">{fmtQuota(inp?.quota_book)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Source bookmaker</dt>
            <dd className="font-medium">{String(inp?.execution_quote_source ?? inp?.book_source ?? '—')}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Quota Cecchino</dt>
            <dd className="font-medium tabular-nums">{fmtQuota(inp?.quota_cecchino)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Edge</dt>
            <dd className="font-medium tabular-nums">{formatEdgePct(inp?.edge_pct as number | null)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Vantaggio probabilistico</dt>
            <dd className="font-medium tabular-nums">
              {inp?.probability_advantage_pp != null
                ? `${Number(inp.probability_advantage_pp).toFixed(1)} pp`
                : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Rating</dt>
            <dd className="font-medium tabular-nums">{inp?.rating != null ? String(inp.rating) : '—'}</dd>
          </div>
          <div>
            <dt className="text-slate-500">value_score</dt>
            <dd className="font-medium tabular-nums">
              {formatV3Number((item.value_score ?? theoretical?.value_score) as number | null)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">quality score</dt>
            <dd className="font-medium tabular-nums">
              {formatV3Number(
                (item.quality_score ?? theoretical?.theoretical_quality_score) as number | null,
              )}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">theoretical raw</dt>
            <dd className="font-medium tabular-nums">
              {formatV3Number(
                (item.theoretical_raw_score ??
                  item.theoretical_raw ??
                  theoretical?.theoretical_raw_score) as number | null,
              )}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">storico</dt>
            <dd className="font-medium tabular-nums">
              {historical?.historical_multiplier != null
                ? String(historical.historical_multiplier)
                : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">final score</dt>
            <dd className="font-medium tabular-nums">{score ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-slate-500">penalità</dt>
            <dd className="font-medium tabular-nums">
              {formatV3Number((item.total_penalty ?? theoretical?.theoretical_penalty_total) as number | null)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">gate</dt>
            <dd className="font-medium">{String(gate?.gate_status ?? item.gate_status ?? '—')}</dd>
          </div>
          <div>
            <dt className="text-slate-500">formula version</dt>
            <dd className="font-medium break-all text-xs">{item.formula_version ?? '—'}</dd>
          </div>
        </dl>
      </details>
    </div>
  )
}
