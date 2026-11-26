/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PlayCheck } from '../../lib/analystJournalApi'
import { AddToJournalButton } from './AddToJournalButton'

vi.mock('../../contexts/AuthContext', () => ({
  useOptionalAuth: () => ({ me: { id: 1 }, canSee: () => true }),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const createEntry = vi.fn((input: unknown) => Promise.resolve({ entry: { ...(input as object), id: 99 } }))
const savePaperPlay = vi.fn(() => Promise.resolve({ saved: true }))
const uploadEntryPhoto = vi.fn(() => Promise.resolve({ photo: {} }))
let check: PlayCheck = { match_type: null, quota_cecchino: null, warnings: [], checklist_warning: null, rule: null }

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
  checkPlay: vi.fn(() => Promise.resolve(check)),
  createEntry: (input: unknown) => createEntry(input),
  savePaperPlay: (...a: unknown[]) => savePaperPlay(...(a as [])),
  uploadEntryPhoto: (...a: unknown[]) => uploadEntryPhoto(...(a as [])),
}))

async function fillAnswers() {
  for (const group of ['Assenze pesanti confermate', 'Cambio allenatore o crisi', 'Motivazione particolare']) {
    await userEvent.click(screen.getByRole('group', { name: group }).querySelector('button')!)
  }
}

describe('Prima di salvare (capitolato del 24/11/2026)', () => {
  afterEach(() => {
    cleanup()
    createEntry.mockClear()
    savePaperPlay.mockClear()
    window.localStorage.clear()
    check = { match_type: null, quota_cecchino: null, warnings: [], checklist_warning: null, rule: null }
  })

  it('quota presa e bookmaker obbligatori, poi le tre domande e «cosa potrebbe smentire»', async () => {
    render(<AddToJournalButton todayFixtureId={7} source="tabella" marketKey="UNDER_2_5" quota={1.85} />)
    await userEvent.click(screen.getByTestId('add-to-journal'))
    await screen.findByText(/Casa FC – Ospite FC/)
    const quota = screen.getByPlaceholderText('es. 1,85') as HTMLInputElement
    expect(quota.value).toBe('')
    expect(screen.getByText(/Quota del tool/).textContent).toContain('1,85')
    expect(screen.getByText(/Quote lette/).textContent).toContain('più di 12 ore')
    // la vecchia checklist di 16 voci non c'e' piu'
    expect(screen.queryByText(/Scheda pronostico/)).toBeNull()

    const save = () => userEvent.click(screen.getByRole('button', { name: 'Salva nel diario' }))
    await save()
    expect(await screen.findByText('Scrivi la quota presa')).toBeTruthy()
    await userEvent.type(quota, '1,92')
    await save()
    expect(await screen.findByText('Scrivi il bookmaker della quota presa')).toBeTruthy()
    await userEvent.type(screen.getByPlaceholderText('es. Bet365'), 'Sisal')
    await save()
    expect(await screen.findByText(/Rispondi alle tre domande/)).toBeTruthy()
    await fillAnswers()
    await save()
    expect(await screen.findByText(/almeno 15 caratteri/)).toBeTruthy()
    expect(createEntry).not.toHaveBeenCalled()

    await userEvent.type(screen.getByPlaceholderText(/Il Catanzaro ha giocato/), 'Se la casa segna presto la gara si apre')
    await save()
    expect(createEntry).toHaveBeenCalledTimes(1)
    expect(createEntry.mock.calls[0][0]).toMatchObject({
      market_key: 'UNDER_2_5',
      quota: 1.92,
      bookmaker: 'Sisal',
      answers: { assenze: 'si', allenatore: 'si', motivazione: 'si' },
      risk_note: 'Se la casa segna presto la gara si apre',
      exception: false,
    })
    expect(window.localStorage.getItem('diario-ultimo-bookmaker')).toBe('Sisal')
  })

  it('segno bloccato: si salva sulla carta e si registra solo come eccezione con il motivo (modifiche 4 e 11)', async () => {
    check = {
      match_type: null,
      quota_cecchino: 2.26,
      warnings: [],
      checklist_warning: null,
      rule: null,
      sign: {
        key: 'UNDER_2_5',
        label: 'Under 2.5',
        group: 'UNDER / OVER',
        q: 1.8,
        q_at: '2099-11-09T05:00:00+00:00',
        q_source: 'morning',
        morning: 1.8,
        change: null,
        prob_book: 0.53,
        quota_cecchino: 2.26,
        prob_cecchino: 0.44,
        value: -0.2,
        state: 'blocked',
        reasons: [{ code: 'r1', rule: 'R1', text: 'R1 · book 15% sotto il Cecchino', short: 'R1' }],
        notes: [],
      },
      quota_gap: { pct: 0.06, text: 'La quota presa è diversa da quella del tool di 6%: controlla' },
      alerts: [{ code: 'p27', text: '⚠ P27 · favorita senza nulla da giocarsi' }],
    }
    render(<AddToJournalButton todayFixtureId={7} source="tabella" marketKey="UNDER_2_5" />)
    await userEvent.click(screen.getByTestId('add-to-journal'))
    expect(await screen.findByText('Questa giocata è fuori regola')).toBeTruthy()
    expect(screen.getByText('R1 · book 15% sotto il Cecchino')).toBeTruthy()
    expect(savePaperPlay).toHaveBeenCalledWith(7, 'UNDER_2_5')
    // promemoria della modifica 17 sotto «Motivazione particolare»
    expect(screen.getByText('⚠ P27 · favorita senza nulla da giocarsi')).toBeTruthy()
    expect(screen.getByText(/diversa da quella del tool di 6%/)).toBeTruthy()

    await userEvent.type(screen.getByPlaceholderText('es. 1,85'), '1,90')
    await userEvent.type(screen.getByPlaceholderText('es. Bet365'), 'Bet365')
    await fillAnswers()
    await userEvent.type(screen.getByPlaceholderText(/Il Catanzaro ha giocato/), 'Se il pressing alto non regge al ritmo')
    const register = screen.getByRole('button', { name: 'Registra eccezione' })
    await userEvent.click(register)
    expect(await screen.findByText(/Scrivi perché la vuoi registrare lo stesso/)).toBeTruthy()
    await userEvent.type(screen.getByPlaceholderText(/formazione ufficiale con 3 attaccanti/), 'formazione ufficiale uscita dopo le 6')
    await userEvent.click(register)
    expect(createEntry).toHaveBeenCalledTimes(1)
    expect(createEntry.mock.calls[0][0]).toMatchObject({ exception: true, exception_reason: 'formazione ufficiale uscita dopo le 6' })
  })
})
