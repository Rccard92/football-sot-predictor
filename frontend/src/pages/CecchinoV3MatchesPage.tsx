import { useCallback, useEffect, useState } from 'react'
import { PatternInsightsShell, Section } from '../components/pattern-insights/PatternInsightsShell'
import { ClassChip, MatchDetailPanel } from '../components/cecchino-v3/MatchDetailPanel'
import {
  INDEX_CLASS_LABELS,
  RELIABILITY_LABELS,
  getIndexRuns,
  getMatchFilters,
  listMatches,
  startIndexRun,
  type IndexClass,
  type IndexRun,
  type MatchListItem,
  type ReliabilityClass,
} from '../lib/cecchinoV3MatchesApi'

const PAGE_SIZE = 50
const TEXT_MUTED = 'var(--pi-muted)'
const COLOR_OK = '#1ea68f'
const COLOR_BAD = '#d95a57'

function pct(v: number | null | undefined): string {
  return v == null ? '—' : `${(v * 100).toFixed(0)}%`
}

function CoherenceBlock({ run }: { run: IndexRun }) {
  const checks = run.summary?.coherence_checks ?? []
  return (
    <Section
      title="Controlli di coerenza degli indici"
      note="Fissati prima del calcolo · stagioni di giudizio, partite idonee"
    >
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {checks.map((c) => (
          <div key={c.code} className="pi-tile">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-xs font-semibold">
                {c.code} · {c.label}
              </span>
              <span
                className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                style={{ border: `1px solid ${c.passed ? COLOR_OK : COLOR_BAD}` }}
              >
                <span style={{ color: c.passed ? COLOR_OK : COLOR_BAD }}>{c.passed ? '✓' : '✗'}</span>{' '}
                {c.passed ? 'Superato' : 'Non superato'}
              </span>
            </div>
            <table className="pi-table">
              <thead>
                <tr>
                  <th>Classe</th>
                  <th>Partite</th>
                  <th>{c.code === 'C1' ? 'Gol medi' : c.code === 'C4' ? 'Errore 1X2' : 'Frequenza'}</th>
                </tr>
              </thead>
              <tbody>
                {c.rows.map((r) => (
                  <tr key={r.class}>
                    <td>
                      {INDEX_CLASS_LABELS[r.class as IndexClass] ?? RELIABILITY_LABELS[r.class as ReliabilityClass] ?? r.class}
                    </td>
                    <td className="tabular-nums">{r.n.toLocaleString('it-IT')}</td>
                    <td className="tabular-nums">
                      {r.value == null ? '—' : c.code === 'C1' ? r.value.toFixed(2) : c.code === 'C4' ? r.value.toFixed(4) : `${(r.value * 100).toFixed(1)}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </Section>
  )
}

export function CecchinoV3MatchesPage() {
  const [runs, setRuns] = useState<{ latest: IndexRun | null; completed: IndexRun | null } | null>(null)
  const [filters, setFilters] = useState<{ competitions: string[]; seasons: string[] }>({ competitions: [], seasons: [] })
  const [competition, setCompetition] = useState('')
  const [season, setSeason] = useState('')
  const [team, setTeam] = useState('')
  const [teamInput, setTeamInput] = useState('')
  const [reliability, setReliability] = useState<ReliabilityClass | ''>('')
  const [page, setPage] = useState(0)
  const [items, setItems] = useState<MatchListItem[]>([])
  const [total, setTotal] = useState(0)
  const [detailId, setDetailId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const loadRuns = useCallback(async () => {
    try {
      const [r, f] = await Promise.all([getIndexRuns(), getMatchFilters()])
      setRuns(r)
      setFilters({ competitions: f.competitions, seasons: f.seasons })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Errore caricamento')
    }
  }, [])

  useEffect(() => {
    void loadRuns()
  }, [loadRuns])

  const active = runs?.latest?.status === 'pending' || runs?.latest?.status === 'running'
  useEffect(() => {
    if (!active) return
    const t = window.setInterval(() => void loadRuns(), 5000)
    return () => window.clearInterval(t)
  }, [active, loadRuns])

  useEffect(() => {
    if (!runs?.completed) return
    let alive = true
    listMatches({ competition, season, team, reliability, limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then((res) => {
        if (!alive) return
        setItems(res.items)
        setTotal(res.total)
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : 'Errore caricamento partite'))
    return () => {
      alive = false
    }
  }, [runs?.completed, competition, season, team, reliability, page])

  useEffect(() => {
    setPage(0)
  }, [competition, season, team, reliability])

  const start = async () => {
    setBusy(true)
    try {
      await startIndexRun()
      await loadRuns()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Avvio non riuscito')
    } finally {
      setBusy(false)
    }
  }

  const completed = runs?.completed ?? null

  return (
    <PatternInsightsShell>
      <header className="mb-5">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-bold tracking-tight">Cecchino V3 · Partita per partita</h1>
          {completed ? <span className="pi-chip">Modello di riferimento #{completed.source_run_id}</span> : null}
          {completed?.summary ? (
            <span className="pi-chip">{completed.summary.matches.toLocaleString('it-IT')} partite</span>
          ) : null}
        </div>
        <p className="mt-2 max-w-4xl text-xs leading-relaxed" style={{ color: TEXT_MUTED }}>
          Ogni partita letta a 360 gradi: probabilita&apos; dei 17 mercati, opinione di ogni specialista e indici di
          equilibrio, pareggio, intensita&apos; goal, forma, calendario, disciplina e affidabilita&apos; della stima. Tutti
          gli indici usano solo informazioni disponibili prima del calcio d&apos;inizio; il risultato e&apos; mostrato solo
          come verifica.
        </p>
      </header>

      {error && (
        <div
          className="mb-4 rounded-xl border px-3 py-2 text-xs"
          style={{ borderColor: 'rgba(248,113,113,0.4)', background: 'rgba(248,113,113,0.08)', color: '#fca5a5' }}
        >
          {error}
        </div>
      )}

      <div className="space-y-4">
        <Section title="Calcolo indici" note={runs?.latest ? `Ultimo calcolo #${runs.latest.id}` : 'Nessun calcolo'}>
          {active ? (
            <div className="text-xs">{runs?.latest?.current_step ?? 'In attesa di avvio'}…</div>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className="pi-btn" disabled={busy} onClick={() => void start()}>
                {completed ? 'Ricalcola indici' : 'Calcola indici'}
              </button>
              {runs?.latest?.status === 'failed' && (
                <span className="text-xs" style={{ color: '#fca5a5' }}>
                  Ultimo calcolo fallito: {runs.latest.error?.message ?? 'errore'}
                </span>
              )}
            </div>
          )}
        </Section>

        {completed && <CoherenceBlock run={completed} />}

        {completed && (
          <Section title="Partite" note={`${total.toLocaleString('it-IT')} partite con i filtri attuali · clicca per il dettaglio`}>
            <div className="mb-3 flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-[11px]" style={{ color: TEXT_MUTED }}>
                Campionato
                <select className="pi-select" value={competition} onChange={(e) => setCompetition(e.target.value)}>
                  <option value="">Tutti</option>
                  {filters.competitions.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-[11px]" style={{ color: TEXT_MUTED }}>
                Stagione
                <select className="pi-select" value={season} onChange={(e) => setSeason(e.target.value)}>
                  <option value="">Tutte</option>
                  {filters.seasons.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-[11px]" style={{ color: TEXT_MUTED }}>
                Squadra
                <input
                  className="pi-input w-44"
                  value={teamInput}
                  placeholder="es. Inter"
                  onChange={(e) => setTeamInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') setTeam(teamInput)
                  }}
                  onBlur={() => setTeam(teamInput)}
                />
              </label>
              <label className="flex flex-col gap-1 text-[11px]" style={{ color: TEXT_MUTED }}>
                Affidabilita'
                <select
                  className="pi-select"
                  value={reliability}
                  onChange={(e) => setReliability(e.target.value as ReliabilityClass | '')}
                >
                  <option value="">Tutte</option>
                  <option value="alta">Alta</option>
                  <option value="media">Media</option>
                  <option value="bassa">Bassa</option>
                </select>
              </label>
            </div>

            <div className="pi-scroll" style={{ maxHeight: 680 }}>
              <table className="pi-table">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Partita</th>
                    <th>Ris.</th>
                    <th>1</th>
                    <th>X</th>
                    <th>2</th>
                    <th>Over 2.5</th>
                    <th>Equilibrio</th>
                    <th>Pareggio</th>
                    <th>Intensita' goal</th>
                    <th>Affidabilita'</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((m) => (
                    <tr key={m.lab_match_id} style={{ cursor: 'pointer' }} onClick={() => setDetailId(m.lab_match_id)}>
                      <td className="whitespace-nowrap tabular-nums">
                        {m.kickoff_at ? new Date(m.kickoff_at).toLocaleDateString('it-IT') : '—'}
                      </td>
                      <td>
                        <div className="font-semibold">
                          {m.home_team} – {m.away_team}
                        </div>
                        <div className="text-[10px]" style={{ color: TEXT_MUTED }}>
                          {m.competition} · {m.season_label}
                          {m.phase === 'early' ? ' · inizio stagione' : m.phase === 'final' ? ' · ultime 5 giornate' : ''}
                        </div>
                      </td>
                      <td className="tabular-nums">{m.score ?? '—'}</td>
                      <td className="tabular-nums">{pct(m.prob_home)}</td>
                      <td className="tabular-nums">{pct(m.prob_draw)}</td>
                      <td className="tabular-nums">{pct(m.prob_away)}</td>
                      <td className="tabular-nums">{pct(m.prob_over_2_5)}</td>
                      <td>
                        <ClassChip klass={m.equilibrio.class} />
                      </td>
                      <td>
                        <ClassChip klass={m.pareggio.class} />
                      </td>
                      <td>
                        <ClassChip klass={m.intensita_goal.class} />
                      </td>
                      <td className="whitespace-nowrap tabular-nums">
                        {m.reliability == null ? '—' : m.reliability.toFixed(0)}{' '}
                        <span className="text-[10px]" style={{ color: TEXT_MUTED }}>
                          {m.reliability_class ? RELIABILITY_LABELS[m.reliability_class] : ''}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-3 flex items-center justify-between text-[11px]" style={{ color: TEXT_MUTED }}>
              <button type="button" className="pi-btn" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
                ← Precedenti
              </button>
              <span className="tabular-nums">
                {total === 0 ? 0 : page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} di{' '}
                {total.toLocaleString('it-IT')}
              </span>
              <button
                type="button"
                className="pi-btn"
                disabled={(page + 1) * PAGE_SIZE >= total}
                onClick={() => setPage((p) => p + 1)}
              >
                Successivi →
              </button>
            </div>
          </Section>
        )}
      </div>

      {detailId != null && <MatchDetailPanel labMatchId={detailId} onClose={() => setDetailId(null)} />}
    </PatternInsightsShell>
  )
}
