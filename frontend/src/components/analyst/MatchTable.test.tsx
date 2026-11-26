/** @vitest-environment jsdom */
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { EvaluatedSign, MatchTableResponse, MatchTableRow, TableGame } from '../../lib/analystJournalApi'
import { MatchTable } from './MatchTable'

/** Gara di prova del capitolato di Giovanni (24/11/2026): Juve Stabia – Catanzaro, quote Bet365 delle 06:03. */
const g = (ft: string, ht: string, ftOutcome: 'V' | 'N' | 'P', htOutcome: 'V' | 'N' | 'P', opponent: string, rank: number, level: 'strong' | 'even' | 'weak'): TableGame => ({
  date: '2026-11-01',
  opponent,
  opponent_rank: rank,
  home: true,
  ft,
  ht,
  ft_outcome: ftOutcome,
  ht_outcome: htOutcome,
  bold_ft: false,
  bold_ht: false,
  diff: level === 'strong' ? 0.4 : level === 'weak' ? -0.4 : 0.1,
  level,
})

const juve = [
  g('0-3', '0-1', 'P', 'P', 'Pisa', 5, 'even'),
  g('1-1', '0-1', 'N', 'P', 'Cesena', 8, 'strong'),
  g('3-0', '1-0', 'V', 'V', 'Sudtirol', 7, 'strong'),
  g('0-1', '0-0', 'P', 'N', 'Verona', 9, 'weak'),
  g('1-0', '1-0', 'V', 'V', 'Arezzo', 16, 'even'),
]

const sign = (key: string, label: string, group: string, q: number, qc: number, state: EvaluatedSign['state'], reason?: string): EvaluatedSign => ({
  key,
  label,
  group,
  q,
  q_at: '2026-11-24T05:03:00+00:00',
  q_source: 'morning',
  morning: q,
  change: null,
  prob_book: 1 / q,
  quota_cecchino: qc,
  prob_cecchino: 1 / qc,
  value: q / qc - 1,
  state,
  reasons: reason ? [{ code: reason.startsWith('R1') ? 'r1' : 'x', rule: 'R1', text: reason, short: 'R1' }] : [],
  notes: [],
})

const row: MatchTableRow = {
  today_fixture_id: 7,
  scan_date: '2099-11-24',
  kickoff: '2099-11-24T18:00:00+00:00',
  country: 'Italy',
  league: 'Serie B',
  home_team: 'Juve Stabia',
  away_team: 'Catanzaro',
  eligible: true,
  balance: { index: 39.4, class: 'Squilibrio' },
  blocks: {
    forma_casa: { games: 5, enough: true, points: 7, max_points: 15, scored: 5, conceded: 5, ht_games: 5, ht_scored: 2, ht_conceded: 2, team_rank: 12, results: juve, strength: 0.1, strength_level: 'even' },
    forma_fuori: { games: 2, enough: false },
    forma_totale_casa: { games: 2, enough: false },
    forma_totale_fuori: { games: 1, enough: false },
  },
  yellows: { home: { games: 5, available: true, own: 8, opponents: 7, own_avg: 1.6, opponents_avg: 1.4 }, away: { games: 5, available: true, own: 9, opponents: 6, own_avg: 1.8, opponents_avg: 1.2 } },
  standings_complete: true,
  home_rank: 12,
  away_rank: 20,
  quotes: [
    { key: 'HOME', label: '1', group: 'Fisse', quota: 1.9 },
    { key: 'DRAW', label: 'X', group: 'Fisse', quota: 3.5 },
    { key: 'AWAY', label: '2', group: 'Fisse', quota: 3.9 },
    { key: 'OVER_2_5', label: 'Over 2.5', group: 'Over', quota: 1.75 },
  ],
  match_type: 'Scala 1X',
  my_note: '',
  other_notes: [],
  started: false,
  editable: true,
  odds_checked_at: '2099-11-24T05:03:00+00:00',
  goal_form: { goals: 22, games: 10, avg: 2.2, alert: false, threshold: 2.7, markets: [] },
  pt_form: { goals: 7, games: 10, avg: 0.7, alert: false, threshold: 1.5, markets: [], x_pt: 5, u15_pt: 9, x_pct: 50, u15_pct: 90 },
  reliability: { level: 'yellow', red: [], yellow: ['Quote lette più di 12 ore prima della gara'] },
  squads: {
    home: { lineups_known: 10, habitual: null, injured: [], missing_starters: 0, probable: null, injuries_known: false, history: [{ date: '2026-11-01', opponent: 'Pisa', rosa: null, home: true, ft: '0-3', ht: '0-1', ft_outcome: 'P', opponent_rank: 5, level: 'even' }] },
    away: { lineups_known: 10, habitual: null, injured: [], missing_starters: 0, probable: null, injuries_known: false, history: [] },
  },
  evaluation: {
    signs: [
      sign('DRAW', 'X', 'ESITO FINALE', 3.5, 3.75, 'playable'),
      sign('DRAW_PT', 'X PT', 'PRIMO TEMPO', 2.3, 2.09, 'playable'),
      sign('OVER_2_5', 'Over 2.5', 'UNDER / OVER', 1.75, 2.26, 'blocked', 'R1 · book 23% sotto il Cecchino'),
      sign('OVER_PT_0_5', 'Over PT 0.5', 'GOL PRIMO TEMPO', 1.3, 1.56, 'blocked', 'R1 · book 17% sotto il Cecchino'),
      { ...sign('HOME', '1', 'ESITO FINALE', 1.9, 2.0, 'out'), reasons: [{ code: 'sopra_massimo', text: 'Oltre la quota massima 1,55' }] },
    ],
    counts: { playable: 2, check: 0, blocked: 2, out: 1 },
    odds_at: '2099-11-24T05:03:00+00:00',
    second_read: { done: false, at: null, due: '2099-11-24T16:45:00+00:00' },
  },
  computed_at: '2099-11-24T05:10:00+00:00',
  weather: {
    status: 'ok',
    fetched_at: '2099-11-24T06:00:00+00:00',
    kickoff: { at: '2099-11-24T18:00:00+00:00', temperature: 14, precipitation: 0, wind: 12, code: 3, icon: '☁', text: 'nuvoloso' },
    hours: [{ at: '2099-11-24T18:00:00+00:00', temperature: 14, precipitation: 0, wind: 12, code: 3, icon: '☁', text: 'nuvoloso' }],
  },
  close_games: null,
  season_end: null,
}

const response: MatchTableResponse = {
  day: '2099-11-24',
  total: 1,
  total_day: 1,
  page: 1,
  page_size: 50,
  countries: ['Italy'],
  leagues: ['Serie B'],
  match_types: ['Scala 1X'],
  odds_at: '2099-11-24T05:03:00+00:00',
  can_write: true,
  rows: [row],
}

vi.mock('../../contexts/AuthContext', () => ({ useOptionalAuth: () => ({ me: { id: 1 }, canSee: () => true }) }))
vi.mock('../../lib/analystJournalApi', async (orig) => ({
  ...(await orig<typeof import('../../lib/analystJournalApi')>()),
  getMatchTable: vi.fn(() => Promise.resolve(response)),
  getMatchStandings: vi.fn(() =>
    Promise.resolve({
      today_fixture_id: 7,
      league: 'Serie B',
      country: 'Italy',
      home_team_id: 1,
      away_team_id: 2,
      games: 3,
      complete: true,
      tables: {
        total: [
          { rank: 1, team_id: 2, team: 'Catanzaro', played: 2, won: 2, drawn: 0, lost: 0, gf: 4, ga: 1, gd: 3, points: 6 },
          { rank: 2, team_id: 1, team: 'Juve Stabia', played: 2, won: 1, drawn: 0, lost: 1, gf: 3, ga: 3, gd: 0, points: 3 },
        ],
        home: [{ rank: 1, team_id: 1, team: 'Juve Stabia', played: 1, won: 1, drawn: 0, lost: 0, gf: 2, ga: 0, gd: 2, points: 3 }],
        away: [{ rank: 1, team_id: 2, team: 'Catanzaro', played: 1, won: 1, drawn: 0, lost: 0, gf: 2, ga: 0, gd: 2, points: 3 }],
      },
      recent: { '1': { total: [], home: [], away: [] }, '2': { total: [], home: [], away: [] } },
    }),
  ),
  saveMatchNote: vi.fn(() => Promise.resolve({ today_fixture_id: 7, note: 'x' })),
}))

async function detail() {
  render(<MatchTable />)
  await screen.findAllByText('Juve Stabia')
  return screen.getByRole('heading', { level: 2 }).closest('aside')!
}

describe('MatchTable · capitolato del 24/11/2026', () => {
  afterEach(cleanup)

  it('lista: segni ✓ ✕, quote 1X2, tipo partita con indice, nessuna cifra ±forza (modifica 14)', async () => {
    render(<MatchTable />)
    await screen.findAllByText('Juve Stabia')
    const list = screen.getAllByRole('button', { pressed: true })[0]
    expect(within(list).getByText('2 ✓')).toBeTruthy()
    expect(within(list).getByText('2 ✕')).toBeTruthy()
    expect(within(list).getByText('1,90 · 3,50 · 3,90')).toBeTruthy()
    expect(within(list).getByText('Scala 1X')).toBeTruthy()
    expect(within(list).getByText('39')).toBeTruthy()
    expect(within(list).queryByText('+0,10')).toBeNull()
    expect(screen.getByText('quote delle 06:03')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Solo con segni giocabili' })).toBeTruthy()
  })

  it('testata: tipo partita grigio, equilibrio in arancio, pulsante a tre stati (modifiche 15 e 16)', async () => {
    const d = await detail()
    expect(within(d).getByText('1,90 · 3,50 · 3,90')).toBeTruthy()
    expect(within(d).getByText('Squilibrio · 39')).toBeTruthy()
    expect(within(d).queryByText(/non concordano/)).toBeNull()
    const save = within(d).getByTestId('salva-giocata')
    expect(save.textContent).toContain('+ Salva giocata · scegli un segno')
    expect((save as HTMLButtonElement).disabled).toBe(true)
    await userEvent.click(within(d).getByLabelText('Scegli X'))
    expect(within(d).getByTestId('salva-giocata').textContent).toContain('+ Salva giocata · X a 3,50')
    await userEvent.click(within(d).getByLabelText('Scegli Over 2.5 (bloccato)'))
    expect(within(d).getByTestId('salva-giocata').textContent).toContain('🔒 Over 2,5 bloccato · R1')
  })

  it('cinque riquadri e «Segni · decidi qui» (modifiche 2, 3 e 5)', async () => {
    const d = await detail()
    expect(within(d).getByText('gialla')).toBeTruthy()
    expect(within(d).getByText('Quote lette più di 12 ore prima della gara')).toBeTruthy()
    expect(within(d).getByText(/quote 06:03 · 2ª lettura 17:45/)).toBeTruthy()
    expect(within(d).getByText('n.d. · n.d.')).toBeTruthy()
    expect(within(d).getByText('ultime 10 gare · nessun avviso')).toBeTruthy()
    expect(within(d).getAllByText(/14°C/).length).toBeGreaterThan(0)
    // tabella dei segni: gruppi, bloccati con il motivo, fuori fascia nascosti
    expect(within(d).getByText('ESITO FINALE')).toBeTruthy()
    expect(within(d).getByText('BLOCCATI')).toBeTruthy()
    expect(within(d).getByText('R1 · book 23% sotto il Cecchino')).toBeTruthy()
    expect(within(d).getByText('−7%')).toBeTruthy()
    expect(within(d).getByText('+10%')).toBeTruthy()
    expect(within(d).queryByText('Oltre la quota massima 1,55')).toBeNull()
    await userEvent.click(within(d).getByText(/altri 1 segni fuori fascia o da evitare/))
    expect(within(d).getByText('Oltre la quota massima 1,55')).toBeTruthy()
    expect(within(d).getByText(/Quote Bet365 delle 06:03/)).toBeTruthy()
  })

  it('forma: PT e finale, cornice quando cambia, forza a parole, punti contro le avversarie (modifica 6)', async () => {
    const d = await detail()
    expect(within(d).getByText('in casa · 7 punti su 15')).toBeTruthy()
    const cesenaPt = within(d).getAllByTitle(/PT 0-1/)[1]
    expect(cesenaPt.style.outline).toContain('dashed')
    const pisaPt = within(d).getAllByTitle(/PT 0-1/)[0]
    expect(pisaPt.style.outline).toBe('')
    expect(within(d).getAllByText('▲ più forte').length).toBe(2)
    expect(within(d).getAllByText('▼ più debole').length).toBe(1)
    expect(within(d).getByText('4 su 6')).toBeTruthy()
    expect(within(d).getByText('3 su 6')).toBeTruthy()
    expect(within(d).getByText('0 su 3')).toBeTruthy()
    expect(within(d).getByText('1 gara')).toBeTruthy()
    expect(within(d).getAllByText('2,2').length).toBeGreaterThan(0)
    expect(within(d).getByText('90%')).toBeTruthy()
  })

  it('contesto chiuso: movimento n.d. prima della seconda lettura, rosa n.d. mai 0 (modifiche 7, 9, 13)', async () => {
    const d = await detail()
    expect(within(d).getByText(/seconda lettura Bet365 alle 17:45/)).toBeTruthy()
    expect(within(d).getByText(/rosa non nota per entrambe \(n\.d\., non 0\)/)).toBeTruthy()
    expect(within(d).getByText(/1,6 e 1,8 a gara \(ultime 5\)/)).toBeTruthy()
    expect(within(d).getAllByText('rosa n.d.').length).toBeGreaterThan(0)
    expect(within(d).queryByText(/0 titolari/)).toBeNull()
    expect(within(d).getAllByText('n.d.').length).toBeGreaterThan(0)
  })

  it('avvisi di calendario e motivazione nella testata (modifica 17)', async () => {
    const api = await import('../../lib/analystJournalApi')
    const r = {
      ...row,
      balance: { index: 80, class: 'Equilibrio' },
      match_type: 'Squilibrio',
      close_games: { code: 'ravvicinata', label: '⚠ gara ravvicinata', text: 'Juve Stabia ha giocato 2 giorni fa (campionato)' },
      season_end: {
        code: 'fine',
        label: '⚑ ultime 2 giornate',
        text: 'Juve Stabia: posizione decisa (retrocessa) · Catanzaro: posizione decisa (2ª)',
        home: null,
        away: null,
        alerts: [{ code: 'senza_motivazioni', text: '⚠ gara senza motivazioni: risultato poco prevedibile, la X rende meno della quota (storico −9,0%)' }],
      },
    }
    vi.mocked(api.getMatchTable).mockResolvedValueOnce({ ...response, rows: [r] })
    const d = await detail()
    expect(within(d).getByText('⚠ gara ravvicinata')).toBeTruthy()
    expect(within(d).getByText('⚑ ultime 2 giornate')).toBeTruthy()
    expect(within(d).getByText(/posizione decisa \(retrocessa\)/)).toBeTruthy()
    expect(within(d).getByText(/gara senza motivazioni/)).toBeTruthy()
    expect(within(d).getByText('Quote e Cecchino non concordano sull’equilibrio della gara.'.replace('’', "'"))).toBeTruthy()
  })

  it('classifica e giorno dopo restano', async () => {
    const api = await import('../../lib/analystJournalApi')
    render(<MatchTable />)
    await screen.findAllByText('Juve Stabia')
    await userEvent.click(screen.getByRole('button', { name: 'Classifica' }))
    expect(await screen.findByText(/Ricostruita/)).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'Domani' }))
    const days = vi.mocked(api.getMatchTable).mock.calls.map((c) => c[0]?.day)
    const tomorrow = new Date(Date.now() + 86400000).toLocaleDateString('sv-SE', { timeZone: 'Europe/Rome' })
    expect(days).toContain(tomorrow)
  })
})
