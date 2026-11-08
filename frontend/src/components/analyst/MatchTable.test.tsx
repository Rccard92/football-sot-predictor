/** @vitest-environment jsdom */
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { MatchTableResponse, TableGame } from '../../lib/analystJournalApi'
import { MatchTable } from './MatchTable'

const g = (ft: string, ht: string, ftOutcome: 'V' | 'N' | 'P', htOutcome: 'V' | 'N' | 'P', boldFt = false): TableGame => ({
  date: '2026-10-20',
  opponent: 'Rivale',
  opponent_rank: 2,
  home: true,
  ft,
  ht,
  ft_outcome: ftOutcome,
  ht_outcome: htOutcome,
  bold_ft: boldFt,
  bold_ht: false,
})

const response: MatchTableResponse = {
  day: '2026-11-05',
  total: 1,
  total_day: 1,
  page: 1,
  page_size: 50,
  countries: ['Italia'],
  leagues: ['Serie Z'],
  can_write: true,
  rows: [
    {
      today_fixture_id: 7,
      scan_date: '2026-11-05',
      kickoff: '2099-11-05T19:00:00+00:00',
      country: 'Italia',
      league: 'Serie Z',
      home_team: 'Casa FC',
      away_team: 'Ospite FC',
      eligible: true,
      balance: { index: 72.5, class: 'Equilibrio' },
      blocks: {
        forma_casa: {
          games: 3,
          enough: true,
          points: 4,
          max_points: 9,
          scored: 4,
          conceded: 4,
          ht_games: 3,
          ht_scored: 1,
          ht_conceded: 1,
          team_rank: 5,
          results: [g('2-0', '1-0', 'V', 'V'), g('1-1', '0-0', 'N', 'N', true), g('1-3', '0-1', 'P', 'P', true)],
        },
        forma_fuori: { games: 2, enough: false },
        forma_totale_casa: { games: 2, enough: false },
        forma_totale_fuori: { games: 1, enough: false },
      },
      yellows: { home: { games: 5, available: true, own: 9, opponents: 7, own_avg: 1.8, opponents_avg: 1.4 }, away: { games: 1, available: false } },
      standings_complete: true,
      home_rank: 5,
      away_rank: 3,
      quotes: [
        { key: 'HOME', label: '1', group: 'Fisse', quota: 2.1, status: 'out', warnings: ['Oltre la quota massima 1,55'] },
        { key: 'DRAW', label: 'X', group: 'Fisse', quota: 3.2, status: 'ok', warnings: [] },
        { key: 'AWAY', label: '2', group: 'Fisse', quota: null },
        { key: 'OVER_2_5', label: 'Over 2.5', group: 'Over', quota: 1.85 },
      ],
      match_type: 'Scala 1X',
      my_note: '',
      other_notes: [],
      started: false,
    },
  ],
}

vi.mock('../../lib/analystJournalApi', async (orig) => ({
  ...(await orig<typeof import('../../lib/analystJournalApi')>()),
  getMatchTable: vi.fn(() => Promise.resolve(response)),
  getMatchStandings: vi.fn(() =>
    Promise.resolve({
      today_fixture_id: 7,
      league: 'Serie Z',
      country: 'Italia',
      home_team_id: 1,
      away_team_id: 2,
      games: 3,
      complete: true,
      tables: {
        total: [
          { rank: 1, team_id: 2, team: 'Ospite FC', played: 2, won: 2, drawn: 0, lost: 0, gf: 4, ga: 1, gd: 3, points: 6 },
          { rank: 2, team_id: 1, team: 'Casa FC', played: 2, won: 1, drawn: 0, lost: 1, gf: 3, ga: 3, gd: 0, points: 3 },
        ],
        home: [{ rank: 1, team_id: 1, team: 'Casa FC', played: 1, won: 1, drawn: 0, lost: 0, gf: 2, ga: 0, gd: 2, points: 3 }],
        away: [
          { rank: 1, team_id: 2, team: 'Ospite FC', played: 1, won: 1, drawn: 0, lost: 0, gf: 2, ga: 0, gd: 2, points: 3 },
          { rank: 2, team_id: 1, team: 'Casa FC', played: 1, won: 0, drawn: 0, lost: 1, gf: 1, ga: 3, gd: -2, points: 0 },
        ],
      },
      recent: {
        '1': {
          total: [{ ...g('1-3', '0-1', 'P', 'P'), opponent_id: 2, opponent: 'Ospite FC', opponent_rank: 1, home: false }],
          home: [{ ...g('2-0', '1-0', 'V', 'V'), opponent_id: 2, opponent: 'Ospite FC', opponent_rank: 1 }],
          away: [{ ...g('1-3', '0-1', 'P', 'P'), opponent_id: 2, opponent: 'Ospite FC', opponent_rank: 1, home: false }],
        },
        '2': { total: [], home: [], away: [] },
      },
    }),
  ),
  saveMatchNote: vi.fn(() => Promise.resolve({ today_fixture_id: 7, note: 'x' })),
}))

describe('MatchTable', () => {
  afterEach(cleanup)

  it('lista compatta e scheda partita con risultati, cornice, gol, gialli e quote', async () => {
    render(<MatchTable />)
    expect(await screen.findAllByText('Casa FC')).toBeTruthy()
    const detail = screen.getByRole('heading', { level: 2 }).closest('aside')!
    expect(within(detail).getByText('4 pt')).toBeTruthy()
    // sconfitta contro una squadra piu' in alto: quadratino rosso con il bordo
    // il quadratino mostra il risultato; sconfitta contro una squadra piu' in alto: rosso con la cornice
    const lost = within(detail).getAllByTitle(/1-3 FT, persa/)[0]
    expect(lost.textContent).toBe('1-3')
    expect(lost.className).toContain('bg-rose-100')
    expect(lost.className).toContain('ring-2')
    const drawn = within(detail).getAllByTitle(/1-1 FT, pareggiata/)[0]
    expect(drawn.className).toContain('bg-slate-100')
    expect(drawn.className).toContain('ring-2')
    const won = within(detail).getAllByTitle(/2-0 FT, vinta/)[0]
    expect(won.textContent).toBe('2-0')
    expect(won.className).toContain('bg-emerald-100')
    expect(won.className).not.toContain('ring-2')
    expect(within(detail).getAllByTitle(/0-1 PT, persa/)[0].textContent).toBe('0-1')
    expect(within(detail).getByText('Gol PT')).toBeTruthy()
    expect(within(detail).getByText('n.d.')).toBeTruthy()
    expect(within(detail).getByText('1,8')).toBeTruthy()
    expect(within(detail).getByText(/totale 9 · 7 in 5 gare/)).toBeTruthy()
    expect(within(detail).getByText('1,85')).toBeTruthy()
    expect(within(detail).getAllByText('Meno di 3 gare (2)').length).toBe(2)
    expect(screen.queryByText(/Equilibrio/)).toBeNull()
    // tipo di partita e quote colorate con le regole di acquisto
    expect(within(detail).getByText('Scala 1X')).toBeTruthy()
    expect(within(detail).getByText('2,10').className).toContain('text-rose-700')
    expect(within(detail).getByText('3,20').className).toContain('text-emerald-700')
    expect(within(detail).getByText('2,10').closest('[title]')?.getAttribute('title')).toContain('Oltre la quota massima')
  })

  it('classifica completa: totale, casa e trasferta', async () => {
    render(<MatchTable />)
    await screen.findAllByText('Casa FC')
    await userEvent.click(screen.getByRole('button', { name: 'Classifica' }))
    const dialog = await screen.findByText('Ricostruita dai 3 risultati del campionato nel nostro archivio.')
    const aside = dialog.closest('aside')!
    expect(within(aside).getByText('6')).toBeTruthy()
    await userEvent.click(within(aside).getByRole('button', { name: 'Casa' }))
    expect(within(aside).queryByText('Ospite FC')).toBeNull()
    await userEvent.click(within(aside).getByRole('button', { name: 'Trasferta' }))
    expect(within(aside).getAllByText('Ospite FC').length).toBeGreaterThan(0)
    // clic sulla squadra di casa: si accende l'avversaria delle ultime gare fuori e compare il box
    await userEvent.click(within(aside).getByRole('button', { name: 'Casa FC' }))
    const opponentRow = within(aside).getAllByText('Ospite FC')[0].closest('tr')!
    expect(opponentRow.className).toContain('bg-rose-50')
    expect(within(aside).getByText(/Casa FC · ultime 1 partite fuori casa/)).toBeTruthy()
    // in casa la stessa selezione mostra la vittoria 2-0
    await userEvent.click(within(aside).getByRole('button', { name: 'Casa' }))
    expect(within(aside).getByText(/ultime 1 partite in casa/)).toBeTruthy()
    expect(within(aside).getAllByText('2-0').length).toBeGreaterThan(0)
    // secondo clic: si toglie
    await userEvent.click(within(aside).getByRole('button', { name: 'Casa FC' }))
    expect(within(aside).queryByText(/ultime 1 partite/)).toBeNull()
  })

  it('il pulsante Domani chiede il giorno dopo', async () => {
    const api = await import('../../lib/analystJournalApi')
    render(<MatchTable />)
    await screen.findAllByText('Casa FC')
    await userEvent.click(screen.getByRole('button', { name: 'Domani' }))
    const days = vi.mocked(api.getMatchTable).mock.calls.map((c) => c[0]?.day)
    const tomorrow = new Date(Date.now() + 86400000).toLocaleDateString('sv-SE', { timeZone: 'Europe/Rome' })
    expect(days).toContain(tomorrow)
  })
})
