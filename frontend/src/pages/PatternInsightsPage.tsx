import { useCallback, useEffect, useState } from 'react'
import { Kpi, PatternInsightsShell, Section } from '../components/pattern-insights/PatternInsightsShell'
import {
  AnatomyBlock,
  DataFoundationBlock,
  MarketValueBlock,
  SignalNoiseBlock,
  SituationsBlock,
} from '../components/pattern-insights/PatternInsightsBlocks'
import { PatternExplorer } from '../components/pattern-insights/PatternExplorer'
import { MarketScoreboardBlock } from '../components/pattern-insights/MarketScoreboardBlock'
import {
  MarketValidationBlock,
  PersistenceBlock,
  SampleProofBlock,
  ShrinkageBlock,
  SituationValidationBlock,
  ValidationHeadlineBlock,
} from '../components/pattern-insights/PatternValidationBlocks'
import {
  getMarketScoreboard,
  getPatternInsightAnalytics,
  getValidationAnalytics,
  type MarketScoreboard,
  type PatternInsightAnalytics,
  type TierKey,
  type ValidationAnalytics,
} from '../lib/patternInsightsApi'

const MIN_N_OPTIONS = [20, 50, 100, 200]

export function PatternInsightsPage() {
  const [minN, setMinN] = useState(50)
  const [data, setData] = useState<PatternInsightAnalytics | null>(null)
  const [validation, setValidation] = useState<ValidationAnalytics | null>(null)
  const [scoreboard, setScoreboard] = useState<MarketScoreboard | null>(null)
  const [validationId, setValidationId] = useState<number | null>(null)
  const [tier, setTier] = useState<TierKey>('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [analytics, validationAnalytics] = await Promise.all([
        getPatternInsightAnalytics(minN),
        getValidationAnalytics(minN, validationId, tier),
      ])
      setData(analytics)
      setValidation(validationAnalytics)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore caricamento analisi')
    } finally {
      setLoading(false)
    }
  }, [minN, validationId, tier])

  useEffect(() => {
    getMarketScoreboard()
      .then(setScoreboard)
      .catch(() => setScoreboard(null))
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const run = data?.run ?? null
  const cov = data?.source_coverage ?? {}
  const totals = run?.summary?.candidates_by_type ?? {}
  const markets = data?.by_market ?? []
  const situations = data?.synthetic_directions ?? []

  const bestMarket = markets[0]
  const hasValidation = validation?.validation != null
  const validationSeason = validation?.validation?.season_label
  const validationSeasons = (validation?.validations ?? []).map((v) => v.season_label).filter(Boolean)
  const oddsMode = run?.odds_mode ?? validation?.insight?.odds_mode

  return (
    <PatternInsightsShell>
      <header className="mb-5">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-bold tracking-tight">Pattern Insights</h1>
          {cov.season_label ? <span className="pi-chip">Run V2 · {cov.season_label}</span> : null}
          {validationSeasons.length ? (
            <span className="pi-chip">Verificato su {validationSeasons.join(' · ')}</span>
          ) : null}
          {oddsMode ? (
            <span className="pi-chip">{oddsMode === 'closing' ? 'Quote di chiusura' : 'Quote Run V2 (miste)'}</span>
          ) : null}
          {cov.leakage_ok ? <span className="pi-chip">Anti-leakage superato</span> : null}
        </div>
        <p className="mt-2 max-w-4xl text-xs leading-relaxed" style={{ color: 'var(--pi-muted)' }}>
          Ricerca esaustiva alla cieca sui dati Run V2: oltre ai pilastri Goal e Balance gia&apos;
          noti, il motore combina anche tiri, tiri in porta, corner, cartellini e severita&apos;
          storica dell&apos;arbitro — tutti valori pre-partita — su 17 mercati con quota e su una
          serie di situazioni di gioco senza quota storica.
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            Campione minimo per considerare un pattern:
          </span>
          {MIN_N_OPTIONS.map((v) => (
            <button
              key={v}
              type="button"
              className="pi-btn"
              style={
                v === minN
                  ? { borderColor: 'var(--pi-accent)', color: 'var(--pi-accent)' }
                  : undefined
              }
              onClick={() => setMinN(v)}
            >
              {v}+
            </button>
          ))}
          <span className="ml-1 text-[11px]" style={{ color: 'var(--pi-muted)' }}>
            (alzalo per togliere di mezzo i pattern piu&apos; fragili)
          </span>
        </div>

        <div
          className="mt-3 rounded-xl border px-3 py-2 text-[11px] leading-relaxed"
          style={{
            borderColor: 'rgba(251,191,36,0.35)',
            background: 'rgba(251,191,36,0.07)',
            color: '#f6d68a',
          }}
        >
          <strong>Stadio dell&apos;analisi:</strong>{' '}
          {hasValidation ? (
            <>
              pattern scoperti sul {cov.season_label ?? '—'} e verificati su{' '}
              {validationSeasons.length > 1
                ? `${validationSeasons.length} stagioni mai viste (${validationSeasons.join(', ')})`
                : `una sola stagione mai vista (${validationSeason})`}
              . Profitti misurati a quota di chiusura, prime divisioni e divisioni inferiori leggibili
              separatamente. Il 2025/26 resta sotto chiave per il test finale.
            </>
          ) : (
            <>
              Run V2 ha per ora una sola stagione ({cov.season_label ?? '—'}), quindi nessun pattern qui
              e&apos; ancora stato verificato su una stagione mai vista. Sono ipotesi da confermare, non
              pattern validati.
            </>
          )}
        </div>
      </header>

      {error && (
        <div
          className="mb-4 rounded-xl border px-3 py-2 text-xs"
          style={{ borderColor: 'rgba(248,113,113,0.4)', background: 'rgba(248,113,113,0.08)', color: '#fca5a5' }}
        >
          {error}
        </div>
      )}

      {loading && !data && (
        <div className="text-sm" style={{ color: 'var(--pi-muted)' }}>
          Caricamento analisi…
        </div>
      )}

      {!loading && run == null && !error && (
        <Section title="Nessuna analisi disponibile">
          <p className="text-xs" style={{ color: 'var(--pi-muted)' }}>
            Non risulta ancora nessuna analisi Pattern Insights completata su una Run V2.
          </p>
        </Section>
      )}

      {run && (
        <div className="space-y-4">
          {scoreboard && scoreboard.seasons.length > 0 && <MarketScoreboardBlock data={scoreboard} />}

          {hasValidation && validation && (
            <>
              <div className="pi-section flex flex-wrap items-center gap-4">
                <span className="text-[11px]" style={{ color: 'var(--pi-muted)' }}>
                  Stagione di verifica:
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {(validation.validations ?? []).map((v) => (
                    <button
                      key={v.id}
                      type="button"
                      className="pi-btn"
                      style={
                        v.id === validation.validation?.id
                          ? { borderColor: 'var(--pi-accent)', color: 'var(--pi-accent)' }
                          : undefined
                      }
                      onClick={() => setValidationId(v.id)}
                    >
                      {v.season_label}
                    </button>
                  ))}
                </div>
                <span className="text-[11px]" style={{ color: 'var(--pi-muted)' }}>
                  Campionati:
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {(validation.tiers ?? []).map((t) => (
                    <button
                      key={t.key}
                      type="button"
                      className="pi-btn"
                      style={t.key === tier ? { borderColor: 'var(--pi-accent)', color: 'var(--pi-accent)' } : undefined}
                      onClick={() => setTier(t.key)}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
                {loading && (
                  <span className="text-[11px]" style={{ color: 'var(--pi-muted)' }}>
                    aggiornamento…
                  </span>
                )}
              </div>
              <PersistenceBlock data={validation} />
              <ValidationHeadlineBlock data={validation} />
              <SampleProofBlock data={validation} />
              <ShrinkageBlock data={validation} />
              <MarketValidationBlock data={validation} />
              <SituationValidationBlock data={validation} />
              <div className="flex items-center gap-3 pt-2">
                <div className="h-px flex-1" style={{ background: 'var(--pi-border)' }} />
                <span className="pi-section-title">Scoperta · {cov.season_label ?? ''}</span>
                <div className="h-px flex-1" style={{ background: 'var(--pi-border)' }} />
              </div>
            </>
          )}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-6">
            <Kpi
              label="Pattern trovati"
              value={(run.summary?.candidates_total ?? 0).toLocaleString('it-IT')}
              hint={`${(totals.market ?? 0).toLocaleString('it-IT')} su mercati · ${(totals.synthetic ?? 0).toLocaleString('it-IT')} su situazioni`}
              tone="accent"
            />
            <Kpi
              label="Mercati coperti"
              value={String(markets.length)}
              hint="con quota storica, incluso primo tempo"
            />
            <Kpi
              label="Situazioni analizzate"
              value={String(situations.length)}
              hint="tiri, corner, cartellini"
            />
            <Kpi
              label="Partite analizzate"
              value={(cov.matches ?? 0).toLocaleString('it-IT')}
              hint={`${cov.competitions?.length ?? 0} campionati`}
            />
            <Kpi
              label="Violazioni anti-leakage"
              value={String(cov.leakage_violations ?? 0)}
              hint={`${(cov.matches_audited ?? 0).toLocaleString('it-IT')} partite verificate`}
              tone={cov.leakage_violations === 0 ? 'pos' : 'neg'}
            />
            <Kpi
              label="Miglior mercato"
              value={bestMarket ? `${(bestMarket.best_roi_pct ?? 0).toFixed(0)}%` : '—'}
              hint={bestMarket ? bestMarket.target_label : undefined}
              tone="warn"
            />
          </div>

          {markets.length > 0 && <MarketValueBlock markets={markets} />}

          {(data?.factor_frequency?.length ?? 0) > 0 && (
            <AnatomyBlock
              factors={data?.factor_frequency ?? []}
              complexity={data?.by_complexity ?? []}
            />
          )}

          {(data?.quality_scatter?.length ?? 0) > 0 && (
            <SignalNoiseBlock
              scatter={data?.quality_scatter ?? []}
              buckets={data?.sample_buckets ?? []}
            />
          )}

          {situations.length > 0 && <SituationsBlock situations={situations} />}

          {(cov.competitions?.length ?? 0) > 0 && <DataFoundationBlock coverage={cov} />}

          <PatternExplorer defaultMinN={minN} />

          <div className="pb-2 text-center text-[10px]" style={{ color: 'var(--pi-muted)' }}>
            Analisi #{run.id} su Run V2 #{run.run_v2_run_id}
            {run.completed_at
              ? ` · completata il ${new Date(run.completed_at).toLocaleString('it-IT')}`
              : ''}
            {cov.avg_ms_per_match ? ` · ${cov.avg_ms_per_match.toFixed(0)} ms per partita` : ''}
          </div>
        </div>
      )}
    </PatternInsightsShell>
  )
}
