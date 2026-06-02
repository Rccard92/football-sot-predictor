import { useState } from 'react'
import { Card } from '../ui/Card'
import { postRoundAnalysisAnalyze, type RoundAnalysisDetail } from '../../lib/api'

type Props = {
  competitionId: number | null
  seasonYear: number
  seasonLabel: string
  firstRecommendedRound: number | null
  onAnalyzed: (detail: RoundAnalysisDetail) => void
  onReloadList: () => void
}

export function RoundAnalysisForm({
  competitionId,
  seasonYear,
  seasonLabel,
  firstRecommendedRound,
  onAnalyzed,
  onReloadList,
}: Props) {
  const [roundNumber, setRoundNumber] = useState(36)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [forceRecalculate, setForceRecalculate] = useState(false)

  const run = async (force: boolean) => {
    if (competitionId == null) {
      setError('Seleziona un campionato.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const { analysis } = await postRoundAnalysisAnalyze({
        competition_id: competitionId,
        season_year: seasonYear,
        round_number: roundNumber,
        force_recalculate: force,
        models: [
          'baseline_v1_1',
          'baseline_v2_0_lineup_impact',
          'baseline_v2_1_weighted_components',
          'baseline_v3_0_sot_value_selector',
        ],
      })
      onAnalyzed(analysis)
      onReloadList()
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.includes('409') || msg.includes('analysis_already_completed')) {
        setError('Analisi già presente per questa giornata. Usa «Rianalizza giornata».')
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
      setForceRecalculate(false)
    }
  }

  return (
    <Card title="Analizza giornata">
      <div className="space-y-4 text-sm text-slate-700">
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span className="font-medium text-slate-800">Giornata</span>
            <input
              type="number"
              min={1}
              max={50}
              className="rounded-lg border border-slate-200 px-3 py-2"
              value={roundNumber}
              onChange={(e) => setRoundNumber(Number(e.target.value))}
            />
            <span className="text-xs text-slate-500">
              Le prime giornate possono avere storico insufficiente. Per risultati più affidabili,
              analizza anche giornate dalla 3/4 in poi.
            </span>
            {firstRecommendedRound != null ? (
              <span className="text-xs font-medium text-slate-700">
                Prima giornata consigliata: {firstRecommendedRound}
              </span>
            ) : null}
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-medium text-slate-800">Stagione</span>
            <input
              type="text"
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
              value={seasonLabel}
              readOnly
            />
          </label>
          <div className="flex items-end gap-2">
            <button
              type="button"
              disabled={loading || competitionId == null}
              onClick={() => void run(false)}
              className="rounded-lg bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-50"
            >
              {loading && !forceRecalculate ? 'Analisi in corso…' : 'Analizza giornata'}
            </button>
            <button
              type="button"
              disabled={loading || competitionId == null}
              onClick={() => {
                setForceRecalculate(true)
                void run(true)
              }}
              className="rounded-lg border border-slate-300 px-4 py-2 font-medium text-slate-800 disabled:opacity-50"
            >
              Rianalizza giornata
            </button>
          </div>
        </div>

        <button
          type="button"
          className="text-slate-600 underline"
          onClick={() => setShowAdvanced((v) => !v)}
        >
          {showAdvanced ? 'Nascondi opzioni avanzate' : 'Opzioni avanzate'}
        </button>
        {showAdvanced ? (
          <p className="text-xs text-slate-500">
            Confronto automatico v1.1, v2.0 e v2.1 con linee Over e filtri consiglio standard.
          </p>
        ) : null}

        {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      </div>
    </Card>
  )
}
