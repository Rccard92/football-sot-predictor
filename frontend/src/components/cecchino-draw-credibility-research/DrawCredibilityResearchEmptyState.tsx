type Props = {
  onRunAudit: () => void
}

export function DrawCredibilityResearchEmptyState({ onRunAudit }: Props) {
  return (
    <section className="rounded-2xl border border-dashed border-slate-300 bg-white/60 p-8 text-center">
      <p className="text-sm text-slate-600">
        Seleziona un intervallo date e premi &quot;Esegui audit&quot; per analizzare la copertura
        storica Credibilità X.
      </p>
      <button
        type="button"
        onClick={onRunAudit}
        className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
      >
        Esegui audit
      </button>
    </section>
  )
}
