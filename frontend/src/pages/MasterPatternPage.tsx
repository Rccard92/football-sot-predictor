import { useEffect, useState } from 'react'
import { PatternInsightsShell, Section } from '../components/pattern-insights/PatternInsightsShell'
import {
  MARKET_LABELS,
  SEASONS,
  getMasterPatternDetail,
  getOverview,
  listMasterPatterns,
  startBuild,
  type DetailSeason,
  type MasterPattern,
  type ModelCode,
  type Overview,
  type SeasonStats,
  type TargetType,
} from '../lib/masterPatternApi'

const PAGE_SIZE = 50
const TEXT_MUTED = 'var(--pi-muted)'
const COLOR_POS = 'var(--pi-pos)'
const COLOR_NEG = 'var(--pi-neg)'
const MODELS: ModelCode[] = ['V2', 'V2.5', 'V3']

const MODEL_DESCRIPTIONS: Record<ModelCode, string> = {
  V2: 'Cecchino V2 · RUN V2',
  'V2.5': 'V2 con moduli migliorati · in costruzione',
  V3: 'Agenti e orchestratore',
}

function num(v: number | null | undefined, d = 2): string {
  return v == null ? '—' : v.toLocaleString('it-IT', { minimumFractionDigits: d, maximumFractionDigits: d })
}

function signed(v: number | null | undefined, d = 1, suffix = '%'): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${num(v, d)}${suffix}`
}

function shortSeason(s: string): string {
  return `${s.slice(2, 4)}/${s.slice(7, 9)}`
}

function marketName(p: MasterPattern): string {
  return p.target_type === 'market' ? (MARKET_LABELS[p.target_key] ?? p.market_label) : p.market_label
}

function SeasonCell({ s, targetType }: { s: SeasonStats | undefined; targetType: TargetType }) {
  if (!s || !s.n) return <td style={{ color: TEXT_MUTED }}>—</td>
  const main = targetType === 'market' ? signed(s.roi_pct) : `${num(s.win_rate_pct, 0)}%`
  const tone = targetType === 'market' ? (s.roi_pct ?? 0) : (s.deviation_pct ?? 0)
  return (
    <td className="whitespace-nowrap tabular-nums">
      <span style={{ color: tone > 0 ? COLOR_POS : COLOR_NEG }}>{main}</span>
      <span className="text-[10px]" style={{ color: TEXT_MUTED }}>
        {' '}
        · {s.n}
      </span>
    </td>
  )
}

function ModelCards({
  overview,
  model,
  onSelect,
}: {
  overview: Overview | null
  model: ModelCode
  onSelect: (m: ModelCode) => void
}) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {MODELS.map((code) => {
        const info = overview?.models.find((m) => m.model === code)
        const summary = info?.completed?.summary
        const selected = code === model
        const disabled = !info?.available
        return (
          <button
            key={code}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(code)}
            className="pi-kpi text-left"
            style={{
              borderColor: selected ? 'var(--pi-accent)' : undefined,
              opacity: disabled ? 0.5 : 1,
              cursor: disabled ? 'not-allowed' : 'pointer',
            }}
          >
            <div className="text-lg font-bold">{code}</div>
            <div className="text-[11px]" style={{ color: TEXT_MUTED }}>
              {MODEL_DESCRIPTIONS[code]}
            </div>
            <div className="mt-2 text-xs tabular-nums">
              {disabled
                ? 'Disponibile quando la V2.5 sara pronta'
                : summary
                  ? `${summary.tally.market.winners} pattern con quota · ${summary.tally.synthetic.winners} senza quota`
                  : 'Non ancora calcolato'}
            </div>
          </button>
        )
      })}
    </div>
  )
}

function DetailPanel({ id, onClose }: { id: number; onClose: () => void }) {
  const [data, setData] = useState<{ pattern: MasterPattern; seasons: DetailSeason[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [season, setSeason] = useState<string>(SEASONS[SEASONS.length - 1])

  useEffect(() => {
    let alive = true
    getMasterPatternDetail(id)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : 'Errore caricamento dettaglio'))
    return () => {
      alive = false
    }
  }, [id])

  const block = data?.seasons.find((s) => s.season_label === season)
  const isMarket = data?.pattern.target_type === 'market'

  return (
    <div className="fixed inset-0 z-50 flex justify-end" style={{ background: 'rgba(4,8,16,0.6)' }} onClick={onClose}>
      <div className="pi-root h-full w-full max-w-5xl overflow-y-auto" style={{ borderRadius: 0 }} onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            {data ? (
              <>
                <div className="text-lg font-bold">
                  {data.pattern.model} · {marketName(data.pattern)}
                </div>
                <div className="text-xs">{data.pattern.conditions_text}</div>
                <div className="text-[10px]" style={{ color: TEXT_MUTED }}>
                  Versione motore: {data.pattern.engine_version}
                </div>
              </>
            ) : (
              <div className="text-sm">{error ?? 'Caricamento partite…'}</div>
            )}
          </div>
          <button type="button" className="pi-btn" onClick={onClose}>
            Chiudi
          </button>
        </div>

        {data && (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {SEASONS.map((s) => {
                const st = data.pattern.seasons[s]
                return (
                  <button
                    key={s}
                    type="button"
                    className="pi-btn"
                    style={s === season ? { borderColor: 'var(--pi-accent)' } : undefined}
                    onClick={() => setSeason(s)}
                  >
                    {s}
                    {s === SEASONS[0] ? ' · scoperta' : ''}
                    {st?.n ? ` · ${st.n}` : ''}
                  </button>
                )
              })}
            </div>

            {block && (
              <>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <div className="pi-kpi">
                    <div className="text-[10px] uppercase" style={{ color: TEXT_MUTED }}>Partite</div>
                    <div className="text-xl font-bold tabular-nums">{block.overall.n}</div>
                  </div>
                  <div className="pi-kpi">
                    <div className="text-[10px] uppercase" style={{ color: TEXT_MUTED }}>Vinte / perse</div>
                    <div className="text-xl font-bold tabular-nums">
                      {block.overall.wins} / {block.overall.n - block.overall.wins}
                    </div>
                  </div>
                  {isMarket ? (
                    <>
                      <div className="pi-kpi">
                        <div className="text-[10px] uppercase" style={{ color: TEXT_MUTED }}>Quota media</div>
                        <div className="text-xl font-bold tabular-nums">{num(block.overall.avg_quota)}</div>
                      </div>
                      <div className="pi-kpi">
                        <div className="text-[10px] uppercase" style={{ color: TEXT_MUTED }}>Profitto · ROI</div>
                        <div className="text-xl font-bold tabular-nums">
                          {signed(block.overall.profit_units, 2, 'u')} · {signed(block.overall.roi_pct)}
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="pi-kpi">
                        <div className="text-[10px] uppercase" style={{ color: TEXT_MUTED }}>Frequenza</div>
                        <div className="text-xl font-bold tabular-nums">{num(block.overall.win_rate_pct, 1)}%</div>
                      </div>
                      <div className="pi-kpi">
                        <div className="text-[10px] uppercase" style={{ color: TEXT_MUTED }}>Media campionato · scarto</div>
                        <div className="text-xl font-bold tabular-nums">
                          {num(block.overall.baseline_win_rate_pct, 1)}% · {signed(block.overall.deviation_pct)}
                        </div>
                      </div>
                    </>
                  )}
                </div>

                <Section title="Per campionato">
                  <div className="pi-scroll">
                    <table className="pi-table">
                      <thead>
                        <tr>
                          <th>Campionato</th>
                          <th>Partite</th>
                          <th>Vinte</th>
                          <th>% vinte</th>
                          {isMarket && <th>Quota media</th>}
                          {isMarket && <th>Profitto</th>}
                          {isMarket && <th>ROI</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {block.by_competition.map((c) => (
                          <tr key={c.competition}>
                            <td className="font-semibold">{c.competition}</td>
                            <td className="tabular-nums">{c.n}</td>
                            <td className="tabular-nums">{c.wins}</td>
                            <td className="tabular-nums">{num(c.win_rate_pct, 1)}%</td>
                            {isMarket && <td className="tabular-nums">{num(c.avg_quota)}</td>}
                            {isMarket && <td className="tabular-nums">{signed(c.profit_units, 2, 'u')}</td>}
                            {isMarket && <td className="tabular-nums">{signed(c.roi_pct)}</td>}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Section>

                <Section title="Partite" note={`${block.matches_total} partite${block.matches.length < block.matches_total ? ` · prime ${block.matches.length}` : ''}`}>
                  <div className="pi-scroll" style={{ maxHeight: 520 }}>
                    <table className="pi-table">
                      <thead>
                        <tr>
                          <th>Data</th>
                          <th>Campionato</th>
                          <th>Partita</th>
                          {isMarket ? <th>Quota</th> : <th>Valore reale</th>}
                          <th>Esito</th>
                          {isMarket && <th>Profitto</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {block.matches.map((m) => (
                          <tr key={m.lab_match_id}>
                            <td className="whitespace-nowrap tabular-nums">
                              {m.match_date ? new Date(m.match_date).toLocaleDateString('it-IT') : '—'}
                            </td>
                            <td>{m.competition}</td>
                            <td>
                              {m.home_team} – {m.away_team}
                            </td>
                            <td className="tabular-nums">{isMarket ? num(m.quota) : num(m.actual_value, 0)}</td>
                            <td>
                              {m.won == null ? '—' : <span style={{ color: m.won ? COLOR_POS : COLOR_NEG }}>{m.won ? '✓' : '✗'}</span>}
                            </td>
                            {isMarket && <td className="tabular-nums">{signed(m.profit, 2, 'u')}</td>}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Section>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export function MasterPatternPage() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [model, setModel] = useState<ModelCode>('V2')
  const [targetType, setTargetType] = useState<TargetType>('market')
  const [market, setMarket] = useState('')
  const [minMatches, setMinMatches] = useState('')
  const [minQuota, setMinQuota] = useState('')
  const [maxQuota, setMaxQuota] = useState('')
  const [sort, setSort] = useState('')
  const [page, setPage] = useState(0)
  const [data, setData] = useState<Awaited<ReturnType<typeof listMasterPatterns>> | null>(null)
  const [detailId, setDetailId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    let alive = true
    getOverview()
      .then((o) => alive && setOverview(o))
      .catch((e) => alive && setError(e instanceof Error ? e.message : 'Errore caricamento'))
    return () => {
      alive = false
    }
  }, [refresh])

  const modelInfo = overview?.models.find((m) => m.model === model)
  const running = modelInfo?.latest?.status === 'pending' || modelInfo?.latest?.status === 'running'

  useEffect(() => {
    if (!running) return
    const t = window.setInterval(() => setRefresh((x) => x + 1), 10000)
    return () => window.clearInterval(t)
  }, [running])

  useEffect(() => {
    let alive = true
    listMasterPatterns({
      model,
      targetType,
      market: market || undefined,
      minMatches: minMatches ? Number(minMatches) : undefined,
      minQuota: minQuota ? Number(minQuota.replace(',', '.')) : undefined,
      maxQuota: maxQuota ? Number(maxQuota.replace(',', '.')) : undefined,
      sort,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    })
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : 'Errore caricamento pattern'))
    return () => {
      alive = false
    }
  }, [model, targetType, market, minMatches, minQuota, maxQuota, sort, page, refresh, modelInfo?.completed?.id])

  const resetPage = () => setPage(0)
  const tally = modelInfo?.completed?.summary?.tally[targetType]
  const isMarket = targetType === 'market'

  const build = async () => {
    try {
      await startBuild(model)
      setRefresh((x) => x + 1)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Avvio non riuscito')
    }
  }

  return (
    <PatternInsightsShell>
      <header className="mb-5">
        <h1 className="text-xl font-bold tracking-tight">Master Pattern</h1>
        <p className="mt-1 text-xs" style={{ color: TEXT_MUTED }}>
          Pattern vincenti in tutte e 4 le stagioni 2022/23 – 2025/26 (almeno 20 partite per stagione). Scoperta sul 2021/22.
        </p>
      </header>

      {error && (
        <div className="mb-4 text-xs" style={{ color: '#fca5a5' }}>
          {error}
        </div>
      )}

      <div className="space-y-4">
        <ModelCards
          overview={overview}
          model={model}
          onSelect={(m) => {
            setModel(m)
            setMarket('')
            resetPage()
          }}
        />

        <div className="flex flex-wrap items-center gap-2">
          {(
            [
              ['market', 'Mercati con quota'],
              ['synthetic', 'Mercati senza quota'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className="pi-btn"
              style={key === targetType ? { borderColor: 'var(--pi-accent)' } : undefined}
              onClick={() => {
                setTargetType(key)
                setMarket('')
                setSort('')
                resetPage()
              }}
            >
              {label}
            </button>
          ))}
          {modelInfo?.available && (
            <span className="ml-auto text-[11px]" style={{ color: TEXT_MUTED }}>
              {running ? (
                `Calcolo in corso: ${modelInfo.latest?.current_step ?? 'in attesa'}…`
              ) : (
                <>
                  {modelInfo.completed?.completed_at
                    ? `Aggiornato il ${new Date(modelInfo.completed.completed_at).toLocaleString('it-IT')}`
                    : 'Mai calcolato'}{' '}
                  <button type="button" className="pi-btn ml-2" onClick={() => void build()}>
                    {modelInfo.completed ? 'Ricalcola' : 'Calcola'}
                  </button>
                </>
              )}
            </span>
          )}
        </div>

        {tally && (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="pi-kpi">
              <div className="text-[10px] uppercase" style={{ color: TEXT_MUTED }}>Pattern verificati in 4 stagioni</div>
              <div className="text-xl font-bold tabular-nums">{tally.tested_all_seasons.toLocaleString('it-IT')}</div>
            </div>
            <div className="pi-kpi">
              <div className="text-[10px] uppercase" style={{ color: TEXT_MUTED }}>Vincenti 4 su 4</div>
              <div className="text-xl font-bold tabular-nums">{tally.winners.toLocaleString('it-IT')}</div>
            </div>
            <div className="pi-kpi">
              <div className="text-[10px] uppercase" style={{ color: TEXT_MUTED }}>Attesi per puro caso</div>
              <div className="text-xl font-bold tabular-nums">{num(tally.expected_by_chance, 1)}</div>
            </div>
            <div className="pi-kpi">
              <div className="text-[10px] uppercase" style={{ color: TEXT_MUTED }}>Vincenti rispetto al caso</div>
              <div className="text-xl font-bold tabular-nums">{tally.lift == null ? '—' : `${num(tally.lift, 2)}×`}</div>
            </div>
          </div>
        )}

        <Section title={isMarket ? 'Pattern vincenti con quota' : 'Pattern vincenti senza quota'} note={`${data?.total ?? 0} pattern`}>
          <div className="mb-3 flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-[11px]" style={{ color: TEXT_MUTED }}>
              Mercato
              <select
                className="pi-select"
                value={market}
                onChange={(e) => {
                  setMarket(e.target.value)
                  resetPage()
                }}
              >
                <option value="">Tutti</option>
                {(data?.markets ?? []).map((m) => (
                  <option key={m.key} value={m.key}>
                    {(isMarket ? MARKET_LABELS[m.key] : m.key) ?? m.key} ({m.count})
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-[11px]" style={{ color: TEXT_MUTED }}>
              Partite minime
              <input
                className="pi-input w-24"
                inputMode="numeric"
                value={minMatches}
                onChange={(e) => {
                  setMinMatches(e.target.value.replace(/\D/g, ''))
                  resetPage()
                }}
              />
            </label>
            {isMarket && (
              <>
                <label className="flex flex-col gap-1 text-[11px]" style={{ color: TEXT_MUTED }}>
                  Quota media da
                  <input
                    className="pi-input w-20"
                    inputMode="decimal"
                    value={minQuota}
                    onChange={(e) => {
                      setMinQuota(e.target.value)
                      resetPage()
                    }}
                  />
                </label>
                <label className="flex flex-col gap-1 text-[11px]" style={{ color: TEXT_MUTED }}>
                  a
                  <input
                    className="pi-input w-20"
                    inputMode="decimal"
                    value={maxQuota}
                    onChange={(e) => {
                      setMaxQuota(e.target.value)
                      resetPage()
                    }}
                  />
                </label>
              </>
            )}
            <label className="flex flex-col gap-1 text-[11px]" style={{ color: TEXT_MUTED }}>
              Ordina per
              <select
                className="pi-select"
                value={sort}
                onChange={(e) => {
                  setSort(e.target.value)
                  resetPage()
                }}
              >
                {isMarket ? (
                  <>
                    <option value="">Profitto</option>
                    <option value="roi">ROI</option>
                    <option value="partite">Partite</option>
                  </>
                ) : (
                  <>
                    <option value="">Scarto dalla media</option>
                    <option value="frequenza">Frequenza</option>
                    <option value="partite">Partite</option>
                  </>
                )}
              </select>
            </label>
          </div>

          {!data?.build ? (
            <div className="text-xs" style={{ color: TEXT_MUTED }}>
              {modelInfo?.available ? 'Nessun calcolo disponibile per questo modello.' : 'Modello in costruzione.'}
            </div>
          ) : (
            <>
              <div className="pi-scroll" style={{ maxHeight: 720 }}>
                <table className="pi-table">
                  <thead>
                    <tr>
                      <th>Mercato</th>
                      <th>Condizioni</th>
                      {SEASONS.map((s) => (
                        <th key={s}>{shortSeason(s)}</th>
                      ))}
                      <th>Partite</th>
                      <th>Vinte</th>
                      <th>Perse</th>
                      <th>% vinte</th>
                      {isMarket ? (
                        <>
                          <th>Quota media</th>
                          <th>Profitto</th>
                          <th>ROI</th>
                        </>
                      ) : (
                        <th>Scarto medio</th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((p) => (
                      <tr key={p.id} style={{ cursor: 'pointer' }} onClick={() => setDetailId(p.id)}>
                        <td className="whitespace-nowrap font-semibold">{marketName(p)}</td>
                        <td className="min-w-[260px]">{p.conditions_text}</td>
                        {SEASONS.map((s) => (
                          <SeasonCell key={s} s={p.seasons[s]} targetType={targetType} />
                        ))}
                        <td className="tabular-nums">{p.total_n.toLocaleString('it-IT')}</td>
                        <td className="tabular-nums">{p.total_wins.toLocaleString('it-IT')}</td>
                        <td className="tabular-nums">{p.total_losses.toLocaleString('it-IT')}</td>
                        <td className="tabular-nums">{num(p.win_rate_pct, 1)}%</td>
                        {isMarket ? (
                          <>
                            <td className="tabular-nums">{num(p.avg_quota)}</td>
                            <td className="tabular-nums font-semibold">{signed(p.profit_units, 2, 'u')}</td>
                            <td className="tabular-nums">{signed(p.roi_pct)}</td>
                          </>
                        ) : (
                          <td className="tabular-nums font-semibold">{signed(p.avg_deviation_pct)}</td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-3 flex items-center justify-between text-[11px]" style={{ color: TEXT_MUTED }}>
                <button type="button" className="pi-btn" disabled={page === 0} onClick={() => setPage((x) => Math.max(0, x - 1))}>
                  ← Precedenti
                </button>
                <span className="tabular-nums">
                  {data.total === 0 ? 0 : page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, data.total)} di {data.total}
                </span>
                <button
                  type="button"
                  className="pi-btn"
                  disabled={(page + 1) * PAGE_SIZE >= data.total}
                  onClick={() => setPage((x) => x + 1)}
                >
                  Successivi →
                </button>
              </div>
            </>
          )}
        </Section>
      </div>

      {detailId != null && <DetailPanel id={detailId} onClose={() => setDetailId(null)} />}
    </PatternInsightsShell>
  )
}
