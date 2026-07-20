import { useMemo, useState } from 'react'
import type { BalanceReadinessDecisionContract } from '../../../lib/cecchinoModuleMonitoringApi'
import {
  BALANCE_V5_GOVERNANCE_DECISION_CONFIRM,
  recordBalanceGovernanceDecision,
} from '../../../lib/cecchinoModuleMonitoringApi'
import { CARD_BASE } from '../moduleMonitoringUi'

type Props = {
  contract: BalanceReadinessDecisionContract | null
}

export function BalanceGovernanceDecisionPanel({ contract }: Props) {
  const [selectedDecision, setSelectedDecision] = useState('')
  const [reason, setReason] = useState('')
  const [confirmToken, setConfirmToken] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<string | null>(null)

  const options = useMemo(() => {
    const allowed = new Set(contract?.allowed_now || [])
    const decisions = contract?.decisions || {}
    return Object.entries(decisions)
      .filter(([key, meta]) => allowed.has(key) && meta?.allowed !== false)
      .map(([key, meta]) => ({
        key,
        label: meta?.label_it || key,
      }))
  }, [contract])

  if (!contract) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedDecision) {
      alert('Seleziona una decisione')
      return
    }
    if (confirmToken !== BALANCE_V5_GOVERNANCE_DECISION_CONFIRM) {
      alert('Token di conferma non valido')
      return
    }

    setSubmitting(true)
    setResult(null)
    try {
      await recordBalanceGovernanceDecision({
        decision: selectedDecision,
        decision_reason: reason || undefined,
        confirm: confirmToken,
      })
      setResult('Decisione registrata con successo.')
      setSelectedDecision('')
      setReason('')
      setConfirmToken('')
    } catch (err: unknown) {
      setResult(`Errore: ${(err as Error)?.message || 'Errore sconosciuto'}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className={`${CARD_BASE} border-violet-200 bg-violet-50/30 p-4`}>
      <h4 className="text-sm font-semibold text-slate-800">Decisioni di governance</h4>
      <p className="mt-1 text-xs text-slate-600">
        Ammesse nello Step 2C: continue_monitoring, freeze_as_descriptive,
        request_formula_review. Le decisioni Signals richiedono implementazione separata.
      </p>

      {options.length === 0 ? (
        <p className="mt-3 text-sm text-slate-600">Nessuna decisione ammessa nel contratto.</p>
      ) : (
        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <div>
            <label htmlFor="decision-select" className="block text-xs font-medium text-slate-700">
              Decisione
            </label>
            <select
              id="decision-select"
              value={selectedDecision}
              onChange={(e) => setSelectedDecision(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              disabled={submitting}
            >
              <option value="">— Seleziona —</option>
              {options.map((d) => (
                <option key={d.key} value={d.key}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="reason-input" className="block text-xs font-medium text-slate-700">
              Motivazione (opzionale)
            </label>
            <textarea
              id="reason-input"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              disabled={submitting}
            />
          </div>

          <div>
            <label htmlFor="confirm-token" className="block text-xs font-medium text-slate-700">
              Token di conferma
            </label>
            <input
              id="confirm-token"
              type="text"
              value={confirmToken}
              onChange={(e) => setConfirmToken(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm"
              placeholder="CONFIRM_BALANCE_V5_GOVERNANCE_DECISION"
              disabled={submitting}
            />
          </div>

          <button
            type="submit"
            disabled={!selectedDecision || submitting}
            className="rounded-lg border border-violet-600 bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? 'Registrazione…' : 'Registra decisione'}
          </button>

          {result ? (
            <p
              className={`rounded-lg border px-3 py-2 text-sm ${
                result.startsWith('Errore')
                  ? 'border-rose-200 bg-rose-50 text-rose-800'
                  : 'border-emerald-200 bg-emerald-50 text-emerald-800'
              }`}
            >
              {result}
            </p>
          ) : null}
        </form>
      )}

      {contract.notes && contract.notes.length > 0 ? (
        <ul className="mt-3 space-y-1 border-t border-violet-200/50 pt-3 text-xs text-slate-600">
          {contract.notes.map((note) => (
            <li key={note}>• {note}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
