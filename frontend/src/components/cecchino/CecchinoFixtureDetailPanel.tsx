import type { CecchinoFixtureDetailResponse } from '../../lib/cecchinoApi'
import { canShowFinalOdds, getLeakageStatus } from '../../lib/cecchinoUtils'
import { CecchinoDataQualityBanner } from './CecchinoDataQualityBanner'
import { CecchinoDebugJsonPanel } from './CecchinoDebugJsonPanel'
import { CecchinoFinalOddsDashboard } from './CecchinoFinalOddsDashboard'
import { CecchinoInputDataPanel } from './CecchinoInputDataPanel'
import { CecchinoMatchBasics } from './CecchinoMatchBasics'
import { CecchinoKpiPanel } from './CecchinoKpiPanel'
import { CecchinoPicchettiDashboardTable } from './CecchinoPicchettiDashboardTable'
import { CecchinoSignalsMatrixPanel } from './CecchinoSignalsMatrixPanel'
import { CecchinoSignalsMatrixPlaceholder } from './CecchinoSignalsMatrixPlaceholder'
import { CecchinoStatusMessage } from './CecchinoStatusMessage'

type Props = {
  detail: CecchinoFixtureDetailResponse
}

export function CecchinoFixtureDetailPanel({ detail }: Props) {
  const leakageFailed = getLeakageStatus(detail.data_quality) === 'failed'
  const calcStatus = detail.calculation_status
  const output = detail.output
  const showOutput = detail.status === 'ok' && output != null && canShowFinalOdds(calcStatus)

  if (detail.status !== 'ok') {
    return (
      <div className="space-y-4">
        <CecchinoMatchBasics detail={detail} />
        <CecchinoStatusMessage
          title="Dettaglio non disponibile"
          code={detail.code}
          message={detail.message ?? 'Risposta API non valida.'}
          variant="error"
        />
        <CecchinoDebugJsonPanel detail={detail} />
      </div>
    )
  }

  if (leakageFailed) {
    return (
      <div className="space-y-4">
        <CecchinoMatchBasics detail={detail} />
        <CecchinoStatusMessage
          title="Calcolo bloccato — leakage check failed"
          message="I dati storici non superano il controllo anti-leakage. Nessuna quota mostrata."
          variant="error"
        />
        <CecchinoDataQualityBanner
          dataQuality={detail.data_quality}
          calculationStatus={calcStatus}
        />
        <CecchinoInputDataPanel inputSnapshot={detail.input_snapshot} dataQuality={detail.data_quality} />
        <CecchinoDebugJsonPanel detail={detail} />
      </div>
    )
  }

  if (calcStatus === 'insufficient_data') {
    return (
      <div className="space-y-4">
        <CecchinoMatchBasics detail={detail} />
        <CecchinoDataQualityBanner dataQuality={detail.data_quality} calculationStatus={calcStatus} />
        <CecchinoStatusMessage
          title="Dati insufficienti"
          message="Non ci sono abbastanza partite precedenti per calcolare quote affidabili. Le tabelle quote non vengono mostrate."
          variant="warning"
        />
        <CecchinoInputDataPanel inputSnapshot={detail.input_snapshot} dataQuality={detail.data_quality} />
        <CecchinoDebugJsonPanel detail={detail} />
      </div>
    )
  }

  if (calcStatus === 'error' || !output) {
    return (
      <div className="space-y-4">
        <CecchinoMatchBasics detail={detail} />
        <CecchinoStatusMessage
          title="Errore calcolo Cecchino"
          code={detail.code}
          message={detail.message ?? 'Output mancante o stato error.'}
          variant="error"
        />
        <CecchinoDataQualityBanner dataQuality={detail.data_quality} calculationStatus={calcStatus} />
        <CecchinoInputDataPanel inputSnapshot={detail.input_snapshot} dataQuality={detail.data_quality} />
        <CecchinoDebugJsonPanel detail={detail} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <CecchinoMatchBasics detail={detail} />
      <CecchinoDataQualityBanner dataQuality={detail.data_quality} calculationStatus={calcStatus} />
      <CecchinoInputDataPanel inputSnapshot={detail.input_snapshot} dataQuality={detail.data_quality} />

      {showOutput && (
        <>
          <CecchinoPicchettiDashboardTable picchetti={output.picchetti} />
          <CecchinoFinalOddsDashboard final={output.final} />
        </>
      )}

      {calcStatus === 'partial_low_sample' && (
        <CecchinoStatusMessage
          title="Campione parziale"
          message="Le quote sono calcolate ma almeno un contesto ha meno partite del target (warning low_sample)."
          variant="warning"
        />
      )}

      {output.signals_matrix?.status === 'available' ? (
        <CecchinoSignalsMatrixPanel matrix={output.signals_matrix} />
      ) : (
        <CecchinoSignalsMatrixPlaceholder status={output.signals_matrix?.status} />
      )}
      {(detail.kpi_panel || output.kpi_panel) ? (
        <CecchinoKpiPanel
          panel={(detail.kpi_panel || output.kpi_panel)!}
          bookmakerStatus={output.bookmaker_comparison?.status}
        />
      ) : null}
      <CecchinoDebugJsonPanel detail={detail} />
    </div>
  )
}
