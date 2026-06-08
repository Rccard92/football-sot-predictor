import { Link } from 'react-router-dom'
import type { CecchinoSignalsMatrix } from '../../lib/cecchinoApi'
import { CecchinoSignalsMatrixPanel } from './CecchinoSignalsMatrixPanel'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

type Props = {
  matrix: CecchinoSignalsMatrix
  scanDate?: string | null
  todayFixtureId?: number | null
}

export function CecchinoSignalsCard({ matrix, scanDate, todayFixtureId }: Props) {
  const monitoringHref =
    scanDate != null
      ? `/monitoraggio-segnali?date_from=${encodeURIComponent(scanDate)}&date_to=${encodeURIComponent(scanDate)}${
          todayFixtureId != null ? `&today_fixture_id=${todayFixtureId}` : ''
        }`
      : '/monitoraggio-segnali'

  return (
    <section className={`${todayCard} ${todayCardPadding} h-full space-y-4`}>
      <div>
        <h3 className={todaySectionTitle}>Segnali Cecchino</h3>
        <p className={todaySectionSubtitle}>Matrice SI/NO</p>
        <p className="mt-2 text-xs text-slate-500">
          Questi segnali vengono salvati nel Monitoraggio Segnali e valutati dopo
          l&apos;aggiornamento risultati.
        </p>
        <Link
          to={monitoringHref}
          className="mt-1 inline-block text-xs font-medium text-sky-700 hover:underline"
        >
          Apri monitoraggio segnali
        </Link>
      </div>
      <CecchinoSignalsMatrixPanel matrix={matrix} variant="embedded" />
    </section>
  )
}
