type Props = {
  snapshot?: Record<string, unknown> | null
}

function Row({ label, value }: { label: string; value: unknown }) {
  const text =
    value == null || value === ''
      ? '—'
      : typeof value === 'number'
        ? Number.isInteger(value)
          ? String(value)
          : value.toFixed(3)
        : String(value)
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-slate-100 py-1.5 text-sm">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium tabular-nums text-slate-900">{text}</span>
    </div>
  )
}

export function HomeWinsGoalIntensitySnapshotPanel({ snapshot }: Props) {
  if (!snapshot || snapshot.status === 'unavailable') {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="text-base font-semibold text-slate-900">Intensità Goal Avanzata v5</h3>
        <p className="mt-2 text-sm text-slate-600">
          Dato non disponibile nello snapshot storico
        </p>
        {snapshot?.reason ? (
          <p className="mt-1 text-xs text-slate-400">{String(snapshot.reason)}</p>
        ) : null}
      </section>
    )
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="text-base font-semibold text-slate-900">Intensità Goal Avanzata v5</h3>
      <p className="mt-1 text-sm text-slate-500">Snapshot persistito — nessun ricalcolo</p>
      <div className="mt-3 grid gap-x-6 sm:grid-cols-2">
        <Row label="Primary score" value={snapshot.primary_candidate_score} />
        <Row label="Challenger score" value={snapshot.challenger_candidate_score} />
        <Row label="Benchmark score" value={snapshot.benchmark_score} />
        <Row label="Diagnostic score" value={snapshot.diagnostic_score} />
        <Row label="Expected total goals" value={snapshot.expected_total_goals} />
        <Row label="P(goals ≥ 2)" value={snapshot.probability_goals_ge_2} />
        <Row label="P(goals ≥ 3)" value={snapshot.probability_goals_ge_3} />
        <Row label="P(BTTS)" value={snapshot.probability_btts} />
        <Row label="History sample" value={snapshot.history_sample_size} />
        <Row label="xG status" value={snapshot.xg_status} />
        <Row label="Preview status" value={snapshot.preview_status} />
        <Row label="Snapshot before KO" value={String(snapshot.source_snapshot_before_kickoff ?? '—')} />
        <Row label="No target in score" value={String(snapshot.no_target_used_in_score ?? '—')} />
      </div>
    </section>
  )
}
