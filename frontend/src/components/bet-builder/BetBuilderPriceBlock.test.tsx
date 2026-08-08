/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { BetBuilderPriceBlock } from './BetBuilderPriceBlock'
import type { BetBuilderPriceValue } from '../../lib/cecchinoBetBuilderApi'

afterEach(() => cleanup())

function basePrice(over: Partial<BetBuilderPriceValue> = {}): BetBuilderPriceValue {
  return {
    present: false,
    method: 'v31_theoretical',
    quota_book: null,
    quota_cecchino: 1.5,
    prob_book: null,
    prob_cecchino: 0.67,
    vantaggio_prob: null,
    edge_pct: null,
    score_acquisto: null,
    rating: null,
    rating_label: null,
    status: 'available',
    ...over,
  }
}

describe('BetBuilderPriceBlock book provenance', () => {
  it('mostra Betfair quando non è fallback', () => {
    render(
      <BetBuilderPriceBlock
        price={basePrice({
          quota_book: 1.8,
          bookmaker_name: 'Betfair',
          book_fallback_used: false,
          provider_bookmaker_id: 3,
        })}
      />,
    )
    expect(screen.getByTestId('book-provenance').textContent).toBe('Betfair')
  })

  it('mostra Bet365 · fallback', () => {
    render(
      <BetBuilderPriceBlock
        price={basePrice({
          quota_book: 1.36,
          bookmaker_name: 'Bet365',
          book_fallback_used: true,
          provider_bookmaker_id: 8,
        })}
      />,
    )
    expect(screen.getByTestId('book-provenance').textContent).toBe('Bet365 · fallback')
  })

  it('mostra N/D senza quota Book', () => {
    render(<BetBuilderPriceBlock price={basePrice()} />)
    expect(screen.getByTestId('book-provenance').textContent).toBe('N/D')
  })
})
