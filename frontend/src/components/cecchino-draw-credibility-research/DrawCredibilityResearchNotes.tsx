export function DrawCredibilityResearchNotes() {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-slate-50/80 p-4 text-xs leading-relaxed text-slate-600">
      <h2 className="text-sm font-semibold text-slate-800">Note operative</h2>
      <ul className="mt-2 list-inside list-disc space-y-1">
        <li>Nessuna API esterna consumata — solo lettura dati già presenti nel database.</li>
        <li>Nessuna formula produttiva modificata (F36, Dominanza, Gap, Credibilità X attuale).</li>
        <li>Nessun segnale Cecchino, KPI o rating modificato.</li>
        <li>L&apos;audit verifica copertura storica per la futura Fase 1B (dataset Credibilità X).</li>
      </ul>
    </section>
  )
}
