import { useMemo, useState } from 'react'
import type {
  ExplanationComponent,
  ExplanationFixture,
  ExplanationSampleRow,
  ExplanationVariable,
  ModelComparisonRow,
  SotFixtureExplanationResponse,
} from '../../types/sotExplanation'
import { InternalFormulaPanel, PredictionFinalFormulaSection } from './PredictionFinalFormulaSection'
import {
  AppliedVariableTraceTable,
  ComponentTreeView,
  FrameworkConsistencyCard,
} from './MatchExplanationTraceability'
import { LineupImpactSimulationCard } from '../sportapi/LineupImpactSimulationCard'
import { SportApiLineupsCard } from '../sportapi/SportApiLineupsCard'
import { PlayerDbProfilesSection } from './PlayerDbProfilesSection'
import { PredictionModelSummary } from './PredictionModelSummary'
import { SotBettingAdviceCard } from './SotBettingAdviceCard'
import { V20LineupImpactBreakdown } from './V20LineupImpactBreakdown'
import { V20_MODEL } from '../../lib/modelVersions'

function fmtDate(iso: string) {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
  } catch {
    return iso
  }
}

function Badge({
  children,
  tone,
}: {
  children: React.ReactNode
  tone: 'slate' | 'emerald' | 'rose' | 'amber' | 'violet' | 'sky'
}) {
  const map = {
    slate: 'bg-slate-100 text-slate-800 border-slate-200',
    emerald: 'bg-emerald-50 text-emerald-900 border-emerald-200',
    rose: 'bg-rose-50 text-rose-900 border-rose-200',
    amber: 'bg-amber-50 text-amber-950 border-amber-200',
    violet: 'bg-violet-50 text-violet-900 border-violet-200',
    sky: 'bg-sky-50 text-sky-900 border-sky-200',
  }
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${map[tone]}`}>
      {children}
    </span>
  )
}

function SectionCard({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-slate-50/80 px-4 py-2.5">
        <h2 className="text-sm font-semibold tracking-tight text-slate-900">{title}</h2>
        {subtitle ? <p className="mt-1 text-[11px] leading-relaxed text-slate-600">{subtitle}</p> : null}
      </div>
      <div className="p-4">{children}</div>
    </section>
  )
}

function Accordion({ title, defaultOpen, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(Boolean(defaultOpen))
  return (
    <div className="rounded-xl border border-slate-100">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium text-slate-800 hover:bg-slate-50"
        onClick={() => setOpen(!open)}
      >
        {title}
        <span className="text-slate-400">{open ? '−' : '+'}</span>
      </button>
      {open ? <div className="border-t border-slate-100 px-3 py-2">{children}</div> : null}
    </div>
  )
}

function SampleMatchesTable({ rows }: { rows: ExplanationSampleRow[] }) {
  if (!rows.length) return <p className="text-xs text-slate-500">Nessuna riga campione disponibile.</p>
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-[11px] text-slate-700">
        <thead>
          <tr className="border-b border-slate-200 text-slate-500">
            <th className="py-1.5 pr-2 font-medium">Data</th>
            <th className="py-1.5 pr-2 font-medium">Partita</th>
            <th className="py-1.5 pr-2 font-medium">Squadra</th>
            <th className="py-1.5 pr-2 font-medium">Lato</th>
            <th className="py-1.5 pr-2 font-medium">SOT</th>
            <th className="py-1.5 pr-2 font-medium">Tiri</th>
            <th className="py-1.5 pr-2 font-medium">GF</th>
            <th className="py-1.5 pr-2 font-medium">Avversario</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.fixture_id}-${r.date}-${r.side}`} className="border-b border-slate-100">
              <td className="py-1.5 pr-2 whitespace-nowrap">{fmtDate(r.date)}</td>
              <td className="py-1.5 pr-2">
                {r.home_team} – {r.away_team}
              </td>
              <td className="py-1.5 pr-2">{r.team}</td>
              <td className="py-1.5 pr-2">{r.side === 'home' ? 'Casa' : 'Trasferta'}</td>
              <td className="py-1.5 pr-2">{r.shots_on_target ?? '—'}</td>
              <td className="py-1.5 pr-2">{r.total_shots ?? '—'}</td>
              <td className="py-1.5 pr-2">{r.goals_for ?? '—'}</td>
              <td className="py-1.5 pr-2">{r.opponent}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function VariableTable({ vars }: { vars: ExplanationVariable[] }) {
  if (!vars.length) return null
  return (
    <div className="mt-2 overflow-x-auto rounded-lg border border-slate-100">
      <table className="min-w-full text-left text-[11px]">
        <thead>
          <tr className="bg-slate-50 text-slate-600">
            <th className="px-2 py-1.5 font-medium">Variabile</th>
            <th className="px-2 py-1.5 font-medium">Valore</th>
            <th className="px-2 py-1.5 font-medium">Peso</th>
            <th className="px-2 py-1.5 font-medium">Contributo</th>
            <th className="px-2 py-1.5 font-medium">Fonte</th>
            <th className="px-2 py-1.5 font-medium">Note</th>
          </tr>
        </thead>
        <tbody className="text-slate-800">
          {vars.map((v) => (
            <tr key={v.key} className="border-t border-slate-100">
              <td className="px-2 py-1.5">{v.label}</td>
              <td className="px-2 py-1.5 whitespace-nowrap">
                {v.value ?? '—'} {v.unit ? <span className="text-slate-500">{v.unit}</span> : null}
              </td>
              <td className="px-2 py-1.5">{v.weight_internal != null ? `${Math.round(v.weight_internal * 100)}%` : '—'}</td>
              <td className="px-2 py-1.5">{v.contribution ?? '—'}</td>
              <td className="px-2 py-1.5 text-slate-600">{v.data_source ?? '—'}</td>
              <td className="px-2 py-1.5">
                <div className="flex flex-wrap gap-1">
                  {v.fallback_used ? <Badge tone="amber">Fallback</Badge> : null}
                  {v.cap_applied ? <Badge tone="rose">Cap</Badge> : null}
                  {v.no_data_leakage_note ? <Badge tone="emerald">No leakage</Badge> : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const MODEL_COMPARE_ORDER: string[] = [
  'baseline_v2_1_weighted_components',
  'baseline_v2_0_lineup_impact',
  'baseline_v1_1_sot',
  'baseline_v1_0_sot',
  'baseline_v0_4_offensive_core_sot',
  'baseline_v0_3_core_sot',
  'baseline_v0_2_player_adjusted',
  'baseline_v0_2_context_player',
  'baseline_v0_1',
]

function roleBadgeTone(role: string | null | undefined): 'slate' | 'emerald' | 'violet' | 'sky' {
  if (role === 'Lineup Impact') return 'violet'
  if (role === 'stabile') return 'emerald'
  if (role === 'attivo') return 'sky'
  return 'slate'
}

function ComponentsForTeam({
  teamName,
  components,
}: {
  teamName: string
  components: ExplanationComponent[]
}) {
  if (!components.length) {
    return <p className="text-xs text-slate-500">Nessun breakdown componenti per {teamName}.</p>
  }
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{teamName}</h3>
      <div className="overflow-x-auto rounded-xl border border-slate-100">
        <table className="min-w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-slate-600">
              <th className="px-3 py-2 font-medium">Componente</th>
              <th className="px-3 py-2 font-medium">Valore</th>
              <th className="px-3 py-2 font-medium">Peso</th>
              <th className="px-3 py-2 font-medium">Contributo</th>
              <th className="px-3 py-2 font-medium">Direzione</th>
              <th className="px-3 py-2 font-medium">Dati</th>
            </tr>
          </thead>
          <tbody className="text-slate-800">
            {components.map((c) => (
              <tr key={c.id} className="border-b border-slate-100 align-top">
                <td className="px-3 py-2 font-medium text-slate-900">{c.label}</td>
                <td className="px-3 py-2 tabular-nums">{c.value ?? '—'}</td>
                <td className="px-3 py-2">{c.weight != null ? `${Math.round(c.weight * 100)}%` : '—'}</td>
                <td className="px-3 py-2 tabular-nums">{c.contribution ?? '—'}</td>
                <td className="px-3 py-2 capitalize text-slate-600">{c.direction}</td>
                <td className="px-3 py-2">
                  <Badge tone={c.data_status === 'ok' ? 'emerald' : 'amber'}>{c.data_status}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {components.map((c) => (
        <div key={`${c.id}-acc`} className="space-y-2">
          {c.internal_formula ? (
            <Accordion title={`Come è stato calcolato questo componente? — ${c.label}`}>
              <InternalFormulaPanel block={c.internal_formula} />
            </Accordion>
          ) : null}
          {c.variables?.length ? (
            <Accordion title={`Variabili usate — ${c.label}`}>
              <VariableTable vars={c.variables} />
              {c.variables.map((v) => (
                <div key={`${c.id}-${v.key}-m`} className="mt-2">
                  {(v.sample_matches?.length ?? 0) > 0 ? (
                    <Accordion title="Partite considerate (campione)">
                      {v.sample_matches_note ? <p className="mb-2 text-[11px] text-slate-600">{v.sample_matches_note}</p> : null}
                      <SampleMatchesTable rows={v.sample_matches ?? []} />
                    </Accordion>
                  ) : null}
                </div>
              ))}
            </Accordion>
          ) : null}
        </div>
      ))}
    </div>
  )
}

export function MatchExplanationView({
  data,
  onDataRefresh,
}: {
  data: SotFixtureExplanationResponse
  onDataRefresh?: () => void | Promise<void>
}) {
  const fx = data.fixture as ExplanationFixture
  const summary = data.prediction_summary

  const comparisonRows: ModelComparisonRow[] = useMemo(() => {
    const rows = data.model_comparison?.rows ?? []
    const order = new Map(MODEL_COMPARE_ORDER.map((mv, i) => [mv, i]))
    return [...rows].sort((a, b) => {
      const ia = order.get(a.model_version) ?? 999
      const ib = order.get(b.model_version) ?? 999
      return ia - ib
    })
  }, [data.model_comparison?.rows])

  const traceHome = data.applied_variable_trace?.home ?? []
  const traceAway = data.applied_variable_trace?.away ?? []
  const homeFormulaTraceCount = useMemo(() => {
    const n = data.prediction_formula_breakdown?.home?.formula_terms_count
    if (n != null) return n
    return data.prediction_formula_breakdown?.home?.components_table?.length ?? undefined
  }, [data.prediction_formula_breakdown?.home])
  const awayFormulaTraceCount = useMemo(() => {
    const n = data.prediction_formula_breakdown?.away?.formula_terms_count
    if (n != null) return n
    return data.prediction_formula_breakdown?.away?.components_table?.length ?? undefined
  }, [data.prediction_formula_breakdown?.away])

  if (!fx || !summary) return null

  return (
    <div className="space-y-5">
      <header className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
        <div className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            {fx.home_team.logo_url ? (
              <img src={fx.home_team.logo_url} alt="" className="h-10 w-10 object-contain" />
            ) : (
              <div className="h-10 w-10 rounded-full bg-slate-100" />
            )}
            <div>
              <p className="text-lg font-semibold text-slate-900">
                {fx.home_team.name} <span className="text-slate-400">–</span> {fx.away_team.name}
              </p>
              <p className="text-xs text-slate-500">
                {fmtDate(fx.kickoff_at)} · {fx.round ?? 'Giornata n/d'} · {fx.status_short}
              </p>
            </div>
            {fx.away_team.logo_url ? (
              <img src={fx.away_team.logo_url} alt="" className="h-10 w-10 object-contain" />
            ) : (
              <div className="h-10 w-10 rounded-full bg-slate-100" />
            )}
          </div>
          <div className="flex flex-col items-start gap-1.5 sm:items-end">
            <Badge tone="slate">Mercato: tiri in porta squadra</Badge>
            <Badge tone={data.actual_result?.fixture_finished ? 'violet' : 'sky'}>
              {summary.ui_mode === 'post_match_audit' ? 'Post-match audit' : 'Pre-match'}
            </Badge>
            {data.active_model_version ? (
              <p className="text-right text-[11px] text-slate-600">
                Modello: <span className="font-mono text-slate-900">{data.active_model_version}</span>
              </p>
            ) : null}
          </div>
        </div>
      </header>

      {data.framework_consistency ? (
        <SectionCard
          title="Tracciabilità variabili modello"
          subtitle="Allineamento tra voci del manifest, righe del trace applicato e ruoli (formula, contesto, qualità). I conteggi qui sono la fonte di riferimento per il registro tabellare sotto."
        >
          <p className="mb-3 text-[11px] text-slate-600">
            Modello attivo:{' '}
            <span className="font-mono text-slate-900">
              {data.framework_consistency.model_version ?? data.active_model_version ?? '—'}
            </span>
          </p>
          <FrameworkConsistencyCard fc={data.framework_consistency} traceHome={traceHome} traceAway={traceAway} />
        </SectionCard>
      ) : null}

      <SectionCard
        title="Previsione modello"
        subtitle="Solo valori previsti dal modello attivo — senza esito reale post-partita."
      >
        <PredictionModelSummary
          fixture={fx}
          home={summary.home}
          away={summary.away}
          matchTotal={summary.match_total}
        />
      </SectionCard>

      {data.betting_advice ? <SotBettingAdviceCard advice={data.betting_advice} /> : null}

      {data.active_model_version === V20_MODEL ? (
        <V20LineupImpactBreakdown
          fixture={fx}
          homeSummary={summary.home}
          awaySummary={summary.away}
          lineupImpact={data.lineup_impact_simulation}
          sportapiFetchedAt={data.sportapi_lineups?.fetched_at ?? null}
          activeModelVersion={data.active_model_version}
        />
      ) : null}

      {data.prediction_formula_breakdown?.home || data.prediction_formula_breakdown?.away ? (
        <SectionCard title="Formula finale della previsione">
          <div className="space-y-6">
            <PredictionFinalFormulaSection
              teamName={fx.home_team.name}
              formula={data.prediction_formula_breakdown?.home ?? undefined}
              cardPredicted={summary.home.predicted_sot}
              traceFormulaCount={homeFormulaTraceCount}
            />
            <PredictionFinalFormulaSection
              teamName={fx.away_team.name}
              formula={data.prediction_formula_breakdown?.away ?? undefined}
              cardPredicted={summary.away.predicted_sot}
              traceFormulaCount={awayFormulaTraceCount}
            />
          </div>
        </SectionCard>
      ) : null}

      {data.component_tree?.home?.length || data.component_tree?.away?.length ? (
        <SectionCard title="Albero componenti">
          <div className="space-y-6">
            <ComponentTreeView nodes={data.component_tree?.home ?? []} teamName={fx.home_team.name} />
            <div className="border-t border-slate-100" />
            <ComponentTreeView nodes={data.component_tree?.away ?? []} teamName={fx.away_team.name} />
          </div>
        </SectionCard>
      ) : null}

      <div className="flex flex-col gap-5">
        <SportApiLineupsCard
          data={data.sportapi_lineups}
          apiFixtureId={fx.api_fixture_id}
          fixtureId={fx.fixture_id}
          kickoffAt={fx.kickoff_at}
          activeModelVersion={data.active_model_version}
          lineupImpact={data.lineup_impact_simulation}
          onDataRefresh={onDataRefresh}
          regenerateV20AfterFetch={data.active_model_version === V20_MODEL}
        />

        <LineupImpactSimulationCard
          data={data.lineup_impact_simulation}
          fixtureId={fx.fixture_id}
          onDataRefresh={onDataRefresh}
        />
      </div>

      <PlayerDbProfilesSection fixtureId={fx.fixture_id} />

      {(data.applied_variable_trace?.home?.length ?? 0) > 0 || (data.applied_variable_trace?.away?.length ?? 0) > 0 ? (
        <SectionCard title="Registro variabili applicate (trace)">
          <p className="mb-3 text-[11px] text-slate-600">
            Una riga per applicazione tracciata. I totali in «Tracciabilità variabili modello» sono la fonte principale; qui
            puoi filtrare per formula finale, contesto/rischio, qualità dati o righe con dato mancante.
          </p>
          <p className="mb-2 text-xs font-semibold text-slate-900">{fx.home_team.name}</p>
          <AppliedVariableTraceTable rows={data.applied_variable_trace?.home ?? []} />
          <p className="mb-2 mt-6 text-xs font-semibold text-slate-900">{fx.away_team.name}</p>
          <AppliedVariableTraceTable rows={data.applied_variable_trace?.away ?? []} />
        </SectionCard>
      ) : null}

      {data.human_summary ? (
        <SectionCard title="Spiegazione sintetica">
          <p className="text-sm leading-relaxed text-slate-800">{data.human_summary}</p>
        </SectionCard>
      ) : null}

      <SectionCard title="Come è stato costruito il numero">
        <ComponentsForTeam teamName={fx.home_team.name} components={data.components?.home ?? []} />
        <div className="my-6 border-t border-slate-100" />
        <ComponentsForTeam teamName={fx.away_team.name} components={data.components?.away ?? []} />
      </SectionCard>

      {comparisonRows.length > 0 || data.model_comparison?.warning ? (
        <SectionCard title="Confronto con versioni precedenti">
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-slate-600">
                  <th className="py-2 pr-3 font-medium">Modello</th>
                  <th className="py-2 pr-3 font-medium">{fx.home_team.name}</th>
                  <th className="py-2 pr-3 font-medium">{fx.away_team.name}</th>
                  <th className="py-2 pr-3 font-medium">Totale</th>
                </tr>
              </thead>
              <tbody className="text-slate-800">
                {comparisonRows.map((r) => (
                  <tr key={r.model_version} className="border-b border-slate-100">
                    <td className="py-2 pr-3">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-mono text-[11px]">{r.label}</span>
                        {r.role_label ? <Badge tone={roleBadgeTone(r.role_label)}>{r.role_label}</Badge> : null}
                      </div>
                    </td>
                    <td className="py-2 pr-3 tabular-nums">{r.home ?? '—'}</td>
                    <td className="py-2 pr-3 tabular-nums">{r.away ?? '—'}</td>
                    <td className="py-2 pr-3 tabular-nums">{r.total ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.model_comparison?.warning ? (
            <p className="mt-3 text-[11px] text-amber-800">{data.model_comparison.warning}</p>
          ) : null}
          {data.model_comparison?.deltas_text?.length ? (
            <p className="mt-3 text-[11px] leading-relaxed text-slate-600">
              {data.model_comparison.deltas_text.join(' · ')}
            </p>
          ) : null}
        </SectionCard>
      ) : null}

      <SectionCard title="Controlli qualità">
        <ul className="space-y-1.5 text-sm text-slate-800">
          {(data.quality_checks?.items ?? []).map((it) => (
            <li key={it} className="flex gap-2">
              <span className="text-slate-400">•</span>
              <span>{it}</span>
            </li>
          ))}
        </ul>
      </SectionCard>

      <Accordion title="Variabili non applicate al modello attivo">
        <p className="text-[11px] text-slate-600">
          {data.not_applied_variables?.note ??
            'Le variabili del Framework non incluse nel manifest del modello attivo non entrano nel conteggio “applicate”. Filtra per modello nella pagina Framework Analisi.'}
        </p>
        {data.not_applied_variables?.items && data.not_applied_variables.items.length > 0 ? (
          <pre className="mt-2 max-h-48 overflow-auto rounded bg-slate-50 p-2 text-[10px]">
            {JSON.stringify(data.not_applied_variables.items, null, 2)}
          </pre>
        ) : null}
      </Accordion>

      <Accordion title="Audit tecnico completo (raw JSON salvato)">
        <pre className="max-h-[420px] overflow-auto rounded-lg bg-slate-900 p-3 text-[10px] leading-relaxed text-emerald-100">
          {JSON.stringify(data.technical_audit?.prediction_raw_json ?? {}, null, 2)}
        </pre>
        {data.technical_audit?.data_policy ? (
          <p className="mt-2 text-[11px] text-slate-600">
            No leakage: {data.technical_audit.data_policy.no_data_leakage ? 'sì' : 'no'} — {data.technical_audit.data_policy.included_matches_rule}
          </p>
        ) : null}
      </Accordion>
    </div>
  )
}
