/** Helper display per consiglio giocata SOT in UI. */

export function pickShortLabel(pick: string | null | undefined): string {
  if (!pick) return '—'
  const m = pick.match(/Over\s+([\d.]+)/i)
  if (m) return `Over ${m[1]}`
  return pick.replace(/\s+SOT$/i, '').trim()
}

export function confidenceBadgeClass(label: string | null | undefined): string {
  const l = (label || '').toLowerCase()
  if (l === 'alta') return 'border-emerald-200 bg-emerald-50 text-emerald-900'
  if (l === 'media') return 'border-amber-200 bg-amber-50 text-amber-950'
  if (l === 'bassa') return 'border-orange-200 bg-orange-50 text-orange-950'
  return 'border-slate-200 bg-slate-50 text-slate-700'
}

export function riskBadgeClass(risk: string | null | undefined): string {
  const r = risk || ''
  if (r === 'Molto tirata' || r === 'Aggressiva') return 'border-rose-200 bg-rose-50 text-rose-900'
  if (r === 'Moderata') return 'border-amber-200 bg-amber-50 text-amber-950'
  if (r === 'Buon margine' || r === 'Forte margine') return 'border-emerald-200 bg-emerald-50 text-emerald-900'
  return 'border-slate-200 bg-slate-100 text-slate-700'
}

export function formationBadgeClass(label: string | null | undefined): string {
  const l = label || ''
  if (l === 'Ufficiale') return 'border-emerald-200 bg-emerald-50 text-emerald-900'
  if (l === 'Aggiornata') return 'border-sky-200 bg-sky-50 text-sky-900'
  if (l === 'Da aggiornare') return 'border-amber-200 bg-amber-50 text-amber-950'
  if (l === 'Mancante') return 'border-rose-200 bg-rose-50 text-rose-900'
  return 'border-slate-200 bg-slate-100 text-slate-700'
}

export function formationStatusTooltip(label: string | null | undefined): string {
  const l = label || ''
  if (l === 'Ufficiale') return 'Formazione ufficiale SportAPI.'
  if (l === 'Aggiornata') {
    return 'Probabile formazione SportAPI aggiornata nelle ultime 6 ore.'
  }
  if (l === 'Da aggiornare') {
    return 'Probabile formazione più vecchia di 6 ore. Aggiorna prima di valutare la giocata.'
  }
  if (l === 'Mancante') return 'Nessuna formazione SportAPI importata per questa partita.'
  return ''
}

export const AFFIDABILITA_HELP =
  'Misura la qualità dei dati usati: freschezza formazione, mapping giocatori, rosa aggiornata, margine sulla linea e completezza dei profili. Non è probabilità di vincita.'
