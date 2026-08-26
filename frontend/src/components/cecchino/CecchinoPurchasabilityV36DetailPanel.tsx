import type { ReactNode } from 'react'
import type { V36Item, V36Snapshot } from '../../lib/cecchinoTodayApi'
import {
  formatV36ComponentScore,
  formatV36FinalScore,
  formatV36OptionalNumber,
  getV36MarketLabel,
  getV36RawScore,
  getV36Score,
  structuralBlockLabel,
} from './cecchinoPurchasabilityV36UiUtils'

type Props = {
  item: V36Item
  snapshot: V36Snapshot
  panelId: string
}

function Block({
  title,
  children,
  testId,
}: {
  title: string
  children: ReactNode
  testId: string
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-slate-50/70 p-3" data-testid={testId}>
      <h5 className="text-[11px] font-bold uppercase tracking-wide text-slate-600">{title}</h5>
      <div className="mt-2 space-y-2 text-sm text-slate-800">{children}</div>
    </section>
  )
}

function Metric({
  label,
  value,
  hint,
  testId,
}: {
  label: string
  value: string
  hint?: string
  testId?: string
}) {
  return (
    <div className="rounded border border-slate-100 bg-white px-2 py-1.5">
      <p className="text-[10px] uppercase text-slate-500">{label}</p>
      <p className="font-semibold tabular-nums" data-testid={testId}>
        {value}
      </p>
      {hint ? <p className="mt-0.5 text-[11px] text-slate-500">{hint}</p> : null}
    </div>
  )
}

export function CecchinoPurchasabilityV36DetailPanel({ item, snapshot, panelId }: Props) {
  const score = getV36Score(item)
  const rawScore = getV36RawScore(item)
  const v = item.components?.executable_value
  const d = item.components?.market_disagreement
  const r = item.components?.base_rate_reliability
  const s = item.components?.structural_coherence
  const q = item.components?.information_quality
  const sUnavailable =
    s?.structural_status === 'unavailable' ||
    s?.score == null ||
    item.structural_missing_penalty_applied === true
  const ev =
    item.gate?.expected_value ??
    item.input?.expected_value ??
    v?.expected_value ??
    null
  const blocks = s?.blocks ?? []

  return (
    <div
      className="space-y-3 rounded-xl border border-slate-200 bg-white p-4"
      id={`${panelId}-v36-detail`}
      data-testid="v36-detail-panel"
      role="tabpanel"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Mercato</p>
          <h4 className="text-base font-bold text-slate-900">{getV36MarketLabel(item)}</h4>
        </div>
        <div className="text-right">
          <p
            className="text-3xl font-bold tabular-nums text-slate-900"
            data-testid="v36-final-score"
          >
            {formatV36FinalScore(score)}
          </p>
        </div>
      </div>

      <Block title="INPUT" testId="v36-block-input">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <Metric
            label="Execution quote"
            value={formatV36OptionalNumber(item.input?.execution_quote)}
            testId="v36-execution-quote"
          />
          <Metric
            label="Execution quote real"
            value={item.input?.execution_quote_real === true ? 'true' : 'false'}
          />
          <Metric
            label="P Cecchino"
            value={formatV36OptionalNumber(item.input?.probability_cecchino, 3)}
          />
          <Metric
            label="P Book Fair"
            value={formatV36OptionalNumber(item.input?.fair_book_probability, 3)}
          />
          <Metric label="Rating" value={item.input?.rating != null ? String(item.input.rating) : 'N/D'} />
          <Metric label="Expected value (gate)" value={formatV36OptionalNumber(ev, 3)} />
        </div>
      </Block>

      <Block title="VALORE" testId="v36-block-valore">
        <div className="grid gap-2 sm:grid-cols-3">
          <Metric
            label="V"
            value={formatV36ComponentScore(v?.score)}
            hint="Valore matematico alla quota eseguibile"
            testId="v36-comp-V"
          />
          <Metric
            label="D"
            value={formatV36ComponentScore(d?.score)}
            hint="Divergenza Cecchino vs probabilità fair Book"
            testId="v36-comp-D"
          />
          <Metric
            label="VALUE_CORE"
            value={formatV36ComponentScore(item.value_core)}
            hint="Combinazione V + D"
            testId="v36-value-core"
          />
        </div>
      </Block>

      <Block title="AFFIDABILITÀ" testId="v36-block-affidabilita">
        <Metric
          label="Base-rate Reliability Index (R)"
          value={formatV36ComponentScore(r?.score)}
          testId="v36-comp-R"
        />
        <p className="text-[11px] text-slate-600" data-testid="v36-r-disclaimer">
          Indice conservativo della base probabilistica condivisa tra Cecchino e Book. Non è una
          probabilità calibrata di vittoria.
        </p>
        <Metric
          label="ACQUISITION_CORE"
          value={formatV36ComponentScore(item.acquisition_core)}
          testId="v36-acquisition-core"
        />
      </Block>

      <Block title="STRUTTURA" testId="v36-block-struttura">
        {sUnavailable ? (
          <p className="text-sm text-amber-800" data-testid="v36-s-missing">
            Dati strutturali insufficienti: applicata penalizzazione strutturale.
          </p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            <Metric label="S" value={formatV36ComponentScore(s?.score ?? s?.S)} testId="v36-comp-S" />
            <Metric label="S_raw" value={formatV36ComponentScore(s?.S_raw ?? s?.raw_score)} />
            <Metric
              label="structural_confidence"
              value={formatV36OptionalNumber(s?.structural_confidence, 3)}
            />
            <Metric
              label="structural_factor"
              value={formatV36OptionalNumber(item.structural_factor ?? s?.structural_factor, 3)}
            />
          </div>
        )}
        {blocks.length > 0 ? (
          <div className="space-y-2" data-testid="v36-structural-blocks">
            {blocks.map((block, idx) => (
              <div
                key={`${block.block_type ?? 'block'}-${idx}`}
                className="rounded border border-slate-200 bg-white p-2 text-xs"
                data-testid={`v36-block-${block.block_type ?? idx}`}
              >
                <p className="font-semibold text-slate-800">
                  {structuralBlockLabel(block.block_type)}
                </p>
                <p className="mt-1 text-slate-600">
                  block_raw {formatV36ComponentScore(block.block_raw)} · block_confidence{' '}
                  {formatV36OptionalNumber(block.block_confidence, 3)} · coverage{' '}
                  {formatV36OptionalNumber(block.coverage, 3)} · configured_strength{' '}
                  {formatV36OptionalNumber(block.configured_strength, 3)}
                </p>
                {block.related_markets?.length ? (
                  <p className="mt-1 text-slate-500">
                    Mercati correlati: {block.related_markets.join(', ')}
                  </p>
                ) : null}
                {block.opponents?.length ? (
                  <ul className="mt-1 space-y-0.5 text-slate-600">
                    {block.opponents.map((op) => (
                      <li key={op.related_market ?? 'op'}>
                        {op.related_market}: support{' '}
                        {formatV36ComponentScore(op.support_score)}
                        {op.data_available === false ? ' (n/d)' : ''}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </Block>

      <Block title="QUALITÀ" testId="v36-block-qualita">
        <div className="grid gap-2 sm:grid-cols-2">
          <Metric label="Q" value={formatV36ComponentScore(q?.score)} testId="v36-comp-Q" />
          <Metric
            label="quality_factor"
            value={formatV36OptionalNumber(item.quality_factor, 3)}
          />
        </div>
        <div className="text-xs text-slate-600" data-testid="v36-q-penalties">
          <p>overround_penalty {q?.overround_penalty ?? 0}</p>
          <p>fallback_penalty {q?.fallback_penalty ?? 0}</p>
          <p>derived_fair_penalty {q?.derived_fair_penalty ?? 0}</p>
          <p>extreme_divergence_penalty {q?.extreme_divergence_penalty ?? 0}</p>
        </div>
      </Block>

      <Block title="FINALE" testId="v36-block-finale">
        <ol className="space-y-1 text-xs text-slate-700" data-testid="v36-final-pipeline">
          <li>VALUE_CORE = {formatV36ComponentScore(item.value_core)}</li>
          <li>↓ ACQUISITION_CORE = {formatV36ComponentScore(item.acquisition_core)}</li>
          <li>↓ structural_factor = {formatV36OptionalNumber(item.structural_factor, 3)}</li>
          <li>↓ quality_factor = {formatV36OptionalNumber(item.quality_factor, 3)}</li>
          <li>↓ adjusted_confidence = {formatV36OptionalNumber(item.adjusted_confidence, 3)}</li>
          <li className="font-semibold">
            ↓ FINAL SCORE ={' '}
            <span data-testid="v36-final-score-pipeline">{formatV36FinalScore(score)}</span>
          </li>
        </ol>
      </Block>

      <details className="rounded-lg border border-slate-200 p-3" data-testid="v36-technical-details">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">
          Dettagli tecnici V3.6
        </summary>
        <dl className="mt-3 grid gap-1 text-xs text-slate-600 sm:grid-cols-2">
          <div>
            <dt className="font-medium">raw_score</dt>
            <dd>{rawScore != null ? rawScore.toFixed(2) : 'N/D'}</dd>
          </div>
          <div>
            <dt className="font-medium">gate_status</dt>
            <dd>{item.gate?.gate_status ?? item.gate_status ?? 'N/D'}</dd>
          </div>
          <div>
            <dt className="font-medium">formula_version</dt>
            <dd>{snapshot.formula_version ?? 'N/D'}</dd>
          </div>
          <div>
            <dt className="font-medium">formula_freeze_sha256</dt>
            <dd className="break-all">
              {snapshot.formula_freeze_sha256 ?? item.formula_freeze_sha256 ?? 'N/D'}
            </dd>
          </div>
          <div>
            <dt className="font-medium">input_fingerprint_sha256</dt>
            <dd className="break-all">{snapshot.input_fingerprint_sha256 ?? 'N/D'}</dd>
          </div>
          <div>
            <dt className="font-medium">engine_payload_sha256</dt>
            <dd className="break-all">{snapshot.engine_payload_sha256 ?? 'N/D'}</dd>
          </div>
        </dl>
      </details>
    </div>
  )
}
