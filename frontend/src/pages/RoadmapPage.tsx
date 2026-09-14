import { PatternInsightsShell, Section } from '../components/pattern-insights/PatternInsightsShell'
import {
  ROADMAP_RULES,
  ROADMAP_STEPS,
  ROADMAP_UPDATES,
  type RoadmapStatus,
} from '../config/roadmap'

const TEXT_MUTED = 'var(--pi-muted)'

const STATUS: Record<RoadmapStatus, { label: string; color: string; mark: string }> = {
  da_fare: { label: 'Da fare', color: 'var(--pi-border)', mark: '○' },
  in_corso: { label: 'In corso', color: 'var(--pi-warn)', mark: '◐' },
  fatto: { label: 'Fatto', color: 'var(--pi-pos)', mark: '●' },
}

function StatusChip({ status }: { status: RoadmapStatus }) {
  const s = STATUS[status]
  return (
    <span
      className="whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-semibold"
      style={{ border: `1px solid ${s.color}` }}
    >
      <span style={{ color: s.color }}>{s.mark}</span> {s.label}
    </span>
  )
}

export function RoadmapPage() {
  const done = ROADMAP_STEPS.filter((s) => s.status === 'fatto').length
  const current = ROADMAP_STEPS.find((s) => s.status === 'in_corso')
  return (
    <PatternInsightsShell>
      <header className="mb-5">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-bold tracking-tight">Roadmap Cecchino · V2 · V2.5 · V3</h1>
          <span className="pi-chip">
            {done} di {ROADMAP_STEPS.length} step completati
          </span>
          {current ? <span className="pi-chip">In corso: step {current.id}</span> : null}
        </div>
        <p className="mt-2 max-w-4xl text-xs leading-relaxed" style={{ color: TEXT_MUTED }}>
          Piano di sviluppo concordato. Aggiornato a ogni rilascio su staging.
        </p>
      </header>

      <div className="space-y-4">
        <Section title="Regole fisse">
          <ul className="list-disc space-y-1 pl-5 text-xs leading-relaxed">
            {ROADMAP_RULES.map((rule) => (
              <li key={rule}>{rule}</li>
            ))}
          </ul>
        </Section>

        {ROADMAP_STEPS.map((step) => (
          <Section
            key={step.id}
            title={`Step ${step.id} · ${step.title}`}
            note={step.dependsOn.length ? `Dopo: step ${step.dependsOn.join(', ')}` : 'Nessun prerequisito'}
          >
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <StatusChip status={step.status} />
              <span className="text-xs">{step.goal}</span>
            </div>
            <ul className="space-y-1 text-xs">
              {step.tasks.map((task) => (
                <li key={task.text} className="flex items-start gap-2">
                  <span style={{ color: STATUS[task.status].color }}>{STATUS[task.status].mark}</span>
                  <span>{task.text}</span>
                </li>
              ))}
            </ul>
            <div className="mt-2 text-[11px]" style={{ color: TEXT_MUTED }}>
              Fatto quando: {step.doneWhen}
            </div>
          </Section>
        ))}

        <Section title="Aggiornamenti">
          <ul className="space-y-1 text-xs">
            {[...ROADMAP_UPDATES].reverse().map((u) => (
              <li key={`${u.date}-${u.text}`}>
                <span className="tabular-nums" style={{ color: TEXT_MUTED }}>
                  {u.date}
                </span>{' '}
                · {u.text}
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </PatternInsightsShell>
  )
}
