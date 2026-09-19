import { V4_VIEWS, V4_VIEW_LABELS, type V4View } from './constants'

type Props = {
  view: V4View
  onChange: (view: V4View) => void
}

export function V4ViewSwitch({ view, onChange }: Props) {
  return (
    <div
      className="inline-flex max-w-full overflow-x-auto rounded-xl border border-slate-200 bg-slate-100/80 p-1 shadow-sm"
      role="tablist"
      aria-label="Viste Cecchino V4"
      data-testid="v4-view-switch"
    >
      {V4_VIEWS.map((v) => {
        const active = v === view
        return (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={active}
            data-testid={`v4-view-${v}`}
            className={`min-h-11 whitespace-nowrap rounded-lg px-4 text-base font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 ${
              active ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
            onClick={() => onChange(v)}
          >
            {V4_VIEW_LABELS[v]}
          </button>
        )
      })}
    </div>
  )
}
