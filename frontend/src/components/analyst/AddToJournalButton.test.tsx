/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AddToJournalButton } from './AddToJournalButton'

vi.mock('../../contexts/AuthContext', () => ({
  useOptionalAuth: () => ({ me: { id: 1 }, canSee: () => true }),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const createEntry = vi.fn((input: unknown) => Promise.resolve({ entry: input }))

vi.mock('../../lib/analystJournalApi', async (orig) => ({
  ...(await orig<typeof import('../../lib/analystJournalApi')>()),
  getJournalMeta: vi.fn(() => Promise.resolve({ checklist: [], markets: [], can_write: true, user_id: 1, is_admin: false })),
  getFixtureInfo: vi.fn(() =>
    Promise.resolve({
      fixture: {
        today_fixture_id: 7,
        match_date: '2026-11-09',
        kickoff: '2099-11-09T19:00:00+00:00',
        started: false,
        league_name: 'Serie Z',
        country_name: 'Italia',
        home_team: 'Casa FC',
        away_team: 'Ospite FC',
        odds_checked_at: '2026-11-08T05:22:00+00:00',
      },
      markets: [{ key: 'UNDER_2_5', label: 'Under 2.5', group: 'Under', quota_book: 1.85, prob_cecchino: 0.55 }],
      hints: {},
      my_entries: [],
    }),
  ),
  listCycles: vi.fn(() => Promise.resolve({ cycles: [] })),
  checkPlay: vi.fn(() => Promise.resolve({ match_type: null, quota_cecchino: null, warnings: [], checklist_warning: null, rule: null })),
  createEntry: (input: unknown) => createEntry(input),
}))

describe('AddToJournalButton: quota presa e bookmaker (09/11/2026)', () => {
  afterEach(() => {
    cleanup()
    createEntry.mockClear()
    window.localStorage.clear()
  })

  it('la quota presa non si riempie con quella del tool e servono quota e bookmaker', async () => {
    render(<AddToJournalButton todayFixtureId={7} source="tabella" marketKey="UNDER_2_5" quota={1.85} />)
    await userEvent.click(screen.getByTestId('add-to-journal'))
    await screen.findByText(/Casa FC – Ospite FC/)
    const quota = screen.getByPlaceholderText('es. 1,85') as HTMLInputElement
    expect(quota.value).toBe('')
    // quota del tool a parte e ora della quota con l'avviso (letta ieri)
    expect(screen.getByText(/Quota del tool/).textContent).toContain('1,85')
    expect(screen.getByText(/Quote lette/).textContent).toContain('più di 6 ore')

    await userEvent.click(screen.getByRole('button', { name: /Salva/ }))
    expect(await screen.findByText('Scrivi la quota presa')).toBeTruthy()
    await userEvent.type(quota, '1,92')
    await userEvent.click(screen.getByRole('button', { name: /Salva/ }))
    expect(await screen.findByText('Scrivi il bookmaker della quota presa')).toBeTruthy()
    expect(createEntry).not.toHaveBeenCalled()

    await userEvent.type(screen.getByPlaceholderText('es. Bet365'), 'Sisal')
    await userEvent.click(screen.getByRole('button', { name: /Salva/ }))
    expect(createEntry).toHaveBeenCalledTimes(1)
    expect(createEntry.mock.calls[0][0]).toMatchObject({ market_key: 'UNDER_2_5', quota: 1.92, bookmaker: 'Sisal' })
    // il bookmaker si ricorda per la prossima giocata
    expect(window.localStorage.getItem('diario-ultimo-bookmaker')).toBe('Sisal')
  })
})
