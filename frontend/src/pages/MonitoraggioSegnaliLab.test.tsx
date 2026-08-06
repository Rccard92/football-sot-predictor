/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SignalsActivationsLab } from '../components/cecchino-lab/SignalsActivationsLab'
import { SignalsDetailDrawer } from '../components/cecchino-lab/SignalsDetailDrawer'
import { SignalsLabFilters } from '../components/cecchino-lab/SignalsLabFilters'
import {
  ACQUISITION_FILTER_OPTIONS,
  CURRENT_SIGNAL_FORMULA_VERSION,
  DEFAULT_ACQUISITION_FILTER,
  DEFAULT_SIGNAL_FORMULA_VERSION,
  SIGNAL_FORMULA_VERSION_OPTIONS,
  buildCecchinoSignalsExportUrl,
  type SignalActivationRow,
} from '../lib/cecchinoSignalsApi'
import {
  acquiredBadgeLabel,
  acquisitionStatusLabel,
  formatConsensusRatio,
} from '../components/cecchino-lab/signalsLabUtils'

afterEach(() => {
  cleanup()
})

function filterProps(overrides: Partial<Parameters<typeof SignalsLabFilters>[0]> = {}) {
  return {
    dateFrom: '2026-08-06',
    dateTo: '2026-08-06',
    signalGroup: '',
    sourceColumn: '',
    evaluationStatus: '',
    countryName: '',
    leagueName: '',
    signalFormulaVersion: DEFAULT_SIGNAL_FORMULA_VERSION,
    acquisitionFilter: DEFAULT_ACQUISITION_FILTER,
    consensusYesCountMin: undefined as number | undefined,
    loading: false,
    actionLoading: false,
    onDateFromChange: vi.fn(),
    onDateToChange: vi.fn(),
    onSignalGroupChange: vi.fn(),
    onSourceColumnChange: vi.fn(),
    onEvaluationStatusChange: vi.fn(),
    onCountryNameChange: vi.fn(),
    onLeagueNameChange: vi.fn(),
    onSignalFormulaVersionChange: vi.fn(),
    onAcquisitionFilterChange: vi.fn(),
    onConsensusYesCountMinChange: vi.fn(),
    onRefresh: vi.fn(),
    onBacktest: vi.fn(),
    onRevaluate: vi.fn(),
    onExport: vi.fn(),
    ...overrides,
  }
}

function baseActivation(overrides: Partial<SignalActivationRow> = {}): SignalActivationRow {
  return {
    id: 1,
    today_fixture_id: 100,
    model_key: 'F',
    model_label: 'Modello F',
    scan_date: '2026-08-06',
    kickoff: null,
    match: 'Alpha vs Beta',
    country_name: 'Italy',
    league_name: 'Serie A',
    signal_group: 'DRAW',
    signal_label: 'X',
    source_column: 'EXCEL_D',
    target_market_label: 'X',
    evaluation_status: 'pending',
    evaluation_reason: null,
    ft_score: null,
    ht_score: null,
    quota_book: 3.2,
    quota_cecchino: 2.9,
    edge_pct: 5,
    rating: null,
    is_current: true,
    signal_formula_version: CURRENT_SIGNAL_FORMULA_VERSION,
    consensus_policy_version: 'cecchino_signal_consensus_v1_min_two',
    formula_source_mode: 'persisted_live_matrix',
    consensus_source_group: 'DRAW',
    consensus_eligible: true,
    consensus_available_count: 4,
    consensus_required_count: 2,
    consensus_yes_count: 2,
    consensus_yes_columns: ['EXCEL_D', 'EXCEL_E'],
    consensus_passed: true,
    is_acquired: true,
    acquisition_status: 'acquired_consensus',
    raw_signal_value: true,
    ...overrides,
  }
}

describe('Monitoraggio Segnali Lab — filtri formula/acquisition', () => {
  it('mostra gruppo Filtro Segnali Cecchino con default corrente/acquisiti', () => {
    render(<SignalsLabFilters {...filterProps()} />)

    expect(screen.getByText('Filtro Segnali Cecchino')).toBeTruthy()
    const formula = screen.getByLabelText('Formula') as HTMLSelectElement
    const acquisition = screen.getByLabelText('Acquisizione') as HTMLSelectElement
    expect(formula.value).toBe('current')
    expect(acquisition.value).toBe('acquired')
    expect(SIGNAL_FORMULA_VERSION_OPTIONS.map((o) => o.value)).toEqual([
      'current',
      'legacy',
      'all',
    ])
    expect(ACQUISITION_FILTER_OPTIONS.map((o) => o.label)).toEqual([
      'Segni acquisiti',
      'Consenso raggiunto',
      'Conferma insufficiente',
      'Segni 1/2 esenti',
      'Legacy non classificati',
      'Tutti i SI grezzi',
    ])
  })

  it('propaga cambi formula, acquisizione e conferme minime', () => {
    const onSignalFormulaVersionChange = vi.fn()
    const onAcquisitionFilterChange = vi.fn()
    const onConsensusYesCountMinChange = vi.fn()

    render(
      <SignalsLabFilters
        {...filterProps({
          onSignalFormulaVersionChange,
          onAcquisitionFilterChange,
          onConsensusYesCountMinChange,
        })}
      />,
    )

    fireEvent.change(screen.getByLabelText('Formula'), { target: { value: 'legacy' } })
    fireEvent.change(screen.getByLabelText('Acquisizione'), {
      target: { value: 'consensus_rejected' },
    })
    fireEvent.change(screen.getByLabelText('Conferme minime'), { target: { value: '2' } })

    expect(onSignalFormulaVersionChange).toHaveBeenCalledWith('legacy')
    expect(onAcquisitionFilterChange).toHaveBeenCalledWith('consensus_rejected')
    expect(onConsensusYesCountMinChange).toHaveBeenCalledWith(2)
  })

  it('include signal_formula_version e acquisition_filter nell’export URL', () => {
    const url = buildCecchinoSignalsExportUrl({
      date_from: '2026-08-01',
      date_to: '2026-08-06',
      model_key: 'F',
      signal_formula_version: 'current',
      acquisition_filter: 'acquired',
      consensus_yes_count_min: 2,
    })

    expect(url).toContain('signal_formula_version=current')
    expect(url).toContain('acquisition_filter=acquired')
    expect(url).toContain('consensus_yes_count_min=2')
    expect(url).toContain('/api/admin/cecchino/signals/export.csv')
  })

  it('usa default current/acquired se i filtri formula non sono valorizzati', () => {
    const url = buildCecchinoSignalsExportUrl({
      date_from: '2026-08-01',
      date_to: '2026-08-06',
    })
    expect(url).toContain('signal_formula_version=current')
    expect(url).toContain('acquisition_filter=acquired')
  })
})

describe('Monitoraggio Segnali Lab — badge activations', () => {
  it('mostra consenso 2/4 e badge Acquisito / Esente / Non acquisito', () => {
    const rows: SignalActivationRow[] = [
      baseActivation({
        id: 1,
        match: 'Match Consensus',
        consensus_yes_count: 2,
        consensus_available_count: 4,
        acquisition_status: 'acquired_consensus',
        is_acquired: true,
      }),
      baseActivation({
        id: 2,
        match: 'Match Esente',
        signal_group: 'HOME',
        signal_label: '1',
        consensus_yes_count: 1,
        consensus_available_count: 1,
        acquisition_status: 'acquired_single_formula_exempt',
        is_acquired: true,
      }),
      baseActivation({
        id: 3,
        match: 'Match Respinto',
        consensus_yes_count: 1,
        consensus_available_count: 4,
        acquisition_status: 'rejected_insufficient_consensus',
        is_acquired: false,
      }),
    ]

    render(<SignalsActivationsLab items={rows} onRowClick={vi.fn()} />)

    expect(screen.getByText('2/4')).toBeTruthy()
    expect(formatConsensusRatio(rows[0])).toBe('2/4')
    expect(screen.getAllByText('Acquisito').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('Esente 1/2')).toBeTruthy()
    expect(screen.getByText('Conferma insufficiente')).toBeTruthy()
    expect(screen.getByText('Non acquisito')).toBeTruthy()
    expect(acquisitionStatusLabel('acquired_single_formula_exempt')).toBe('Esente 1/2')
    expect(acquiredBadgeLabel(false)).toBe('Non acquisito')
  })

  it('drawer mostra campi consensus senza [object Object]', () => {
    const row = baseActivation({
      consensus_yes_columns: ['EXCEL_D', 'EXCEL_F'],
    })

    render(
      <MemoryRouter>
        <SignalsDetailDrawer
          state={{ type: 'activation', row }}
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    )

    expect(screen.getByText('Consenso / acquisizione')).toBeTruthy()
    expect(screen.getByText('2/4')).toBeTruthy()
    expect(screen.getByText('Excel D, Excel F')).toBeTruthy()
    expect(screen.queryByText('[object Object]')).toBeNull()
    expect(screen.getByText('cecchino_signal_consensus_v1_min_two')).toBeTruthy()
  })
})
