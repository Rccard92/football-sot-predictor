/** @vitest-environment jsdom */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
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
  it('mostra forma, colori, grassetto, gialli e quote della bozza', async () => {
    render(<MatchTable />)
    expect(await screen.findByText('Casa FC')).toBeTruthy()
    const row = screen.getByText('Casa FC').closest('tr')!
    expect(within(row).getByText('4 pt')).toBeTruthy()
    expect(within(row).getAllByText('2-0')[0].className).toContain('text-emerald-700')
    const lost = within(row).getAllByText('1-3')[0]
    expect(lost.className).toContain('text-rose-700')
    expect(lost.className).toContain('font-bold')
    expect(within(row).getAllByText('1-1')[0].className).toContain('text-slate-400')
    expect(within(row).getAllByText('2-0')).toHaveLength(2) // ripetuti anche sotto Goal
    expect(within(row).getByText('n.d.')).toBeTruthy()
    expect(within(row).getByText('9')).toBeTruthy()
    expect(within(row).getByText('2,10')).toBeTruthy()
    expect(within(row).getByText('Equilibrio')).toBeTruthy()
    await userEvent.click(within(row).getByText('Altre 1 quote'))
    expect(screen.getByText('1,85')).toBeTruthy()
  })
})
