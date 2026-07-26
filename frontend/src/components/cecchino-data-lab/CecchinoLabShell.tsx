import type { CSSProperties, ReactNode } from 'react'
import { labCssVars } from './labTheme'

type Props = {
  children: ReactNode
  className?: string
}

export function CecchinoLabShell({ children, className = '' }: Props) {
  return (
    <div
      className={`lab-shell relative min-h-[calc(100vh-2rem)] overflow-hidden rounded-2xl ${className}`}
      style={
        {
          ...labCssVars,
          background:
            'radial-gradient(1200px 600px at 10% -10%, rgba(46,230,255,0.12), transparent 55%), radial-gradient(900px 500px at 90% 0%, rgba(61,214,140,0.08), transparent 50%), var(--lab-bg)',
          color: 'var(--lab-text)',
          fontFamily: '"IBM Plex Sans", "Segoe UI", system-ui, sans-serif',
        } as CSSProperties
      }
    >
      <style>{`
        .lab-shell {
          border: 1px solid var(--lab-border);
          box-shadow: 0 20px 60px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04);
        }
        .lab-card {
          background: linear-gradient(160deg, var(--lab-surface) 0%, var(--lab-bg-elevated) 100%);
          border: 1px solid var(--lab-border);
          border-radius: 14px;
          box-shadow: 0 8px 24px rgba(0,0,0,0.22);
        }
        .lab-tab {
          color: var(--lab-muted);
          border-bottom: 2px solid transparent;
          transition: color .15s ease, border-color .15s ease, background .15s ease;
        }
        .lab-tab:hover { color: var(--lab-text); background: rgba(46,230,255,0.05); }
        .lab-tab-active {
          color: var(--lab-cyan);
          border-bottom-color: var(--lab-cyan);
          background: rgba(46,230,255,0.08);
        }
        .lab-badge-ok { background: rgba(61,214,140,.15); color: var(--lab-ok); border: 1px solid rgba(61,214,140,.35); }
        .lab-badge-warn { background: rgba(240,180,41,.14); color: var(--lab-warn); border: 1px solid rgba(240,180,41,.35); }
        .lab-badge-err { background: rgba(240,113,120,.14); color: var(--lab-err); border: 1px solid rgba(240,113,120,.35); }
        .lab-badge-muted { background: rgba(138,160,181,.12); color: var(--lab-muted); border: 1px solid rgba(138,160,181,.25); }
        .lab-input {
          background: var(--lab-bg-elevated);
          border: 1px solid var(--lab-border);
          color: var(--lab-text);
          border-radius: 10px;
          padding: 0.55rem 0.75rem;
          width: 100%;
        }
        .lab-input:focus { outline: none; border-color: var(--lab-cyan); box-shadow: 0 0 0 2px var(--lab-cyan-dim); }
        .lab-btn {
          background: linear-gradient(135deg, #1ec8e0, #2ee6ff);
          color: #041018;
          font-weight: 650;
          border-radius: 10px;
          padding: 0.6rem 1.1rem;
          border: none;
          cursor: pointer;
        }
        .lab-btn:disabled { opacity: .45; cursor: not-allowed; }
        .lab-btn-ghost {
          background: transparent;
          color: var(--lab-cyan);
          border: 1px solid var(--lab-border);
          border-radius: 10px;
          padding: 0.55rem 1rem;
          cursor: pointer;
        }
        .lab-table-wrap { overflow: auto; max-height: min(70vh, 820px); border-radius: 12px; border: 1px solid var(--lab-border); }
        .lab-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 0.875rem; }
        .lab-table th {
          position: sticky; top: 0; z-index: 2;
          background: #0f1c2c; color: var(--lab-muted); text-align: left;
          padding: 0.65rem 0.75rem; border-bottom: 1px solid var(--lab-border);
          white-space: nowrap; font-weight: 600; letter-spacing: .02em;
        }
        .lab-table td {
          padding: 0.6rem 0.75rem; border-bottom: 1px solid rgba(120,190,220,0.07);
          white-space: nowrap;
        }
        .lab-table tr:hover td { background: rgba(46,230,255,0.04); }
        .lab-drop {
          border: 1.5px dashed rgba(46,230,255,0.35);
          background: rgba(46,230,255,0.04);
          border-radius: 16px;
          transition: border-color .15s, background .15s;
        }
        .lab-drop-active { border-color: var(--lab-cyan); background: rgba(46,230,255,0.1); }
      `}</style>
      {children}
    </div>
  )
}
