import { useState } from 'react'
import {
  legacyChangelogEntries,
  type ChangelogType,
  visibleChangelogEntries,
} from '../data/modelChangelog'

function typeBadgeClass(t: ChangelogType): string {
  switch (t) {
    case 'major':
      return 'bg-indigo-100 text-indigo-900 ring-indigo-200'
    case 'minor':
      return 'bg-sky-100 text-sky-900 ring-sky-200'
    default:
      return 'bg-slate-100 text-slate-800 ring-slate-200'
  }
}

function typeLabel(t: ChangelogType): string {
  switch (t) {
    case 'major':
      return 'Major'
    case 'minor':
      return 'Minor'
    default:
      return 'Patch'
  }
}

export function Changelog() {
  const [showLegacy, setShowLegacy] = useState(false)
  const entries = visibleChangelogEntries()
  const legacy = legacyChangelogEntries()

  return (
    <div className="space-y-8 pb-8">
        <header className="max-w-3xl">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Changelog modello</h1>
          <p className="mt-2 text-sm text-slate-600">
            Storico delle versioni del predittore SOT visibili in produzione.
          </p>
        </header>

        <ul className="space-y-6">
          {entries.map((e) => (
            <li
              key={e.version}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ${typeBadgeClass(e.type)}`}
                >
                  {typeLabel(e.type)}
                </span>
                <span className="font-mono text-sm font-semibold text-slate-900">v{e.version}</span>
                <span className="text-xs text-slate-500">{e.date}</span>
              </div>
              <h2 className="mt-2 text-lg font-semibold text-slate-900">{e.title}</h2>
              <p className="mt-2 text-sm text-slate-700">{e.summary}</p>
              {e.highlights.length > 0 ? (
                <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
                  {e.highlights.map((h) => (
                    <li key={h}>{h}</li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>

        <details
          className="rounded-2xl border border-slate-200 bg-white shadow-sm"
          open={showLegacy}
          onToggle={(ev) => setShowLegacy((ev.target as HTMLDetailsElement).open)}
        >
          <summary className="cursor-pointer px-5 py-4 text-sm font-semibold text-slate-800">
            Versioni precedenti (legacy)
          </summary>
          <ul className="space-y-4 border-t border-slate-100 px-5 py-4">
            {legacy.map((e) => (
              <li key={e.version} className="text-sm text-slate-600">
                <span className="font-medium text-slate-800">{e.title}</span> — {e.summary}
              </li>
            ))}
          </ul>
        </details>
    </div>
  )
}
