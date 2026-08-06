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

export function HomeWinsBalanceSnapshotPanel({ snapshot }: Props) {
  if (!snapshot || snapshot.status === 'unavailable') {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="text-base font-semibold text-slate-900">Equilibrio vs Squilibrio</h3>
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
      <h3 className="text-base font-semibold text-slate-900">Equilibrio vs Squilibrio</h3>
      <p className="mt-1 text-sm text-slate-500">Snapshot persistito balance_v5_monitoring</p>
      <div className="mt-3 grid gap-x-6 sm:grid-cols-2">
        <Row label="F36 index" value={snapshot.f36_index} />
        <Row label="F36 class" value={snapshot.f36_class} />
        {snapshot.f36_base_index != null ? (
          <Row label="F36 base index" value={snapshot.f36_base_index} />
        ) : null}
        {snapshot.f36_base_class != null ? (
          <Row label="F36 base class" value={snapshot.f36_base_class} />
        ) : null}
        {snapshot.quota_x_media != null ? (
          <Row label="Quota Media X" value={snapshot.quota_x_media} />
        ) : null}
        {snapshot.x_mean_adjustment != null ? (
          <Row label="Correzione X" value={snapshot.x_mean_adjustment} />
        ) : null}
        {snapshot.x_mean_source_status != null ? (
          <Row label="X source status" value={snapshot.x_mean_source_status} />
        ) : null}
        <Row label="Dominance index" value={snapshot.dominance_index} />
        <Row label="Dominance class" value={snapshot.dominance_class} />
        <Row
          label="Dominance direction"
          value={snapshot.dominance_selection ?? snapshot.dominance_direction}
        />
        <Row label="Draw credibility" value={snapshot.draw_credibility_index} />
        <Row label="Gap index" value={snapshot.gap_index} />
        <Row label="Prob 1 norm" value={snapshot.prob_1_norm} />
        <Row label="Prob X norm" value={snapshot.prob_x_norm} />
        <Row label="Prob 2 norm" value={snapshot.prob_2_norm} />
        <Row label="Source mode" value={snapshot.source_mode} />
        <Row label="Pre-match verified" value={String(snapshot.pre_match_verified ?? '—')} />
      </div>
    </section>
  )
}
