type Props = {
  value: number | null
  size?: number
  stroke?: number
  color?: string
  track?: string
  label?: string
}

export function MonitoringProgressRing({
  value,
  size = 56,
  stroke = 6,
  color = '#0891b2',
  track = '#e2e8f0',
  label,
}: Props) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const known = value != null && !Number.isNaN(value)
  const pct = known ? Math.max(0, Math.min(1, value)) : 0
  const offset = c * (1 - pct)

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
        {known ? (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeDasharray={c}
            strokeDashoffset={offset}
            strokeLinecap="round"
          />
        ) : null}
      </svg>
      <span className="absolute text-[11px] font-semibold text-slate-700">
        {label ?? (known ? `${Math.round(pct * 100)}%` : '—')}
      </span>
    </div>
  )
}
