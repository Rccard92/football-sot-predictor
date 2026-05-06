import type { AuditResponse } from './types'
import { buildMainDrivers } from './mapping'

function badgeForDir(dir: 'increase' | 'decrease' | 'neutral' | 'info' | 'missing') {
  if (dir === 'increase') return 'bg-emerald-50 text-emerald-900 ring-emerald-200'
  if (dir === 'decrease') return 'bg-rose-50 text-rose-900 ring-rose-200'
  if (dir === 'neutral') return 'bg-slate-100 text-slate-800 ring-slate-200'
  if (dir === 'missing') return 'bg-slate-100 text-slate-600 ring-slate-200'
  return 'bg-blue-50 text-blue-900 ring-blue-200'
}

function labelForDir(dir: 'increase' | 'decrease' | 'neutral' | 'info' | 'missing') {
  if (dir === 'increase') return 'Aumenta'
  if (dir === 'decrease') return 'Diminuisce'
  if (dir === 'neutral') return 'Neutrale'
  if (dir === 'missing') return 'Mancante'
  return 'Info'
}

function badgeForImpact(i: 'alto' | 'medio' | 'basso') {
  if (i === 'alto') return 'bg-slate-900 text-white ring-slate-900'
  if (i === 'medio') return 'bg-slate-700 text-white ring-slate-700'
  return 'bg-slate-100 text-slate-800 ring-slate-200'
}

export function MainDriversPanel({ data }: { data: AuditResponse }) {
  const drivers = buildMainDrivers(data)

  return (
    <section className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Driver principali</h2>
          <p className="mt-2 text-sm text-slate-600">
            Sintesi interpretativa generata in frontend (non cambia formule né predizioni).
          </p>
        </div>
        <p className="text-xs text-slate-500">{drivers.length} driver</p>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {drivers.map((d) => (
          <article key={d.id} className="rounded-2xl border border-slate-200 bg-slate-50/40 p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="text-sm font-semibold text-slate-900">{d.title}</p>
              <div className="flex items-center gap-2 text-xs">
                <span className={`rounded-full px-2 py-0.5 font-medium ring-1 ${badgeForDir(d.direction)}`}>
                  {labelForDir(d.direction)}
                </span>
                <span className={`rounded-full px-2 py-0.5 font-medium ring-1 ${badgeForImpact(d.impact)}`}>
                  Impatto {d.impact}
                </span>
              </div>
            </div>
            <p className="mt-2 text-xs text-slate-600">{d.explanation}</p>
          </article>
        ))}
      </div>
    </section>
  )
}

