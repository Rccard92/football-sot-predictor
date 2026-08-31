import { beforeEach, describe, expect, it, vi } from 'vitest'

const requestJsonMock = vi.fn()

vi.mock('./api', () => ({
  requestJson: (...args: unknown[]) => requestJsonMock(...args),
}))

import {
  fetchLeaguePatternAnalysisLatest,
  fetchLeaguePatternAnalysisLeague,
  fetchLeaguePatternAnalysisNative,
  fetchLeaguePatternAnalysisPattern,
} from './leaguePatternAnalysisApi'

function assertRelativeLpaPath(path: string) {
  expect(path.startsWith('/api/cecchino-lab/league-pattern-analysis/')).toBe(true)
  expect(path).not.toContain('/https://')
  expect(path.startsWith('http')).toBe(false)
}

describe('leaguePatternAnalysisApi paths', () => {
  beforeEach(() => {
    requestJsonMock.mockReset()
    requestJsonMock.mockResolvedValue({})
  })

  it('passes only relative paths to requestJson (no /https://)', async () => {
    await fetchLeaguePatternAnalysisLatest()
    await fetchLeaguePatternAnalysisLeague('Serie A')
    await fetchLeaguePatternAnalysisPattern('P09')
    await fetchLeaguePatternAnalysisNative('LN01')

    expect(requestJsonMock).toHaveBeenCalledTimes(4)

    const paths = requestJsonMock.mock.calls.map((c) => c[0] as string)
    expect(paths).toEqual([
      '/api/cecchino-lab/league-pattern-analysis/latest',
      `/api/cecchino-lab/league-pattern-analysis/leagues/${encodeURIComponent('Serie A')}`,
      `/api/cecchino-lab/league-pattern-analysis/patterns/${encodeURIComponent('P09')}`,
      `/api/cecchino-lab/league-pattern-analysis/native/${encodeURIComponent('LN01')}`,
    ])

    for (const path of paths) {
      assertRelativeLpaPath(path)
    }
  })
})
