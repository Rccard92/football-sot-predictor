type Props = {
  cecchinoVersion?: string | null
}

export function CecchinoPageHeader({ cecchinoVersion }: Props) {
  const version = cecchinoVersion ?? 'cecchino_v0_3_signals_matrix'

  return (
    <header className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-slate-900">Cecchino</h1>
        <span className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-0.5 text-xs font-medium text-indigo-800">
          {version}
        </span>
      </div>
    </header>
  )
}
