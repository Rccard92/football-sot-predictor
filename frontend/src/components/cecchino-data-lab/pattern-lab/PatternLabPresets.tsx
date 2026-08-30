import type { PatternLabPreset } from '../../../lib/patternLabApi'
import { derivePresetStatusGroup } from '../../../lib/patternLabApi'

type Props = {
  presets: PatternLabPreset[]
  activePresetId: string | null
  presetModified: boolean
  disabled?: boolean
  onApply: (preset: PatternLabPreset) => void
  onClear: () => void
}

const GROUP_STYLE: Record<string, { border: string; badge: string }> = {
  positive_weak: {
    border: 'var(--lab-success, #15803d)',
    badge: 'var(--lab-success, #15803d)',
  },
  mixed: {
    border: 'var(--lab-warning, #b45309)',
    badge: 'var(--lab-warning, #b45309)',
  },
  failed_oos: {
    border: 'var(--lab-danger, #b91c1c)',
    badge: 'var(--lab-danger, #b91c1c)',
  },
  candidate_new: {
    border: 'var(--lab-accent, #1d4ed8)',
    badge: 'var(--lab-accent, #1d4ed8)',
  },
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
            Filtri scientifici congelati (ordine registry, non per ROI). I falliti OOS restano
            visibili. Metriche ROI su quote Bet365 reali (policy separata).
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
          const group =
            p.status_group || derivePresetStatusGroup(p.status)
          const style = GROUP_STYLE[group] || GROUP_STYLE.mixed
          const longshot =
            p.flags?.longshot_pattern || p.flags?.high_variance
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
                borderColor: active ? style.border : 'var(--lab-border)',
                opacity: soft ? 0.75 : 1,
              }}
            >
              <div className="font-medium">{p.label}</div>
              <div className="mt-0.5" style={{ color: style.badge }}>
                {p.ui_badge || p.status}
                {longshot ? ' · longshot' : ''}
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
