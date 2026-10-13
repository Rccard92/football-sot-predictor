/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { CecchinoTodayDetailResponse } from '../../lib/cecchinoTodayApi'
import { CecchinoTodayDetailHeader } from './CecchinoTodayDetailHeader'

function detail(extra: Partial<CecchinoTodayDetailResponse> = {}): CecchinoTodayDetailResponse {
  return {
    status: 'ok',
    country_name: 'Finland',
    league_name: 'Veikkausliiga',
    home_team_name: 'SJK',
    away_team_name: 'Mariehamn',
    kickoff: '2026-09-18T15:00:00Z',
    ...extra,
  }
}

describe('CecchinoTodayDetailHeader', () => {
  afterEach(() => cleanup())

  it('mostra primo tempo e finale quando la partita ha un punteggio', () => {
    render(
      <CecchinoTodayDetailHeader
        detail={detail({
          match_display_status: 'finished',
          score: {
            halftime: { home: 0, away: 1, available: true },
            fulltime: { home: 2, away: 2, available: true },
          },
        })}
      />,
    )
    const box = screen.getByTestId('today-detail-score')
    expect(box.textContent).toContain('PT')
    expect(box.textContent).toContain('0 – 1')
    expect(box.textContent).toContain('Finale')
    expect(box.textContent).toContain('2 – 2')
  })

  it('partita non iniziata: nessun riquadro risultato', () => {
    render(
      <CecchinoTodayDetailHeader
        detail={detail({
          score: {
            halftime: { home: null, away: null, available: false },
            fulltime: { home: null, away: null, available: false },
          },
        })}
      />,
    )
    expect(screen.queryByTestId('today-detail-score')).toBeNull()
  })
})
