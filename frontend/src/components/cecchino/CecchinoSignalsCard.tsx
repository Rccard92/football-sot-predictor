import type { CecchinoSignalsMatrix } from '../../lib/cecchinoApi'
import { CecchinoSignalsMatrixPanel } from './CecchinoSignalsMatrixPanel'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

type Props = {
  matrix: CecchinoSignalsMatrix
}

export function CecchinoSignalsCard({ matrix }: Props) {
  return (
    <section className={`${todayCard} ${todayCardPadding} h-full space-y-4`}>
      <div>
        <h3 className={todaySectionTitle}>Segnali Cecchino</h3>
        <p className={todaySectionSubtitle}>Matrice SI/NO</p>
      </div>
      <CecchinoSignalsMatrixPanel matrix={matrix} variant="embedded" />
    </section>
  )
}
