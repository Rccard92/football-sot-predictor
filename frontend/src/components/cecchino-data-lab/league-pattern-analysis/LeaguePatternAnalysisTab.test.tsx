/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeaguePatternAnalysisTab } from './LeaguePatternAnalysisTab'

const apiMock = vi.hoisted(() => ({
  fetchLeaguePatternAnalysisLatest: vi.fn(),
  fetchLeaguePatternAnalysisLeague: vi.fn(),
  fetchLeaguePatternAnalysisPattern: vi.fn(),
  fetchLeaguePatternAnalysisNative: vi.fn(),
}))

vi.mock('../../../lib/leaguePatternAnalysisApi', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/leaguePatternAnalysisApi')>(
    '../../../lib/leaguePatternAnalysisApi',
  )
  return { ...actual, ...apiMock }
})

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="lpa-heatmap-chart">heatmap</div>,
}))

vi.mock('framer-motion', () => ({
  motion: {
    div: (props: Record<string, unknown>) => <div {...props} />,
  },
}))

const samplePayload = {
  metadata: {
    snapshot_id: 1,
    analysis_version: 'league_pattern_analysis_v1',
    status: 'ready',
    source_run_ids: [17, 19, 20, 21],
    source_seasons: ['2021/2022', '2022/2023', '2023/2024', '2024/2025'],
    analysis_dataset_locked: true,
    future_oos_season: '2025/2026',
    future_oos_included: false,
  },
  summary: {
    seasons_count: 4,
    competitions_count: 16,
    eligible_matches_analyzed: 1000,
    informative_market_rows_analyzed: 5000,
    global_patterns_count: 12,
    league_native_count: 10,
    top_insights: { min_sample: 20 },
  },
  global_patterns: [
    {
      pattern_id: 'P09',
      label: 'P09 · DRAW',
      human: {
        human_title: 'Pareggio con produzione offensiva media',
        short_explanation: 'Test',
        long_explanation: 'Cosa identifica: test',
        technical_formula: 'DRAW + OP MEDIUM + Tempo LOW',
      },
      by_season: {
        '2021/2022': { n: 11, roi_pct: -14.5, profit_1u: -1.6, win_rate: 0.3 },
      },
      total: {
        n: 56,
        roi_pct: 32.5,
        profit_1u: 18,
        stability_label: '3/4 stagioni positive',
        win_rate: 0.4,
        avg_odds: 3.2,
      },
    },
  ],
  competition_regimes_overview: [
    {
      competition: 'Serie B',
      total: {
        matches: 400,
        home_pct: 40,
        draw_pct: 30,
        away_pct: 30,
        over_25_pct: 45,
        under_25_pct: 55,
        avg_ft_goals: 2.3,
      },
    },
  ],
  heatmap: {
    pattern_ids: ['P09'],
    competitions: ['Serie B'],
    cells: [
      {
        pattern_id: 'P09',
        competition: 'Serie B',
        n: 56,
        roi_pct: 32.5,
        profit_1u: 18,
        positive_seasons: 3,
        seasons_with_bets: 4,
        low_sample: false,
      },
    ],
    low_sample_n: 15,
  },
  specializations: [
    {
      id: 'SPEC_P09_SERIE_B',
      pattern_id: 'P09',
      competition: 'Serie B',
      status: 'league_specialization_candidate',
      label: 'Specializzazione da validare',
      metrics: { n: 56, roi_pct: 32.5, profit_1u: 18, stability_label: '3/4' },
    },
  ],
  incompatibilities: [
    {
      id: 'EXCL_P08_SERIE_A',
      pattern_id: 'P08',
      competition: 'Serie A',
      status: 'exclusion_hypothesis',
      label: 'Ipotesi di esclusione',
      metrics: { n: 27, roi_pct: -18.3 },
      negative_label: '3/4 stagioni negative',
    },
  ],
  league_native: [
    {
      pattern_id: 'LN01',
      human_title: 'Vittoria ospite in partite a ritmo medio',
      competition: 'Championship',
      human: {
        human_title: 'Vittoria ospite in partite a ritmo medio',
        short_explanation: 'Test LN',
        long_explanation: 'Cosa identifica LN',
        technical_formula: 'AWAY + Tempo MEDIUM',
      },
      by_season: {
        '2021/2022': { n: 35, roi_pct: 17.3 },
      },
      total: { n: 183, roi_pct: 18.3, profit_1u: 33, stability_label: '4/4' },
    },
  ],
  methodology: {},
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

beforeEach(() => {
  apiMock.fetchLeaguePatternAnalysisLatest.mockResolvedValue(samplePayload)
  apiMock.fetchLeaguePatternAnalysisLeague.mockResolvedValue({
    metadata: samplePayload.metadata,
    competition: 'Serie B',
    league_overview: {
      competition: 'Serie B',
      by_season: {
        '2021/2022': { matches: 100, home_pct: 40, draw_pct: 30, away_pct: 30 },
      },
      total: samplePayload.competition_regimes_overview[0].total,
    },
    patterns: [
      {
        pattern_id: 'P09',
        by_season: { '2021/2022': { n: 11, roi_pct: -14.5 } },
        total: { n: 56, roi_pct: 32.5, profit_1u: 18, stability_label: '3/4' },
      },
    ],
  })
  apiMock.fetchLeaguePatternAnalysisPattern.mockResolvedValue({
    metadata: samplePayload.metadata,
    pattern: {
      ...samplePayload.global_patterns[0],
      by_competition: {
        'Serie B': {
          competition: 'Serie B',
          total: { n: 56, roi_pct: 32.5, profit_1u: 18, stability_label: '3/4' },
        },
      },
    },
  })
})

describe('LeaguePatternAnalysisTab', () => {
  it('mostra tab, subtab global e badge 2025/26', async () => {
    render(<LeaguePatternAnalysisTab />)
    await waitFor(() => expect(screen.getByTestId('league-pattern-analysis-tab')).toBeTruthy())
    expect(screen.getByTestId('lpa-dataset-locked').textContent).toMatch(/LOCKED/)
    expect(screen.getByTestId('lpa-no-2025-26').textContent).toMatch(/NON UTILIZZATA/)
    expect(screen.getByTestId('lpa-subtab-global')).toBeTruthy()
    expect(screen.getByTestId('lpa-subtab-league')).toBeTruthy()
    expect(screen.getByTestId('lpa-subtab-native')).toBeTruthy()
    expect(screen.getByTestId('lpa-panel-global')).toBeTruthy()
    expect(screen.getByTestId('lpa-heatmap-chart')).toBeTruthy()
  })

  it('cambia subtab league e native; selezione campionato', async () => {
    render(<LeaguePatternAnalysisTab />)
    await waitFor(() => expect(screen.getByTestId('lpa-panel-global')).toBeTruthy())

    fireEvent.click(screen.getByTestId('lpa-subtab-league'))
    await waitFor(() => expect(screen.getByTestId('lpa-panel-league')).toBeTruthy())
    expect(screen.getByTestId('lpa-league-chips')).toBeTruthy()
    await waitFor(() =>
      expect(apiMock.fetchLeaguePatternAnalysisLeague).toHaveBeenCalledWith('Serie B'),
    )

    fireEvent.click(screen.getByTestId('lpa-subtab-native'))
    expect(screen.getByTestId('lpa-panel-native')).toBeTruthy()
    expect(screen.getByText('LN01')).toBeTruthy()
  })

  it('tooltip info e drawer pattern; metodologia NOT USED', async () => {
    render(<LeaguePatternAnalysisTab />)
    await waitFor(() => expect(screen.getByText('P09')).toBeTruthy())
    expect(screen.getAllByLabelText(/Informazioni|Cosa identifica/).length).toBeGreaterThan(0)

    fireEvent.click(screen.getByText('P09'))
    await waitFor(() =>
      expect(apiMock.fetchLeaguePatternAnalysisPattern).toHaveBeenCalledWith('P09'),
    )
    await waitFor(() => expect(screen.getByText('Chiudi')).toBeTruthy())

    fireEvent.click(screen.getByText('METODOLOGIA'))
    expect(screen.getByTestId('lpa-method-oos-not-used').textContent).toBe('NOT USED')
  })
})
