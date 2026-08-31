/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CecchinoLabPage } from './CecchinoLabPage'

vi.mock('../components/cecchino-data-lab/OverviewTab', () => ({
  OverviewTab: () => <div>overview</div>,
}))
vi.mock('../components/cecchino-data-lab/ImportWizardTab', () => ({
  ImportWizardTab: () => <div>import</div>,
}))
vi.mock('../components/cecchino-data-lab/DatasetsTab', () => ({
  DatasetsTab: () => <div>datasets</div>,
}))
vi.mock('../components/cecchino-data-lab/MatchesExplorerTab', () => ({
  MatchesExplorerTab: () => <div>matches</div>,
}))
vi.mock('../components/cecchino-data-lab/DataQualityTab', () => ({
  DataQualityTab: () => <div>quality</div>,
}))
vi.mock('../components/cecchino-data-lab/HistoricalScansTab', () => ({
  HistoricalScansTab: () => <div>historical</div>,
}))
vi.mock('../components/cecchino-data-lab/PatternLabTab', () => ({
  PatternLabTab: () => <div>pattern lab</div>,
}))
vi.mock('../components/cecchino-data-lab/league-pattern-analysis/LeaguePatternAnalysisTab', () => ({
  LeaguePatternAnalysisTab: () => (
    <div data-testid="league-pattern-analysis-tab">lpa</div>
  ),
}))
vi.mock('../components/cecchino-data-lab/MatchDetailDrawer', () => ({
  MatchDetailDrawer: () => null,
}))
vi.mock('framer-motion', () => ({
  motion: {
    div: (props: Record<string, unknown>) => <div {...props} />,
  },
}))

afterEach(() => cleanup())

describe('CecchinoLabPage League Pattern Analysis tab', () => {
  it('espone la tab League Pattern Analysis accanto a Pattern Lab', () => {
    render(
      <MemoryRouter>
        <CecchinoLabPage />
      </MemoryRouter>,
    )
    expect(screen.getByText('Pattern Lab')).toBeTruthy()
    expect(screen.getByText('League Pattern Analysis')).toBeTruthy()
  })
})
