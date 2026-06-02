import { useState } from 'react'
import type { RoundAnalysisDetail, RoundAnalysisFixtureRow } from '../../lib/api'
import {
  buildModelDebugJson,
  downloadFixtureReport,
} from './roundAnalysisReportDownload'
import { V30FixtureReasoningPanel } from './V30FixtureReasoningPanel'
import { errorCodeLabelIt, MODEL_KEYS } from './roundAnalysisUtils'

type Props = {
  detail: RoundAnalysisDetail
  competitionName?: string | null
  fixture: RoundAnalysisFixtureRow
}

const MODEL_TABS = [
  { key: MODEL_KEYS.v11, label: 'v1.1' },
  { key: MODEL_KEYS.v20, label: 'v2.0' },
  { key: MODEL_KEYS.v21, label: 'v2.1' },
  { key: MODEL_KEYS.v30, label: 'v3.0' },
] as const

export function RoundAnalysisFixtureRowDetail({ detail, competitionName, fixture }: Props) {
  const [activeTab, setActiveTab] = useState<string>(MODEL_KEYS.v11)
  const [fixtureDownloading, setFixtureDownloading] = useState(false)

  return (
    <div className="space-y-3 text-xs text-slate-700">
      {fixture.status === 'failed' ? (
        <p className="text-rose-700">{fixture.error_message ?? 'Errore calcolo'}</p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={fixtureDownloading}
          className="rounded border border-slate-300 bg-white px-2 py-1 text-[10px] font-medium hover:bg-slate-50 disabled:opacity-50"
          onClick={async (e) => {
            e.stopPropagation()
            setFixtureDownloading(true)
            try {
              await downloadFixtureReport(detail, fixture, competitionName)
            } finally {
              setFixtureDownloading(false)
            }
          }}
        >
          {fixtureDownloading ? 'Download…' : 'Scarica JSON partita'}
        </button>
      </div>

      {Object.entries(fixture.models_json).map(([key, block]) => (
        <div key={key} className="rounded-lg border border-slate-200 bg-white p-3">
          <div className="font-semibold text-slate-900">{block.label ?? key}</div>
          <p className="text-[10px] text-slate-500">
            Richiesto: {block.model_version_requested ?? key} · Usato:{' '}
            {block.model_version_used ?? '—'} · Engine: {block.model_engine_name ?? '—'}
          </p>
          <p className="text-[10px] text-slate-500">
            Status: {block.model_status ?? block.status ?? '—'}
            {block.error_code
              ? ` · ${errorCodeLabelIt(block.error_code)} (${block.error_code})`
              : ''}
          </p>
          {block.status === 'error' ? (
            <p className="text-rose-700">{block.error_message ?? block.message ?? 'Errore tecnico'}</p>
          ) : null}
          {block.status === 'no_prediction' ? (
            <p className="text-slate-600">
              ND — {block.error_message ?? block.message ?? 'Nessuna predizione'}
            </p>
          ) : (
            <p>
              Previsto: {block.predicted_home_sot ?? '—'} / {block.predicted_away_sot ?? '—'} (tot{' '}
              {block.predicted_total_sot ?? '—'})
            </p>
          )}
          {block.status === 'ok' ? (
            <>
              <p>
                Aggressiva: linea {block.aggressive_line ?? '—'} · {block.aggressive_advice ?? '—'} —{' '}
                {block.aggressive_reason ?? ''}
              </p>
              <p>
                Cauta: linea {block.cautious_line ?? '—'} · {block.cautious_advice ?? '—'} —{' '}
                {block.cautious_reason ?? ''}
              </p>
              {key === MODEL_KEYS.v30 && block.status === 'ok' ? (
                <V30FixtureReasoningPanel block={block} />
              ) : null}
            </>
          ) : null}
          {block.trace_summary &&
          typeof block.trace_summary === 'object' &&
          'missing_fields' in block.trace_summary ? (
            <p className="text-[10px] text-slate-500">
              Campi mancanti:{' '}
              {Array.isArray((block.trace_summary as { missing_fields?: string[] }).missing_fields)
                ? (block.trace_summary as { missing_fields: string[] }).missing_fields.join(', ')
                : '—'}
              {' · '}
              Prior:{' '}
              {(block.trace_summary as { prior_context?: { home_prior_matches?: number } }).prior_context
                ?.home_prior_matches ?? '—'}
              /
              {(block.trace_summary as { prior_context?: { away_prior_matches?: number } }).prior_context
                ?.away_prior_matches ?? '—'}
            </p>
          ) : null}
        </div>
      ))}

      <details className="mt-2" open>
        <summary className="cursor-pointer font-medium text-slate-800">Debug JSON modello</summary>
        <div className="mt-2 flex gap-1 border-b border-slate-200">
          {MODEL_TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`px-2 py-1 text-[10px] font-medium ${
                activeTab === tab.key
                  ? 'border-b-2 border-slate-800 text-slate-900'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
              onClick={(e) => {
                e.stopPropagation()
                setActiveTab(tab.key)
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <pre className="mt-2 max-h-48 overflow-auto rounded bg-slate-100 p-2 text-[10px]">
          {JSON.stringify(buildModelDebugJson(fixture, activeTab), null, 2)}
        </pre>
      </details>
    </div>
  )
}
