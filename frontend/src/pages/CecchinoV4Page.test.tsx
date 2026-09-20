/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mockCecchinoV4Api } from '../components/cecchino-v4/mock/cecchinoV4Mock'
import { CecchinoV4Page } from './CecchinoV4Page'

vi.mock('../components/cecchino-lab/LabEChartsCore', () => ({
  default: () => <div data-testid="v4-chart">grafico</div>,
}))

function stubMatchMedia(desktop: boolean) {
  const make = (query: string): MediaQueryList =>
    ({
      matches: query.includes('1536') ? desktop : desktop,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList
  Object.defineProperty(window, 'matchMedia', { writable: true, configurable: true, value: make })
}

function renderPage(initialEntry = '/cecchino-v4') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/cecchino-v4" element={<CecchinoV4Page api={mockCecchinoV4Api} />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('CecchinoV4Page', () => {
  beforeEach(() => {
    stubMatchMedia(false)
  })

  afterEach(() => {
    cleanup()
  })

  it('mostra intestazione, aiuto, quattro viste e le partite di oggi dal mock', async () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1, name: 'Cecchino V4' })).toBeTruthy()
    expect(screen.getByTestId('v4-help').textContent).toContain('"In osservazione" = esame E4 non superato')
    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual(['Partite', 'Shortlist', 'Misura', 'Motore'])
    expect(tabs[0].getAttribute('aria-selected')).toBe('true')

    await screen.findByText('Milan')
    const cards = screen.getAllByTestId('v4-fixture-card')
    expect(cards.length).toBe(8)

    // la scheda mostra una riga sola per l'esito: etichetta, probabilita', quota, profitto
    const milan = cards.find((c) => c.getAttribute('data-fixture-id') === '12') as HTMLElement
    expect(within(milan).getByTestId('v4-best-play').textContent).toBe('Inter over 6,5 tiri in porta · 61% · 1,85 · +13%')
    expect(within(milan).queryByText(/gol attesi/i)).toBeNull()
    expect(within(milan).queryByText(/Segno più probabile/i)).toBeNull()

    const getafe = cards.find((c) => c.getAttribute('data-fixture-id') === '18') as HTMLElement
    expect(within(getafe).getByTestId('v4-no-play').textContent).toBe('Nessuna giocata · incertezza alta')

    // partita finita: punteggio nell'intestazione della scheda, formazioni ufficiali col pallino
    const bologna = cards.find((c) => c.getAttribute('data-fixture-id') === '14') as HTMLElement
    expect(within(bologna).getByText('Finita 1 - 2')).toBeTruthy()
    expect(within(bologna).getByLabelText('Formazioni ufficiali')).toBeTruthy()

    // riepilogo a badge come in Cecchino Today
    const summary = screen.getByTestId('v4-abstention-line')
    expect(within(summary).getByText('8 partite')).toBeTruthy()
    expect(within(summary).getByText('3 giocate')).toBeTruthy()
    expect(within(summary).getByText('5 astensioni')).toBeTruthy()
  })

  it('il filtro "Solo con giocata" riduce la lista alle partite con giocata', async () => {
    renderPage()
    await screen.findByText('Milan')
    expect(screen.getAllByTestId('v4-fixture-card').length).toBe(8)

    fireEvent.click(screen.getByLabelText('Solo con giocata'))
    await waitFor(() => expect(screen.getAllByTestId('v4-fixture-card').length).toBe(3))
    expect(screen.queryAllByTestId('v4-no-play').length).toBe(0)
  })

  it('aprendo una partita finita mostra i sei blocchi, con "Perché sì, perché no" e "Chi sono" gia aperti', async () => {
    renderPage()
    await screen.findByText('Bologna')
    fireEvent.click(screen.getByRole('button', { name: 'Bologna - Napoli, apri il ragionamento' }))

    const reasoning = await screen.findByTestId('v4-reasoning')
    for (const title of ['Chi sono', 'Come giocano', 'Contesto', 'Cosa prevede', 'Perché sì, perché no', 'Come è andata']) {
      expect(within(reasoning).getByText(title)).toBeTruthy()
    }
    // il blocco 5 e' il primo ed e' aperto: la giocata si legge subito
    const blocks = within(reasoning).getAllByTestId(/^v4-block-/)
    expect(blocks[0].getAttribute('data-testid')).toBe('v4-block-5')
    expect(within(reasoning).getByRole('button', { name: /Perché sì, perché no/ }).getAttribute('aria-expanded')).toBe('true')
    expect(within(reasoning).getByTestId('v4-why-play').textContent).toContain('Napoli over 4,5 tiri in porta')
    expect(within(reasoning).getByRole('button', { name: /Chi sono/ }).getAttribute('aria-expanded')).toBe('true')
    expect(within(reasoning).getByRole('button', { name: /Cosa prevede/ }).getAttribute('aria-expanded')).toBe('false')
    // blocco 6 chiuso: lo apro e leggo previsto contro reale
    fireEvent.click(within(reasoning).getByRole('button', { name: /Come è andata/ }))
    expect(within(reasoning).getByText('Vinta')).toBeTruthy()
    expect(within(reasoning).getByText('Tiri in porta Napoli')).toBeTruthy()
  })

  it('partita senza giocata: il blocco 5 spiega il motivo con play null', async () => {
    renderPage('/cecchino-v4?fixture=13')
    const reasoning = await screen.findByTestId('v4-reasoning')
    expect(within(reasoning).getByTestId('v4-why-no-play').textContent).toBe('Nessuna giocata · prezzo giusto')
    expect(within(reasoning).queryByText('Come è andata')).toBeNull()
  })

  it('Milan - Inter: prima i sei mercati chiave, poi tutti i mercati con le statistiche sulla linea migliore', async () => {
    renderPage('/cecchino-v4?fixture=12')
    const reasoning = await screen.findByTestId('v4-reasoning')
    expect(within(reasoning).getByRole('heading', { level: 3, name: 'Milan - Inter' })).toBeTruthy()

    fireEvent.click(within(reasoning).getByRole('button', { name: /Cosa prevede/ }))
    const table = within(reasoning).getByTestId('v4-markets-table')

    // sei mercati chiave: la giocata migliore per prima, poi 1X2 e over/under 2,5
    const keyRows = within(table).getAllByTestId('v4-key-market-row')
    expect(keyRows.length).toBe(6)
    expect(keyRows.map((r) => r.querySelector('td')?.textContent)).toEqual([
      'Inter over 6,5 tiri in porta',
      '1',
      'X',
      '2',
      'Over 2,5 gol',
      'Under 2,5 gol',
    ])
    expect(within(table).getByText('61% (55–66)')).toBeTruthy()
    expect(within(table).queryByText('Tiri in porta · Inter')).toBeNull()

    // tabella completa con i verdetti
    fireEvent.click(within(table).getByRole('button', { name: 'Mostra tutti i mercati' }))
    const chips = within(table).getAllByTestId('v4-verdict-chip')
    const verdicts = new Set(chips.map((c) => c.getAttribute('data-verdict')))
    expect(verdicts.has('giocabile')).toBe(true)
    expect(verdicts.has('prezzo_giusto')).toBe(true)
    expect(verdicts.has('solo_descrittivo')).toBe(true)
    expect(verdicts.has('non_quotato')).toBe(true)
    expect(within(table).getAllByText('Giocabile').length).toBeGreaterThan(0)
    expect(within(table).getAllByText('Prezzo giusto').length).toBeGreaterThan(0)

    // il gruppo "Tiri in porta · Inter" mostra solo la linea della giocata; "Altre linee" apre il selettore
    const group = within(table).getByText('Tiri in porta · Inter').closest('tr') as HTMLElement
    expect(within(table).getAllByText('Inter over 6,5 tiri in porta').length).toBeGreaterThan(0)
    expect(within(table).queryByText('Inter over 7,5 tiri in porta')).toBeNull()
    fireEvent.click(within(group).getByRole('button', { name: /Altre linee/ }))
    fireEvent.click(within(group).getByRole('button', { name: '7,5' }))
    expect(within(table).getByText('Inter over 7,5 tiri in porta')).toBeTruthy()
  })

  it('la vista Shortlist divide Top e Altre e mostra la sigillatura con impronta', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('tab', { name: 'Shortlist' }))
    expect(screen.getByRole('tab', { name: 'Shortlist' }).getAttribute('aria-selected')).toBe('true')

    await screen.findByTestId('v4-shortlist')
    expect(screen.getByTestId('v4-shortlist-top-title').textContent).toBe('Top · 15')
    expect(screen.getByTestId('v4-shortlist-others-title').textContent).toBe('Altre · 3')
    expect(screen.getAllByTestId('v4-shortlist-row').length).toBe(18)
    const seal = screen.getByTestId('v4-shortlist-seal').textContent ?? ''
    expect(seal).toMatch(/^Sigillata alle \d{2}:\d{2} · impronta abcd1234ef56…$/)
    expect(screen.getByText('Esame E4 non superato: giocate classiche in osservazione, non consigliate')).toBeTruthy()
    expect(screen.getByText('Ritirata')).toBeTruthy()
    expect(screen.getByText('Formazione ufficiale: Lacazette non titolare')).toBeTruthy()
    expect(screen.getByText('Astensioni')).toBeTruthy()
  })

  it('la vista Motore mostra gli esami con i tre esiti e i numeri chiave, l’arena e i dati', async () => {
    renderPage('/cecchino-v4?view=motore')
    expect(screen.getByRole('tab', { name: 'Motore' }).getAttribute('aria-selected')).toBe('true')
    const cards = await screen.findAllByTestId('v4-exam-card')
    const outcomes = cards.map((c) => within(c).getAllByTestId('v4-exam-chip')[0].textContent)
    expect(outcomes).toEqual(['Superato', 'Non superato', 'In attesa'])
    expect(screen.getByText('docs/v4/PREREGISTRAZIONE_FASE_1.md')).toBeTruthy()

    // E1: Brier V3 → V4 in una griglia piccola, senza le chiavi grezze
    const e1 = cards[0]
    expect(within(e1).getByText('Brier · V3 → V4')).toBeTruthy()
    expect(within(e1).getByText('0,2063 → 0,2041')).toBeTruthy()
    expect(within(e1).queryByText(/^code$/)).toBeNull()
    expect(within(e1).queryByText(/computed at/)).toBeNull()
    // E2: verdetto per statistica come chip
    const e2 = cards[1]
    expect(within(e2).getByText('Tiri in porta')).toBeTruthy()
    expect(within(e2).getByText('Corner')).toBeTruthy()
    expect(within(e2).getAllByTestId('v4-exam-chip').length).toBeGreaterThanOrEqual(4)
    // E4 senza numeri
    expect(within(cards[2]).getByText('Nessun numero ancora.')).toBeTruthy()

    await screen.findAllByTestId('v4-challenger')
    await screen.findByTestId('v4-coverage-table')
    expect(screen.getByTestId('v4-api-budget').textContent).toBe('412 / 7.000 chiamate oggi')
  })

  it('la vista Misura mostra i KPI con intervallo e i grafici', async () => {
    renderPage('/cecchino-v4?view=misura')
    await screen.findByTestId('v4-measure')
    expect(screen.getByText('−1,2% (−4,0 · +1,8)')).toBeTruthy()
    expect(screen.getAllByTestId('v4-chart').length).toBe(2)
    expect(screen.getByTestId('v4-alert').textContent).toContain('Mercato Corner')
    expect(screen.getByTestId('v4-alert').textContent).toContain('ritiro proposto il 27/09')
  })

  it('sul desktop il Ragionamento sta nel pannello a destra', async () => {
    stubMatchMedia(true)
    renderPage('/cecchino-v4?fixture=12')
    await screen.findByTestId('v4-detail-panel')
    const panel = screen.getByTestId('v4-detail-panel')
    await within(panel).findByTestId('v4-reasoning')
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
