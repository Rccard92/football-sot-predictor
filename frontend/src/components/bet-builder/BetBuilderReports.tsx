import { useState } from 'react'
import { bbCard, bbCardPadding, bbChipActive, bbChipIdle } from './betBuilderStyles'
import { QUOTA_BANDS, type BetBuilderReport, type RoiStat } from './betBuilderReportUtils'

/** Rapporti della pagina Risultati (richiesta di Giovanni, 13/10/2026): si aggiornano con i filtri. */

type Tab = 'bands' | 'value' | 'index' | 'calibration' | 'monthly'

function pct(v: number | null | undefined, signed = false): string {
  if (v == null) return '—'
  const s = v.toLocaleString('it-IT', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
  return `${signed && v > 0 ? '+' : ''}${s}%`
}

function num(v: number | null | undefined): string {
  return v == null ? '—' : v.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function range(s: RoiStat): string {
  if (s.roi_low_pct == null || s.roi_high_pct == null) return '—'
  return `${pct(s.roi_low_pct, true)} / ${pct(s.roi_high_pct, true)}`
}

function roiClass(s: RoiStat): string {
  if (s.roi_pct == null) return 'text-slate-400'
  if ((s.roi_low_pct ?? -1) > 0) return 'font-semibold text-emerald-700'
  if ((s.roi_high_pct ?? 1) < 0) return 'font-semibold text-rose-700'
  return 'text-slate-800'
}

const th = 'px-2 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500'
const td = 'px-2 py-1.5 tabular-nums text-slate-800'

function StatsTable({ rows, first }: { rows: (RoiStat & { label: string; extra?: string })[]; first: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <thead className="border-b border-slate-200">
          <tr>
            <th className={th}>{first}</th>
            <th className={th}>Giocate</th>
            <th className={th}>Vinte</th>
            <th className={th}>Serve per pari</th>
            <th className={th}>Quota media</th>
            <th className={th}>Profitto</th>
            <th className={th}>ROI</th>
            <th className={th}>Forbice 90%</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={r.label} className={r.plays === 0 ? 'text-slate-400' : ''}>
              <td className={`${td} font-medium`}>
                {r.label}
                {r.extra ? <span className="ml-1 text-xs font-normal text-slate-500">{r.extra}</span> : null}
              </td>
              <td className={td}>{r.plays}</td>
              <td className={td}>{pct(r.win_pct)}</td>
              <td className={td}>{pct(r.break_even_pct)}</td>
              <td className={td}>{num(r.avg_quota)}</td>
              <td className={td}>{r.plays ? r.profit.toLocaleString('it-IT', { signDisplay: 'always', maximumFractionDigits: 2 }) : '—'}</td>
              <td className={`${td} ${roiClass(r)}`}>{pct(r.roi_pct, true)}</td>
              <td className={`${td} text-xs text-slate-500`}>{range(r)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ValueMap({ report }: { report: BetBuilderReport }) {
  const markets = [...new Map(report.market_bands.map((c) => [c.market_key, c.market_label])).entries()]
  const cell = (mk: string, band: string) => report.market_bands.find((c) => c.market_key === mk && c.band === band)
  if (!markets.length) return <p className="text-sm text-slate-500">Nessuna giocata conclusa con questi filtri.</p>
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="border-b border-slate-200">
            <tr>
              <th className={th}>Mercato</th>
              {QUOTA_BANDS.map((b) => (
                <th key={b.band} className={th}>
                  {b.band}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {markets.map(([mk, label]) => (
              <tr key={mk}>
                <td className={`${td} font-medium`}>{label}</td>
                {QUOTA_BANDS.map((b) => {
                  const c = cell(mk, b.band)
                  if (!c || c.plays === 0) return <td key={b.band} className={`${td} text-slate-300`}>—</td>
                  return (
                    <td
                      key={b.band}
                      className={`${td} ${c.value ? 'bg-emerald-50' : ''}`}
                      title={`Forbice 90%: ${range(c)}`}
                      data-value={c.value ? 'si' : 'no'}
                    >
                      <span className={c.plays < 10 ? 'text-slate-400' : roiClass(c)}>{pct(c.roi_pct, true)}</span>
                      <span className="ml-1 text-[11px] text-slate-400">({c.plays})</span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">
        ROI per mercato e fascia di quota, tra parentesi le giocate. Verde: {report.value_rule}. In grigio le caselle con meno di 10
        giocate. I mercati non li sceglie nessuno a mano: emergono dai numeri man mano che crescono.
      </p>
    </div>
  )
}

export function BetBuilderReports({ report, title = 'Rapporti' }: { report: BetBuilderReport; title?: string }) {
  const [tab, setTab] = useState<Tab>('bands')
  const s = report.summary
  const tabs: { key: Tab; label: string; show: boolean }[] = [
    { key: 'bands', label: 'Fasce di quota', show: true },
    { key: 'value', label: "Dove c'è valore", show: true },
    { key: 'index', label: report.index_steps ? 'Contributo indice' : 'Punteggio', show: Boolean(report.index_steps || report.score_bands) },
    { key: 'calibration', label: 'Probabilità realistica?', show: Boolean(report.calibration?.length) },
    { key: 'monthly', label: 'Mese per mese', show: true },
  ]
  return (
    <details className={`${bbCard} ${bbCardPadding}`} data-testid="bet-builder-reports">
      <summary className="cursor-pointer list-none">
        <span className="text-sm font-semibold text-slate-900">{title}</span>
        <span className="ml-2 text-xs text-slate-600">
          {s.plays} giocate concluse · quota media {num(s.avg_quota)} · per andare in pari serve vincere il {pct(s.break_even_pct)} · vinte{' '}
          {pct(s.win_pct)} · ROI <span className={roiClass(s)}>{pct(s.roi_pct, true)}</span> (forbice {range(s)})
        </span>
      </summary>
      <div className="mt-3 space-y-3">
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Rapporti">
          {tabs
            .filter((t) => t.show)
            .map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                className={`${tab === t.key ? bbChipActive : bbChipIdle} min-h-9 py-1.5`}
                onClick={() => setTab(t.key)}
              >
                {t.label}
              </button>
            ))}
        </div>

        {tab === 'bands' ? (
          <>
            <StatsTable first="Fascia di quota" rows={report.quota_bands.map((b) => ({ ...b, label: b.band }))} />
            <p className="text-xs text-slate-500">
              Sotto 1,41 le giocate non sono più giocabili né in evidenza (decisione del 13/10/2026): la riga resta per controllo.
            </p>
          </>
        ) : null}

        {tab === 'value' ? <ValueMap report={report} /> : null}

        {tab === 'index' && report.index_steps ? (
          <>
            <StatsTable
              first="Selezione"
              rows={report.index_steps.map((r) => ({
                ...r,
                label: r.step,
                extra: r.roi_vs_baseline_pct != null && r.step !== 'senza indice' ? `${pct(r.roi_vs_baseline_pct, true)} rispetto a senza indice` : undefined,
              }))}
            />
            <p className="text-xs text-slate-500">
              Stessa selezione, prima senza filtro e poi con Acquistabilità V3.6 da 50, 60 e 70: la differenza di ROI è il contributo dell&apos;indice.
              Conta solo se supera la forbice.
            </p>
          </>
        ) : null}

        {tab === 'index' && !report.index_steps && report.score_bands ? (
          <>
            <StatsTable
              first="Punteggio"
              rows={report.score_bands.map((r) => ({ ...r, label: r.band, extra: r.avg_prob_pct != null ? `stima media ${pct(r.avg_prob_pct)}` : undefined }))}
            />
            <p className="text-xs text-slate-500">Le predizioni a 100/100 confrontate con quelle tra 70 e 99.</p>
          </>
        ) : null}

        {tab === 'calibration' && report.calibration ? (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[420px] text-sm">
                <thead className="border-b border-slate-200">
                  <tr>
                    <th className={th}>Probabilità stimata</th>
                    <th className={th}>Giocate</th>
                    <th className={th}>Stima media</th>
                    <th className={th}>Vinte davvero</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {report.calibration.map((c) => (
                    <tr key={c.bin}>
                      <td className={`${td} font-medium`}>{c.bin}</td>
                      <td className={td}>{c.plays}</td>
                      <td className={td}>{pct(c.predicted_pct)}</td>
                      <td className={td}>{pct(c.actual_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-slate-500">
              Se la probabilità è realistica, &quot;stima media&quot; e &quot;vinte davvero&quot; sono vicine in ogni riga. Con poche giocate la
              differenza può essere solo caso.
            </p>
          </>
        ) : null}

        {tab === 'monthly' ? <StatsTable first="Mese" rows={report.monthly.map((m) => ({ ...m, label: m.month }))} /> : null}
      </div>
    </details>
  )
}
