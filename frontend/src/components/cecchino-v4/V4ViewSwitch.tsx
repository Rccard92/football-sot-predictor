import { V4_VIEWS, V4_VIEW_LABELS, v4FilterChip, v4FilterChipOff, v4FilterChipOn, type V4View } from './constants'

type Props = {
  view: V4View
  onChange: (view: V4View) => void
}

/** Quattro viste come chip compatti, stessa grafica dei filtri di Cecchino Today. */
export function V4ViewSwitch({ view, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2" role="tablist" aria-label="Viste Cecchino V4" data-testid="v4-view-switch">
      {V4_VIEWS.map((v) => {
        const active = v === view
        return (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={active}
            data-testid={`v4-view-${v}`}
            className={`${v4FilterChip} ${active ? v4FilterChipOn : v4FilterChipOff} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400`}
            onClick={() => onChange(v)}
          >
            {V4_VIEW_LABELS[v]}
          </button>
        )
      })}
    </div>
  )
}
