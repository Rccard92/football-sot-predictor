/**
 * Tipi condivisi della matrice segnali Cecchino (usati da Cecchino Today e Bet Builder).
 */

export type CecchinoReliability = {
  sample?: number | null
  index?: number | null
  status?: string | null
  level?: string | null
}

export type CecchinoSignalDecimalPolicy = {
  scope?: string
  quantum?: string
  rounding?: string
}

export type CecchinoSignalRowConsensus = {
  consensus_policy_version?: string | null
  consensus_eligible?: boolean | null
  consensus_available_count?: number | null
  consensus_required_count?: number | null
  consensus_yes_count?: number | null
  consensus_yes_columns?: string[] | null
  consensus_passed?: boolean | null
  acquisition_status?: string | null
  is_acquired?: boolean | null
  consensus_source_group?: string | null
}

export type CecchinoSignalRow = {
  key: string
  label: string
  signals: Record<string, string>
  consensus?: CecchinoSignalRowConsensus | null
}

export type CecchinoSignalContract = {
  formula_version?: string
  formula_label?: string
  consensus_policy_version?: string
  audit_version?: string
  decimal_policy?: CecchinoSignalDecimalPolicy
  operational_signal_semantics?: string
  operational_semantics?: string
  legacy_versions_operational?: boolean
  is_current_formula?: boolean
  matrix_status?: string | null
  detected_formula_version?: string | null
  reason_code?: string | null
}

export type CecchinoSignalsMatrix = {
  status: string
  source?: string
  formula_version?: string | null
  consensus_policy_version?: string | null
  excel_mapping?: Record<string, string>
  inputs?: {
    q1?: number | null
    qx?: number | null
    q2?: number | null
    avg_q?: number | null
    diff_1_2?: number | null
  }
  rows?: CecchinoSignalRow[]
  reliability?: CecchinoReliability
  warnings?: string[]
}
