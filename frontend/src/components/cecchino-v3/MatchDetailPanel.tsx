import { useEffect, useState } from 'react'
import {
  INDEX_CLASS_LABELS,
  MARKET_LABELS,
  RELIABILITY_LABELS,
  getMatchDetail,
  type FormaTeam,
  type IndexClass,
  type MatchDetail,
} from '../../lib/cecchinoV3MatchesApi'

const TEXT_MUTED = 'var(--pi-muted)'

function pct(v: number | null | undefined, d = 1): string {
  return v == null ? '—' : `${(v * 100).toFixed(d)}%`
}

function num(v: number | null | undefined, d = 2): string {
  return v == null ? '—' : v.toFixed(d)
}

function signed(v: number | null | undefined, d = 2): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(d)}`
}

export function ClassChip({ klass }: { klass: IndexClass | null | undefined }) {
  if (!klass) return <span style={{ color: TEXT_MUTED }}>n.d.</span>
  return (
    <span className="whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ border: '1px solid var(--pi-border)' }}>
      {INDEX_CLASS_LABELS[klass]}
    </span>
  )
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="pi-kpi">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider" style={{ color: TEXT_MUTED }}>
        {title}
      </div>
      {children}
    </div>
  )
}

function Line({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <span style={{ color: TEXT_MUTED }}>{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  )
}

function formLine(team: FormaTeam) {
  if (!team) return '—'
  return `gioco ${signed(team.gioco)} · risultati ${signed(team.risultati)}`
}

function specialistGoals(specialists: Record<string, unknown> | null, name: string): string {
  const s = specialists?.[name] as { home?: number; away?: number } | undefined
  if (!s || s.home == null || s.away == null) return '—'
  return `${s.home.toFixed(2)} – ${s.away.toFixed(2)}`
}

export function MatchDetailPanel({ labMatchId, onClose }: { labMatchId: number; onClose: () => void }) {
  const [detail, setDetail] = useState<MatchDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setDetail(null)
    setError(null)
    getMatchDetail(labMatchId)
      .then((d) => alive && setDetail(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : 'Errore caricamento partita'))
    return () => {
      alive = false
    }
  }, [labMatchId])

  const weights = (detail?.model.specialists?.weights ?? null) as Record<string, number> | null

  return (
    <div className="fixed inset-0 z-50 flex justify-end" style={{ background: 'rgba(4,8,16,0.6)' }} onClick={onClose}>
      <div
        className="pi-root h-full w-full max-w-4xl overflow-y-auto"
        style={{ borderRadius: 0 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            {detail ? (
              <>
                <div className="text-lg font-bold">
                  {detail.match.home_team} – {detail.match.away_team}
                </div>
                <div className="text-xs" style={{ color: TEXT_MUTED }}>
                  {detail.match.competition} · {detail.match.season_label} ·{' '}
                  {detail.match.kickoff_at ? new Date(detail.match.kickoff_at).toLocaleDateString('it-IT') : ''} ·
                  risultato finale {detail.result.ft}
                </div>
              </>
            ) : (
              <div className="text-sm">{error ?? 'Caricamento…'}</div>
            )}
          </div>
          <button type="button" className="pi-btn" onClick={onClose}>
            Chiudi
          </button>
        </div>

        {detail && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              <Card title="Affidabilita' della stima">
                <div className="text-2xl font-bold tabular-nums">{detail.indices.affidabilita.value.toFixed(0)}</div>
                <div className="mb-2 text-xs">{RELIABILITY_LABELS[detail.indices.affidabilita.class]}</div>
                <Line label="Conoscenza squadre" value={num(detail.indices.affidabilita.knowledge)} />
                <Line label="Accordo specialisti" value={num(detail.indices.affidabilita.agreement)} />
                <Line label="Squadra nuova/neopromossa" value={detail.indices.affidabilita.new_team ? 'si' : 'no'} />
                <Line label="Inizio stagione" value={detail.indices.affidabilita.early_season ? 'si' : 'no'} />
              </Card>
              <Card title="Equilibrio">
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold tabular-nums">{detail.indices.equilibrio.value.toFixed(0)}</span>
                  <ClassChip klass={detail.indices.equilibrio.class} />
                </div>
                <Line
                  label="Favorito"
                  value={
                    detail.indices.equilibrio.favourite === 'home'
                      ? detail.match.home_team
                      : detail.indices.equilibrio.favourite === 'away'
                        ? detail.match.away_team
                        : 'nessuno'
                  }
                />
                <Line label="Scarto 1-2" value={`${detail.indices.equilibrio.gap_pp.toFixed(1)} punti`} />
              </Card>
              <Card title="Credibilita' del pareggio">
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold tabular-nums">{pct(detail.indices.pareggio.prob)}</span>
                  <ClassChip klass={detail.indices.pareggio.class} />
                </div>
                <Line label="Pareggi nel campionato" value={pct(detail.indices.pareggio.league_draw_rate)} />
                <Line label="Scarto" value={detail.indices.pareggio.delta_pp == null ? '—' : `${signed(detail.indices.pareggio.delta_pp, 1)} punti`} />
              </Card>
              <Card title="Intensita' goal">
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold tabular-nums">{num(detail.indices.intensita_goal.total)}</span>
                  <ClassChip klass={detail.indices.intensita_goal.class} />
                </div>
                <Line label="Casa – ospite" value={`${num(detail.indices.intensita_goal.home)} – ${num(detail.indices.intensita_goal.away)}`} />
                <Line label="Media gol campionato" value={num(detail.indices.intensita_goal.league_goals_avg)} />
                <Line label="Over 2.5" value={pct(detail.indices.intensita_goal.p_over_2_5)} />
              </Card>
              <Card title="Forma (ultime 5, rispetto alle attese)">
                <Line label={detail.match.home_team} value={formLine(detail.indices.forma.home)} />
                <Line label={detail.match.away_team} value={formLine(detail.indices.forma.away)} />
                <div className="mt-1 text-[10px]" style={{ color: TEXT_MUTED }}>
                  Positivo = sopra le attese. Nel modello conta solo la forma di gioco (tiri).
                </div>
              </Card>
              <Card title="Calendario">
                <Line label="Riposo casa" value={detail.indices.calendario.rest_days_home ?? 'prima partita'} />
                <Line label="Riposo ospite" value={detail.indices.calendario.rest_days_away ?? 'prima partita'} />
                <Line label="Ultime 5 giornate" value={detail.indices.calendario.final_phase ? 'si' : 'no'} />
                <Line label="Partite giocate" value={`${detail.match.home_played} – ${detail.match.away_played}`} />
              </Card>
            </div>

            {detail.indices.disciplina && (
              <Card title="Disciplina (solo descrittiva)">
                <div className="grid grid-cols-1 gap-x-6 md:grid-cols-2">
                  <Line label="Falli casa / ospite" value={`${signed(detail.indices.disciplina.fouls_index_home)} / ${signed(detail.indices.disciplina.fouls_index_away)}`} />
                  <Line label="Cartellini casa / ospite" value={`${signed(detail.indices.disciplina.cards_index_home)} / ${signed(detail.indices.disciplina.cards_index_away)}`} />
                  <Line label="Arbitro" value={detail.indices.disciplina.referee ?? 'non disponibile'} />
                  <Line label="Gol nelle sue partite" value={detail.indices.disciplina.referee ? signed(detail.indices.disciplina.referee_goals_index) : '—'} />
                </div>
              </Card>
            )}

            <div className="pi-section">
              <div className="pi-section-title mb-2">Gli specialisti</div>
              <div className="pi-scroll">
                <table className="pi-table">
                  <thead>
                    <tr>
                      <th>Specialista</th>
                      <th>Gol attesi casa – ospite</th>
                      <th>Peso nell'orchestratore</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ['forza', 'Forza (gol)'],
                      ['sot', 'Gioco · tiri in porta'],
                      ['shots', 'Gioco · tiri'],
                    ].map(([key, label]) => (
                      <tr key={key}>
                        <td className="font-semibold">{label}</td>
                        <td className="tabular-nums">{specialistGoals(detail.model.specialists, key)}</td>
                        <td className="tabular-nums">{weights?.[key] != null ? weights[key].toFixed(3) : '—'}</td>
                      </tr>
                    ))}
                    <tr>
                      <td className="font-semibold">Orchestratore (finale)</td>
                      <td className="tabular-nums font-semibold">
                        {detail.model.lambda_home.toFixed(2)} – {detail.model.lambda_away.toFixed(2)}
                      </td>
                      <td style={{ color: TEXT_MUTED }}>con forma e calendario</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div className="pi-section">
              <div className="pi-section-title mb-2">Probabilita' dei 17 mercati</div>
              <div className="pi-scroll">
                <table className="pi-table">
                  <thead>
                    <tr>
                      <th>Mercato</th>
                      <th>Probabilita' V3</th>
                      <th>Quota V3</th>
                      <th>Quota chiusura</th>
                      <th>Probabilita' book</th>
                      <th>Esito</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.markets.map((m) => (
                      <tr key={m.market_key}>
                        <td className="font-semibold">{MARKET_LABELS[m.market_key] ?? m.market_key}</td>
                        <td className="tabular-nums">{pct(m.probability)}</td>
                        <td className="tabular-nums">{num(m.model_odds)}</td>
                        <td className="tabular-nums">{num(m.closing_odds)}</td>
                        <td className="tabular-nums">{pct(m.fair_probability)}</td>
                        <td>{m.won == null ? '—' : m.won ? '✓' : '✗'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-2 text-[10px]" style={{ color: TEXT_MUTED }}>
                Probabilita' book = quota di chiusura senza margine. L&apos;esito e&apos; mostrato solo per le partite gia&apos;
                giocate e non entra in nessun calcolo.
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
