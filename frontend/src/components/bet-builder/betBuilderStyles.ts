export const bbCard =
  'rounded-2xl border border-slate-200/90 bg-white shadow-sm shadow-slate-900/5'

export const bbCardPadding = 'p-4 sm:p-5'

export const bbSectionTitle = 'text-sm font-semibold tracking-tight text-slate-800'

export const bbMuted = 'text-sm text-slate-500'

export const bbChipBase =
  'inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2'

export const bbChipIdle = `${bbChipBase} border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50`

export const bbChipActive = `${bbChipBase} border-slate-800 bg-slate-900 text-white`

export const bbBadge =
  'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold tracking-wide'

export const bbInput =
  'min-h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 shadow-sm placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-1'

export const bbSelect = bbInput

export const bbPrimaryBtn =
  'inline-flex min-h-11 items-center justify-center rounded-lg bg-slate-900 px-4 text-sm font-semibold text-white transition hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2'

export const bbSecondaryBtn =
  'inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-800 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2'

export const bbSkeleton = 'animate-pulse rounded-2xl bg-slate-200/80'

/** 1 colonna mobile/tablet; 2 colonne da xl (≥1280) — utile a 1440/1920. */
export const bbGridCards = 'mx-auto grid w-full grid-cols-1 gap-4 xl:grid-cols-2'

export const bbMarketChipScroll =
  '-mx-1 flex gap-2 overflow-x-auto scroll-smooth px-1 pb-1 snap-x snap-mandatory [scrollbar-width:thin] sm:flex-wrap sm:overflow-visible'

/** Scroll orizzontale opportunity: scrollbar nascosta su mobile, wrap da sm. */
export const bbOppTabScroll =
  '-mx-1 flex max-w-full gap-2 overflow-x-auto scroll-smooth px-1 pr-3 pb-1 snap-x snap-mandatory [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:flex-wrap sm:overflow-visible sm:pb-0 sm:pr-1'

export const bbOppTabBase =
  'inline-flex min-h-11 min-w-[4.5rem] shrink-0 snap-start flex-col items-start justify-center gap-0.5 rounded-xl border px-3 py-2 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2'

export const bbOppTabIdle = `${bbOppTabBase} border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50`

/** Secondary selected — slate/navy forte, inequivocabile, senza In evidenza. */
export const bbOppTabSelected = `${bbOppTabBase} border-slate-700 bg-slate-100 text-slate-950 ring-2 ring-slate-600/50 shadow-sm`

/** Primary non-selected — emerald chiaro, non sembra selected. */
export const bbOppTabPrimary = `${bbOppTabBase} border-emerald-300 bg-emerald-50 text-emerald-950 shadow-sm`

/** Primary + selected — emerald pieno elegante. */
export const bbOppTabPrimarySelected = `${bbOppTabBase} border-emerald-600 bg-emerald-600 text-white shadow-md ring-2 ring-emerald-700/40`

export const bbMetricCell =
  'min-w-0 max-w-full overflow-hidden rounded-xl border border-slate-100 bg-slate-50/70 px-3 py-2.5'

export const bbInEvidenzaBadge =
  'inline-flex items-center rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-900'

/** Badge In evidenza su tab primary selected (testo chiaro). */
export const bbInEvidenzaBadgeOnDark =
  'inline-flex items-center rounded bg-white/20 px-1 py-px text-[9px] font-bold uppercase tracking-wider text-white'

/** Badge In evidenza su tab primary non-selected. */
export const bbInEvidenzaBadgeOnLight =
  'inline-flex items-center rounded border border-emerald-200/80 bg-white/80 px-1 py-px text-[9px] font-bold uppercase tracking-wider text-emerald-800'
