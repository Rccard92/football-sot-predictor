export function DrawCredibilityCandidateFormulasLegend() {
  return (
    <details className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <summary className="cursor-pointer text-sm font-semibold text-slate-800">
        Formule candidate (solo research)
      </summary>
      <div className="mt-3 space-y-3 text-xs text-slate-600">
        <p>
          Le formule candidate sono calcolate nel service dataset e <strong>non</strong> modificano il motore
          produttivo Cecchino.
        </p>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <strong>Conviction index</strong>: clamp(100 × (Pmax − Psecond) / Pmax, 0, 100) con bande 0–20 /
            20–40 / 40–60 / 60–80 / 80–100.
          </li>
          <li>
            <strong>Probability gap 1-2</strong>: |prob_1_norm − prob_2_norm| in punti percentuali.
          </li>
          <li>
            <strong>Probability balance index</strong>: clamp(100 × (1 − gap / (p1+p2)), 0, 100).
          </li>
          <li>
            <strong>Gap coherence index</strong>: clamp(100 − |f36_score − prob_balance_index|, 0, 100) con
            classi research dedicate.
          </li>
          <li>
            <strong>x_rank</strong>: posizione di X nell&apos;ordinamento decrescente delle probabilità
            normalizzate 1/X/2; <code>x_tied_for_top</code> se X è in parità col massimo.
          </li>
        </ul>
      </div>
    </details>
  )
}
