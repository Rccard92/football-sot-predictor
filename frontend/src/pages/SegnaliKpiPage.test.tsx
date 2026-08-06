/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { KpiSignalsHeatmapLab } from '../components/cecchino-kpi-signals/KpiSignalsHeatmapLab'
import { KpiSignalsFilters } from '../components/cecchino-kpi-signals/KpiSignalsFilters'
import { KpiSignalDetailDrawer } from '../components/cecchino-kpi-signals/KpiSignalDetailDrawer'
import { PurchasabilityBadge } from '../components/cecchino-kpi-signals/PurchasabilityBadge'
import {
  KPI_HEATMAP_ROWS,
  KPI_SELECTION_OPTIONS,
  type KpiSignalActivationRow,
} from '../lib/cecchinoKpiSignalsApi'

const noop = () => undefined

const filterBase = {
  dateFrom: '2026-08-06',
  dateTo: '2026-08-06',
  ratingBucket: '',
  selectionKey: '',
  evaluationStatus: '',
  countryName: '',
  leagueName: '',
  purchasabilityVersion: '',
  purchasabilityStatus: '',
  purchasabilityClass: '',
  purchasabilityQuality: '',
  purchasabilityScoreMin: '' as const,
  purchasabilityScoreMax: '' as const,
  purchasabilityScoreError: null,
  loading: false,
  actionLoading: false,
  onDateFromChange: noop,
  onDateToChange: noop,
  onRatingBucketChange: noop,
  onSelectionKeyChange: noop,
  onEvaluationStatusChange: noop,
  onCountryNameChange: noop,
  onLeagueNameChange: noop,
  onPurchasabilityVersionChange: noop,
  onPurchasabilityStatusChange: noop,
  onPurchasabilityClassChange: noop,
  onPurchasabilityQualityChange: noop,
  onPurchasabilityScoreMinChange: noop,
  onPurchasabilityScoreMaxChange: noop,
  onRefresh: noop,
  onSync: noop,
  onRevaluate: noop,
  onExport: noop,
}

afterEach(() => {
  cleanup()
})

describe('Segnali KPI 19 mercati + Acquistabilità', () => {
  it('heatmap mostra 19 righe in ordine canonico', () => {
    render(<KpiSignalsHeatmapLab cells={[]} onCellClick={noop} />)
    expect(KPI_HEATMAP_ROWS).toHaveLength(19)
    for (const label of [
      '1 PT',
      'X PT',
      '2 PT',
      'Under 1.5',
      'Over 3.5',
      'Under PT 0.5',
    ]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    }
    expect(KPI_HEATMAP_ROWS[0]).toBe('1')
    expect(KPI_HEATMAP_ROWS[18]).toBe('Under PT 1.5')
  })

  it('riga senza attivazioni resta visibile', () => {
    render(
      <KpiSignalsHeatmapLab
        cells={[]}
        rows={[...KPI_HEATMAP_ROWS]}
        onCellClick={noop}
      />,
    )
    expect(screen.getAllByText('X PT').length).toBeGreaterThan(0)
  })

  it('filtro pronostico è una select con 19 selection key', () => {
    render(<KpiSignalsFilters {...filterBase} />)
    expect(KPI_SELECTION_OPTIONS).toHaveLength(19)
    const select = screen.getByLabelText('Pronostico') as HTMLSelectElement
    expect(select.tagName).toBe('SELECT')
    expect(select.options.length).toBe(20) // Tutti + 19
  })

  it('filtri Acquistabilità disabilitati senza versione', () => {
    render(<KpiSignalsFilters {...filterBase} />)
    const status = screen.getByLabelText('Stato Acquistabilità') as HTMLSelectElement
    expect(status.disabled).toBe(true)
  })

  it('filtri Acquistabilità abilitati con V3', () => {
    render(<KpiSignalsFilters {...filterBase} purchasabilityVersion="v3" />)
    const status = screen.getByLabelText('Stato Acquistabilità') as HTMLSelectElement
    expect(status.disabled).toBe(false)
  })

  it('mostra errore validazione min > max', () => {
    render(
      <KpiSignalsFilters
        {...filterBase}
        purchasabilityVersion="v31"
        purchasabilityScoreMin={80}
        purchasabilityScoreMax={50}
        purchasabilityScoreError="Score minimo non può superare lo score massimo"
      />,
    )
    expect(screen.getByText(/Score minimo non può superare/)).toBeTruthy()
  })

  it('badge score zero e non supportato', () => {
    const { rerender } = render(
      <PurchasabilityBadge
        versionLabel="V3"
        snap={{ status: 'score', score: 0, class_label: 'Molto Bassa' }}
      />,
    )
    expect(screen.getByTitle(/0 · Molto Bassa/)).toBeTruthy()
    rerender(
      <PurchasabilityBadge versionLabel="V3" snap={{ status: 'unsupported_market' }} />,
    )
    expect(screen.getByTitle(/Non supportato/)).toBeTruthy()
  })

  it('drawer mostra blocchi V3/V3.1 e messaggio snapshot assente', () => {
    const row: KpiSignalActivationRow = {
      id: 1,
      today_fixture_id: 10,
      provider_fixture_id: 20,
      scan_date: '2026-08-06',
      kickoff: null,
      country_name: 'Italy',
      league_name: 'Serie A',
      home_team_name: 'A',
      away_team_name: 'B',
      selection_label: 'X PT',
      selection_key: 'DRAW_PT',
      normalized_market: 'MATCH_WINNER_1X2_FIRST_HALF',
      rating_score: 70,
      rating_label: 'Premium',
      rating_bucket: '70-79',
      quota_book: 3.2,
      quota_cecchino: 2.9,
      edge_pct: 5,
      score_pct: null,
      result_home_ht: null,
      result_away_ht: null,
      result_home_ft: null,
      result_away_ft: null,
      evaluation_status: 'pending',
      evaluation_reason: null,
      profit_units: null,
      stake_units: 1,
      evaluated_at: null,
      purchasability_v3: { status: 'unsupported_market', snapshot_available: true },
      purchasability_v31: { status: 'snapshot_unavailable', snapshot_available: false },
    }
    render(
      <MemoryRouter>
        <KpiSignalDetailDrawer state={{ type: 'activation', row }} onClose={noop} />
      </MemoryRouter>,
    )
    expect(screen.getByText('Acquistabilità V3')).toBeTruthy()
    expect(screen.getByText('Acquistabilità V3.1')).toBeTruthy()
    expect(screen.getByText(/Mercato non supportato dalla V3/)).toBeTruthy()
    expect(screen.getByText(/Snapshot Acquistabilità non disponibile/)).toBeTruthy()
  })

  it('compatibilità payload legacy senza purchasability', () => {
    const row = {
      id: 2,
      today_fixture_id: 11,
      provider_fixture_id: 21,
      scan_date: '2026-08-06',
      kickoff: null,
      country_name: null,
      league_name: null,
      home_team_name: 'C',
      away_team_name: 'D',
      selection_label: '1',
      selection_key: 'HOME',
      normalized_market: 'MATCH_WINNER_1X2',
      rating_score: 80,
      rating_label: null,
      rating_bucket: '80-89',
      quota_book: 2,
      quota_cecchino: null,
      edge_pct: null,
      score_pct: null,
      result_home_ht: null,
      result_away_ht: null,
      result_home_ft: null,
      result_away_ft: null,
      evaluation_status: 'pending',
      evaluation_reason: null,
      profit_units: null,
      stake_units: 1,
      evaluated_at: null,
    } as KpiSignalActivationRow
    render(
      <MemoryRouter>
        <KpiSignalDetailDrawer state={{ type: 'activation', row }} onClose={noop} />
      </MemoryRouter>,
    )
    expect(screen.getAllByText(/Snapshot Acquistabilità non disponibile/).length).toBeGreaterThan(0)
  })
})
