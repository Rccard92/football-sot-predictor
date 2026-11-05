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
          team_rank: 5,
          results: [g('2-0', '1-0', 'V', 'V'), g('1-1', '0-0', 'N', 'N'), g('1-3', '0-1', 'P', 'P', true)],
        },
        forma_fuori: { games: 2, enough: false },
        forma_totale_casa: { games: 2, enough: false },
        forma_totale_fuori: { games: 1, enough: false },
      },
      yellows: { home: { games: 5, available: true, own: 9, opponents: 7 }, away: { games: 1, available: false } },
      standings_complete: true,
      home_rank: 5,
      away_rank: 3,
      quotes: [
        { key: 'HOME', label: '1', group: 'Fisse', quota: 2.1 },
        { key: 'DRAW', label: 'X', group: 'Fisse', quota: 3.2 },
        { key: 'AWAY', label: '2', group: 'Fisse', quota: null },
        { key: 'OVER_2_5', label: 'Over 2.5', group: 'Over', quota: 1.85 },
      ],
      my_note: '',
      other_notes: [],
      started: false,
    },
  ],
}

vi.mock('../../lib/analystJournalApi', async (orig) => ({
  ...(await orig<typeof import('../../lib/analystJournalApi')>()),
  getMatchTable: vi.fn(() => Promise.resolve(response)),
  saveMatchNote: vi.fn(() => Promise.resolve({ today_fixture_id: 7, note: 'x' })),
}))

describe('MatchTable', () => {
  afterEach(cleanup)

  it('lista compatta e scheda partita con forma, bordo, gialli e quote', async () => {
    render(<MatchTable />)
    expect(await screen.findAllByText('Casa FC')).toBeTruthy()
    const detail = screen.getByRole('heading', { level: 2 }).closest('aside')!
    expect(within(detail).getByText('4 pt')).toBeTruthy()
    // sconfitta contro una squadra piu' in alto: quadratino rosso con il bordo
    const lost = within(detail).getAllByTitle(/1-3 FT, persa/)[0]
    expect(lost.className).toContain('bg-rose-100')
    expect(lost.className).toContain('ring-2')
    const won = within(detail).getAllByTitle(/2-0 FT, vinta/)[0]
    expect(won.className).toContain('bg-emerald-100')
    expect(won.className).not.toContain('ring-2')
    expect(within(detail).getByText('n.d.')).toBeTruthy()
    expect(within(detail).getByText('9')).toBeTruthy()
    expect(within(detail).getByText('1,85')).toBeTruthy()
    expect(within(detail).getAllByText('Meno di 3 gare (2)').length).toBe(2)
    expect(screen.getAllByText(/73 · Equilibrio/).length).toBeGreaterThan(0)
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
