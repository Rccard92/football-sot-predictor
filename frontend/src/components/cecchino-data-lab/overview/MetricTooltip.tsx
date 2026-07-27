import { useState, type ReactNode } from 'react'

const DEFINITIONS: Record<string, string> = {
  roi_flat:
    'Risultato storico ottenuto simulando una puntata di 1 unità su ogni evento eleggibile. Non rappresenta una strategia futura.',
  favorite:
    'Selezione con quota Bet365 pre-closing più bassa tra 1, X e 2. In caso di parità la partita è esclusa.',
  implied:
    'Probabilità implicita normalizzata: 1/quota diviso la somma di 1/H + 1/D + 1/A, per rimuovere il margine bookmaker.',
  margin:
    'Somma delle probabilità implicite 1/X/2 meno il 100%. Non implica profitto garantito.',
  pre_closing:
    'Quota Bet365 pre-closing (colonne B365H/D/A), tipicamente catturata prima della chiusura del mercato.',
  closing:
    'Quota Bet365 di chiusura (B365CH/D/A), rilevata a mercato chiuso.',
  calibration_gap:
    'Differenza in punti percentuali tra win rate reale della favorita e probabilità implicita normalizzata media nel bucket.',
  coverage:
    'Percentuale di partite con quote 1X2 Bet365 pre-closing complete nel campione filtrato.',
}

type Props = {
  metric: keyof typeof DEFINITIONS | string
  children: ReactNode
  className?: string
}

export function MetricTooltip({ metric, children, className }: Props) {
  const [open, setOpen] = useState(false)
  const text = DEFINITIONS[metric] || metric

  return (
    <span
      className={`relative inline-flex items-center gap-1 ${className || ''}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      <button
        type="button"
        aria-label="Definizione"
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-semibold"
        style={{
          background: 'var(--lab-cyan-dim)',
          color: 'var(--lab-cyan)',
          border: '1px solid var(--lab-border)',
        }}
      >
        ?
      </button>
      {open ? (
        <span
          role="tooltip"
          className="absolute left-0 top-full z-40 mt-2 w-64 rounded-lg px-3 py-2 text-xs leading-relaxed shadow-lg"
          style={{
            background: '#0f1c2c',
            border: '1px solid var(--lab-border)',
            color: 'var(--lab-text)',
          }}
        >
          {text}
        </span>
      ) : null}
    </span>
  )
}
