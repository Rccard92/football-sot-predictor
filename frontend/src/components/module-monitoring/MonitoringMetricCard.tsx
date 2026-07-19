import { motion } from 'framer-motion'
import { CARD_BASE, MOTION_FAST } from './moduleMonitoringUi'

type Props = {
  label: string
  value: string
  hint?: string
  icon?: React.ReactNode
  footer?: React.ReactNode
  ariaLabel?: string
}

export function MonitoringMetricCard({ label, value, hint, icon, footer, ariaLabel }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={MOTION_FAST}
      className={`${CARD_BASE} px-4 py-3`}
      aria-label={ariaLabel}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
        {icon ? <div className="text-slate-400">{icon}</div> : null}
      </div>
      <div className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{value}</div>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
      {footer}
    </motion.div>
  )
}
