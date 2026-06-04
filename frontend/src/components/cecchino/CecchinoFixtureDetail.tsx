import type { CecchinoFixtureDetailResponse } from '../../lib/api'
import { CecchinoDataQualityBanner } from './CecchinoDataQualityBanner'
import { CecchinoInputDataPanel } from './CecchinoInputDataPanel'
import { CecchinoFinalOddsCard } from './CecchinoFinalOddsCard'
import { CecchinoOddsComparisonPlaceholder } from './CecchinoOddsComparisonPlaceholder'
import { CecchinoPicchettiTable } from './CecchinoPicchettiTable'
import { CecchinoSignalsMatrixPlaceholder } from './CecchinoSignalsMatrixPlaceholder'

type Props = {
  detail: CecchinoFixtureDetailResponse
}

export function CecchinoFixtureDetail({ detail }: Props) {
  const output = detail.output
  if (!output) {
    return <p className="text-sm text-slate-600">Nessun output disponibile.</p>
  }

  return (
    <div className="space-y-4">
      <CecchinoDataQualityBanner
        dataQuality={detail.data_quality}
        calculationStatus={detail.calculation_status}
      />
      <CecchinoInputDataPanel
        inputSnapshot={detail.input_snapshot}
        dataQuality={detail.data_quality}
      />

      {detail.warnings.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <p className="font-semibold">Warning</p>
          <ul className="mt-1 list-inside list-disc">
            {detail.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <CecchinoPicchettiTable picchetti={output.picchetti} />
      <CecchinoFinalOddsCard final={output.final} />
      <CecchinoSignalsMatrixPlaceholder status={output.signals_matrix?.status} />
      <CecchinoOddsComparisonPlaceholder status={output.bookmaker_comparison?.status} />
    </div>
  )
}
