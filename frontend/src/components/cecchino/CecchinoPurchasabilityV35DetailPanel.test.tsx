/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { CecchinoPurchasabilityV35DetailPanel } from './CecchinoPurchasabilityV35DetailPanel'
import { HOME_V35_ITEM, V35_VALID_SNAPSHOT } from './fixtures/purchasabilityV35Fixtures'

describe('CecchinoPurchasabilityV35DetailPanel execution quote', () => {
  it('mostra quota numerica e badge REAL, non il boolean', () => {
    render(
      <CecchinoPurchasabilityV35DetailPanel
        item={HOME_V35_ITEM}
        snapshot={V35_VALID_SNAPSHOT}
        selectedCandidate="A"
        panelId="test-panel"
      />,
    )
    const quoteBlock = screen.getByTestId('v35-execution-quote').closest('div')
    expect(quoteBlock).toBeTruthy()
    expect(within(quoteBlock!.parentElement!).getByTestId('v35-execution-quote').textContent).toBe('2.20')
    expect(within(quoteBlock!.parentElement!).getByText('REAL')).toBeTruthy()
    expect(within(quoteBlock!.parentElement!).queryByText('true')).toBeNull()
  })
})
