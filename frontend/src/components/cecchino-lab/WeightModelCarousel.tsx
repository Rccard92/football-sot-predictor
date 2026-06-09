import type { WeightModelSummary } from '../../lib/cecchinoSignalsApi'
import { ModelPerformanceCard } from './ModelPerformanceCard'

type Props = {
  models: WeightModelSummary[]
  selectedModelKey: string
  onSelect: (key: string) => void
}

export function WeightModelCarousel({ models, selectedModelKey, onSelect }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm backdrop-blur-sm">
      <h2 className="text-sm font-semibold text-slate-800">Confronto modelli pesi</h2>
      <p className="mt-1 text-xs text-slate-500">
        Backtest comparativo offline — non modifica il Cecchino Today live.
      </p>
      <div className="mt-4 hidden gap-3 xl:grid xl:grid-cols-6">
        {models.map((model, index) => (
          <ModelPerformanceCard
            key={model.model_key}
            model={model}
            selected={model.model_key === selectedModelKey}
            index={index}
            onSelect={onSelect}
          />
        ))}
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-3 xl:hidden">
        {models.map((model, index) => (
          <ModelPerformanceCard
            key={model.model_key}
            model={model}
            selected={model.model_key === selectedModelKey}
            index={index}
            onSelect={onSelect}
          />
        ))}
      </div>
      <div className="mt-4 flex gap-3 overflow-x-auto pb-2 snap-x snap-mandatory md:hidden">
        {models.map((model, index) => (
          <ModelPerformanceCard
            key={model.model_key}
            model={model}
            selected={model.model_key === selectedModelKey}
            index={index}
            onSelect={onSelect}
          />
        ))}
      </div>
    </section>
  )
}
