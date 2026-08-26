/**
 * Copy Balance V5 — kickoff mismatch: current_strict vs historical_snapshot.
 */
import { describe, expect, it } from 'vitest'
import { blockedAlertMessage } from './CecchinoBalanceV5Panel'
import type { CecchinoBalanceV5SnapshotMeta } from '../../lib/cecchinoTodayApi'

describe('CecchinoBalanceV5Panel blockedAlertMessage kickoff copy', () => {
  it('usa copy current_strict per today_local_kickoff_mismatch', () => {
    const meta: CecchinoBalanceV5SnapshotMeta = {
      mode: 'current_strict',
      warnings: ['today_local_kickoff_mismatch'],
    }
    expect(blockedAlertMessage(meta)).toBe(
      'Dati partita non coerenti: il kickoff locale non è allineato alla programmazione corrente.',
    )
  })

  it('usa Snapshot storico solo in historical_snapshot', () => {
    const meta: CecchinoBalanceV5SnapshotMeta = {
      mode: 'historical_snapshot',
      warnings: ['historical_target_kickoff_mismatch'],
    }
    expect(blockedAlertMessage(meta)).toBe('Snapshot storico bloccato: kickoff non coerente.')
  })
})
