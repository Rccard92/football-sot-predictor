type Tone = 'default' | 'ok' | 'warn' | 'danger'

const TONE_COLORS: Record<Tone, string | undefined> = {
  default: undefined,
  ok: 'var(--lab-cyan)',
  warn: '#fcd34d',
  danger: '#fca5a5',
}

export function RunV2Stat({
  label,
  value,
  tone = 'default',
}: {
  label: string
  value: string
  tone?: Tone
}) {
  return (
    <div className="rounded-md border px-3 py-2" style={{ borderColor: 'var(--lab-border)' }}>
      <div className="text-xs" style={{ color: 'var(--lab-muted)' }}>
        {label}
      </div>
      <div className="font-semibold" style={{ color: TONE_COLORS[tone] }}>
        {value}
      </div>
    </div>
  )
}
