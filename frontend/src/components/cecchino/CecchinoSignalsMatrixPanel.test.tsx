/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { CecchinoSignalsMatrixPanel } from './CecchinoSignalsMatrixPanel'
import type { CecchinoSignalsMatrix } from '../../lib/cecchinoApi'
import {
  CURRENT_SIGNAL_FORMULA_VERSION,
  SIGNAL_FORMULA_CURRENT_BADGE,
} from '../../lib/cecchinoSignalsApi'

afterEach(() => {
  cleanup()
})

function matrixWithConsensus(opts: {
  formulaVersion?: string | null
  status?: string
  drawSignals?: Record<string, string>
  consensus?: {
    is_acquired: boolean
    acquisition_status: string
    consensus_yes_count: number
    consensus_required_count: number
    consensus_available_count: number
    consensus_yes_columns: string[]
  }
}): CecchinoSignalsMatrix {
  return {
    status: opts.status ?? 'available',
    source: 'test',
    formula_version: opts.formulaVersion === undefined ? CURRENT_SIGNAL_FORMULA_VERSION : opts.formulaVersion,
    consensus_policy_version: 'cecchino_signal_consensus_v1_min_two',
    rows: [
      {
        key: 'draw',
        label: 'SEGNO X',
        signals: {
          excel_d: opts.drawSignals?.excel_d ?? 'SI',
          excel_e: opts.drawSignals?.excel_e ?? 'SI',
          excel_f: 'NO',
          excel_g: 'NO',
        },
        consensus: opts.consensus ?? {
          is_acquired: true,
          acquisition_status: 'acquired_consensus',
          consensus_yes_count: 2,
          consensus_required_count: 2,
          consensus_available_count: 4,
          consensus_yes_columns: ['EXCEL_D', 'EXCEL_E'],
        },
      },
    ],
  } as CecchinoSignalsMatrix
}

describe('CecchinoSignalsMatrixPanel V3', () => {
  it('mostra badge Formula corrente V3 e acquisito 2/4', () => {
    render(
      <CecchinoSignalsMatrixPanel
        matrix={matrixWithConsensus({})}
        signalContract={{
          formula_version: CURRENT_SIGNAL_FORMULA_VERSION,
          formula_label: 'Formula corrente V3',
          is_current_formula: true,
          consensus_policy_version: 'cecchino_signal_consensus_v1_min_two',
          audit_version: 'cecchino_signal_explanations_v3',
          operational_semantics: 'acquired_only',
          matrix_status: 'available',
        }}
      />,
    )
    expect(screen.getByText(SIGNAL_FORMULA_CURRENT_BADGE)).toBeTruthy()
    expect(screen.getByText(/Acquisito/i)).toBeTruthy()
  })

  it('mostra warning archivio per matrice V2', () => {
    render(
      <CecchinoSignalsMatrixPanel
        matrix={matrixWithConsensus({
          formulaVersion: 'cecchino_signals_matrix_v2_draw_dfg',
          consensus: {
            is_acquired: false,
            acquisition_status: 'rejected_insufficient_consensus',
            consensus_yes_count: 2,
            consensus_required_count: 2,
            consensus_available_count: 4,
            consensus_yes_columns: ['EXCEL_D', 'EXCEL_E'],
          },
        })}
        signalContract={{
          formula_version: CURRENT_SIGNAL_FORMULA_VERSION,
          formula_label: 'Formula corrente V3',
          is_current_formula: false,
          consensus_policy_version: 'cecchino_signal_consensus_v1_min_two',
          detected_formula_version: 'cecchino_signals_matrix_v2_draw_dfg',
          reason_code: 'signal_matrix_formula_version_not_current',
          matrix_status: 'available',
        }}
      />,
    )
    expect(screen.getByText(/storica non corrente|esclusa dai flussi operativi/i)).toBeTruthy()
    expect(screen.queryByText(SIGNAL_FORMULA_CURRENT_BADGE)).toBeNull()
  })
})
