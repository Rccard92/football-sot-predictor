import type { ReactNode } from 'react'
import type {
  CecchinoPurchasabilityV35CandidateKey,
  CecchinoPurchasabilityV35Item,
  CecchinoPurchasabilityV35Snapshot,
} from '../../lib/cecchinoTodayApi'
import {
  formatV35ComponentScore,
  formatV35IntegerScore,
  formatV35Percent,
  getV35CandidateClass,
  getV35CandidateRawScore,
  getV35CandidateScore,
  getV35MarketLabel,
  V35_CANDIDATE_KEYS,
  v35BadgeClass,
} from './cecchinoPurchasabilityV35UiUtils'

type Props = {
  item: CecchinoPurchasabilityV35Item
  snapshot: CecchinoPurchasabilityV35Snapshot
  selectedCandidate: CecchinoPurchasabilityV35CandidateKey
  panelId: string
}

function ComponentCard({
  title,
  subtitle,
  score,
  children,
}: {
  title: string
  subtitle: string
  score: string
  children?: ReactNode
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold text-slate-800">{title}</p>
          <p className="mt-0.5 text-[11px] text-slate-500">{subtitle}</p>
        </div>
        <p className="text-lg font-bold tabular-nums text-slate-900" data-testid={`v35-comp-score-${title}`}>
          {score}
        </p>
      </div>
      {children ? <div className="mt-2 space-y-1 text-[11px] text-slate-600">{children}</div> : null}
    </div>
  )
}

export function CecchinoPurchasabilityV35DetailPanel({
  item,
  snapshot,
  selectedCandidate,
  panelId,
}: Props) {
  const v = item.components?.executable_value
  const d = item.components?.market_disagreement
  const s = item.components?.structural_coherence
  const q = item.components?.information_quality
  const score = getV35CandidateScore(item, selectedCandidate)
  const rawScore = getV35CandidateRawScore(item, selectedCandidate)
  const classLabel = getV35CandidateClass(item, selectedCandidate)

  return (
    <div
      className="space-y-4 rounded-xl border border-slate-200 bg-white p-4"
      id={`${panelId}-v35-detail`}
      data-testid="v35-detail-panel"
      role="tabpanel"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Mercato</p>
          <h4 className="text-base font-bold text-slate-900">{getV35MarketLabel(item)}</h4>
          <p className="mt-1 text-xs text-slate-500">
            Candidate {selectedCandidate}: score intero, raw e classe descrittiva
          </p>
        </div>
        <div className="text-right">
          <p className="text-3xl font-bold tabular-nums text-slate-900" data-testid="v35-selected-score">
            {formatV35IntegerScore(score)}
          </p>
          <p className="text-xs text-slate-500">
            raw {rawScore != null ? rawScore.toFixed(2) : '—'}
          </p>
          {classLabel ? (
            <span
              className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ${v35BadgeClass(classLabel)}`}
              data-testid="v35-selected-class"
            >
              {classLabel}
            </span>
          ) : null}
        </div>
      </div>

      <div className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-slate-100 p-2">
          <p className="text-[10px] uppercase text-slate-500">Execution quote</p>
          <p className="font-semibold tabular-nums">{item.input?.execution_quote_real ?? 'N/D'}</p>
        </div>
        <div className="rounded-lg border border-slate-100 p-2">
          <p className="text-[10px] uppercase text-slate-500">P Cecchino</p>
          <p className="font-semibold tabular-nums">
            {item.input?.probability_cecchino != null
              ? Number(item.input.probability_cecchino).toFixed(3)
              : 'N/D'}
          </p>
        </div>
        <div className="rounded-lg border border-slate-100 p-2">
          <p className="text-[10px] uppercase text-slate-500">P Book Fair</p>
          <p className="font-semibold tabular-nums">
            {item.input?.fair_book_probability != null
              ? Number(item.input.fair_book_probability).toFixed(3)
              : 'N/D'}
          </p>
        </div>
        <div className="rounded-lg border border-slate-100 p-2">
          <p className="text-[10px] uppercase text-slate-500">Rating</p>
          <p className="font-semibold tabular-nums">{item.input?.rating ?? 'N/D'}</p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <ComponentCard
          title="V"
          subtitle="Valore alla quota realmente eseguibile."
          score={formatV35ComponentScore(v?.score)}
        />
        <ComponentCard
          title="D"
          subtitle="Divergenza tra probabilità Cecchino e Book fair."
          score={formatV35ComponentScore(d?.score)}
        />
        <ComponentCard
          title="S"
          subtitle="Coerenza dei mercati strutturalmente collegati."
          score={
            s?.structural_status === 'unavailable' || s?.score == null
              ? 'N/D'
              : formatV35ComponentScore(s.score)
          }
        >
          {s?.structural_status === 'available' && s.score != null ? (
            <>
              <p>
                Raw: {formatV35ComponentScore(s.raw_score)} · Confidence:{' '}
                {formatV35Percent(s.structural_confidence)} · Coverage:{' '}
                {s.available_relation_count ?? 0}/{s.configured_relation_count ?? 0}
              </p>
              {s.relations?.length ? (
                <div className="mt-2 space-y-1" data-testid="v35-s-relations">
                  {s.relations.map((rel) => (
                    <p key={rel.related_market ?? 'unknown'}>
                      {rel.related_market}: support {formatV35ComponentScore(rel.support_score)} · Δlogit{' '}
                      {rel.related_delta_logit != null ? rel.related_delta_logit.toFixed(3) : 'N/D'} · w{' '}
                      {rel.relation_weight ?? 'N/D'}
                    </p>
                  ))}
                </div>
              ) : null}
            </>
          ) : (
            <p>Nessuna relazione strutturale utilizzabile per questo mercato.</p>
          )}
        </ComponentCard>
        <ComponentCard
          title="Q"
          subtitle="Qualità tecnica delle informazioni disponibili."
          score={formatV35ComponentScore(q?.score)}
        >
          {q?.score != null ? (
            <div data-testid="v35-q-breakdown">
              <p>
                overround penalty {q.overround_penalty ?? 0} · fallback penalty{' '}
                {q.fallback_penalty ?? 0}
              </p>
              <p>
                derived fair penalty {q.derived_fair_penalty ?? 0} · extreme divergence penalty{' '}
                {q.extreme_divergence_penalty ?? 0}
              </p>
              <p>
                overround {item.input?.overround ?? 'N/D'} · book_fallback_used{' '}
                {String(item.input?.book_fallback_used ?? false)} · fair_probability_may_be_derived{' '}
                {String(item.input?.fair_probability_may_be_derived ?? false)}
              </p>
            </div>
          ) : null}
        </ComponentCard>
      </div>

      <div className="overflow-x-auto" data-testid="v35-candidate-comparison">
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
          Confronto candidate sullo stesso mercato
        </p>
        <table className="min-w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-slate-500">
              <th className="py-1 pr-3 font-medium">Candidate</th>
              <th className="py-1 pr-3 font-medium">Score</th>
              <th className="py-1 pr-3 font-medium">Raw</th>
              <th className="py-1 font-medium">Class</th>
            </tr>
          </thead>
          <tbody>
            {V35_CANDIDATE_KEYS.map((key) => {
              const row = item.candidates?.[key]
              const highlighted = key === selectedCandidate
              return (
                <tr
                  key={key}
                  className={highlighted ? 'bg-indigo-50 font-semibold' : undefined}
                  data-testid={`v35-compare-row-${key}`}
                  data-highlighted={highlighted ? 'true' : 'false'}
                >
                  <td className="py-1 pr-3">{key}</td>
                  <td className="py-1 pr-3 tabular-nums">{formatV35IntegerScore(row?.score ?? null)}</td>
                  <td className="py-1 pr-3 tabular-nums">
                    {row?.raw_score != null ? row.raw_score.toFixed(2) : '—'}
                  </td>
                  <td className="py-1">{row?.class ?? '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <details className="rounded-lg border border-slate-200 p-3" data-testid="v35-technical-details">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">
          Dettagli tecnici V3.5
        </summary>
        <dl className="mt-3 grid gap-1 text-xs text-slate-600 sm:grid-cols-2">
          <div>
            <dt className="font-medium">gate_status</dt>
            <dd>{item.gate?.gate_status ?? item.gate_status ?? 'N/D'}</dd>
          </div>
          <div>
            <dt className="font-medium">gate reason codes</dt>
            <dd>{(item.gate?.reason_codes ?? []).join(', ') || '—'}</dd>
          </div>
          <div>
            <dt className="font-medium">expected_value</dt>
            <dd>{String(item.diagnostics?.expected_value ?? item.gate?.expected_value ?? 'N/D')}</dd>
          </div>
          <div>
            <dt className="font-medium">delta_logit</dt>
            <dd>{String(item.diagnostics?.delta_logit ?? d?.delta_logit ?? 'N/D')}</dd>
          </div>
          <div>
            <dt className="font-medium">hours_to_kickoff</dt>
            <dd>{String(item.diagnostics?.hours_to_kickoff ?? 'N/D')}</dd>
          </div>
          <div>
            <dt className="font-medium">formula_version</dt>
            <dd>{snapshot.formula_version ?? 'N/D'}</dd>
          </div>
          <div>
            <dt className="font-medium">feature_version</dt>
            <dd>{snapshot.feature_version ?? 'N/D'}</dd>
          </div>
          <div>
            <dt className="font-medium">candidate_registry_version</dt>
            <dd>{snapshot.candidate_registry_version ?? 'N/D'}</dd>
          </div>
          <div>
            <dt className="font-medium">relation_registry_version</dt>
            <dd>{snapshot.relation_registry_version ?? 'N/D'}</dd>
          </div>
          <div>
            <dt className="font-medium">source_snapshot_at</dt>
            <dd>{snapshot.source_snapshot_at ?? 'N/D'}</dd>
          </div>
          <div>
            <dt className="font-medium">input_fingerprint_sha256</dt>
            <dd className="break-all">{snapshot.input_fingerprint_sha256 ?? 'N/D'}</dd>
          </div>
          <div>
            <dt className="font-medium">engine_payload_sha256</dt>
            <dd className="break-all">{snapshot.engine_payload_sha256 ?? 'N/D'}</dd>
          </div>
          <div>
            <dt className="font-medium">pre_match_verified</dt>
            <dd>{String(snapshot.pre_match_verified ?? false)}</dd>
          </div>
        </dl>
      </details>
    </div>
  )
}
