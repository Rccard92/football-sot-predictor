import type { CecchinoFinalOdds } from '../../lib/cecchinoApi'
import { CecchinoFinalOddsDashboard } from './CecchinoFinalOddsDashboard'
import { todayCard, todayCardPadding, todaySectionSubtitle, todaySectionTitle } from './cecchinoTodayStyles'

type Props = {
  final: CecchinoFinalOdds
}

export function CecchinoTodayFinalOddsCard({ final }: Props) {
  return (
    <section className={`${todayCard} ${todayCardPadding} h-full space-y-4`}>
      <div>
        <h3 className={todaySectionTitle}>Quote finali Cecchino</h3>
        <p className={todaySectionSubtitle}>Quota matematica ponderata</p>
      </div>
      <CecchinoFinalOddsDashboard final={final} variant="embedded" />
    </section>
  )
}
