import type { PatternLabPreset } from '../../../lib/patternLabApi'

type Props = {
  presets: PatternLabPreset[]
  activePresetId: string | null
  presetModified: boolean
  disabled?: boolean
  onApply: (preset: PatternLabPreset) => void
  onClear: () => void
}

export function PatternLabPresets({
  presets,
  activePresetId,
  presetModified,
  disabled,
  onApply,
  onClear,
}: Props) {
  return (
    <section className="lab-card rounded-xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-semibold">Preset pattern</h3>
          <p className="mt-1 text-xs" style={{ color: 'var(--lab-muted)' }}>
            Filtri scientifici congelati. Le metriche ROI restano su quote Bet365 reali
            (policy separata, non parte della formula).
          </p>
        </div>
        {(activePresetId || presetModified) && (
          <button
            type="button"
            className="lab-btn-ghost rounded-md border px-3 py-1.5 text-xs"
            style={{ borderColor: 'var(--lab-border)' }}
            disabled={disabled}
            onClick={onClear}
          >
            Rimuovi preset / Reset
          </button>
        )}
      </div>
      {presetModified && activePresetId && (
        <div className="mt-2 text-xs font-medium" style={{ color: 'var(--lab-warning, #b45309)' }}>
          Preset modificato — i filtri non coincidono più con {activePresetId}
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {presets.map((p) => {
          const active = activePresetId === p.id && !presetModified
          const soft = activePresetId === p.id && presetModified
          return (
            <button
              key={p.id}
              type="button"
              disabled={disabled}
              title={p.description || p.notes || p.label}
              onClick={() => onApply(p)}
              className={`max-w-full rounded-lg border px-3 py-2 text-left text-xs transition ${
                active ? 'lab-tab-active' : ''
              }`}
              style={{
                borderColor: active
                  ? 'var(--lab-accent, var(--lab-border))'
                  : 'var(--lab-border)',
                opacity: soft ? 0.75 : 1,
              }}
            >
              <div className="font-medium">{p.label}</div>
              <div className="mt-0.5" style={{ color: 'var(--lab-muted)' }}>
                {p.ui_badge || p.status}
                {active ? ' · attivo' : soft ? ' · modificato' : ''}
              </div>
            </button>
          )
        })}
        {!presets.length && (
          <span className="text-xs" style={{ color: 'var(--lab-muted)' }}>
            Nessun preset caricato.
          </span>
        )}
      </div>
    </section>
  )
}
