/**
 * Costanti V4 lato interfaccia. Specchiano backend/app/services/cecchino_v4/constants.py:
 * chi cambia una voce la cambia in entrambi i file.
 */

import type {
  V4ChallengerStatus,
  V4ExamOutcome,
  V4LineupsStatus,
  V4PlayResult,
  V4ShortlistItemStatus,
  V4UncertaintyLevel,
  V4Verdict,
} from '../../lib/cecchinoV4Api'

export type V4League = {
  code: string
  competition: string
  country: string
  tier: number
}

export const V4_LEAGUES: readonly V4League[] = [
  { code: 'E0', competition: 'Premier League', country: 'Inghilterra', tier: 1 },
  { code: 'E1', competition: 'Championship', country: 'Inghilterra', tier: 2 },
  { code: 'E2', competition: 'League One', country: 'Inghilterra', tier: 3 },
  { code: 'E3', competition: 'League Two', country: 'Inghilterra', tier: 4 },
  { code: 'I1', competition: 'Serie A', country: 'Italia', tier: 1 },
  { code: 'I2', competition: 'Serie B', country: 'Italia', tier: 2 },
  { code: 'SP1', competition: 'La Liga', country: 'Spagna', tier: 1 },
  { code: 'SP2', competition: 'La Liga 2', country: 'Spagna', tier: 2 },
  { code: 'D1', competition: 'Bundesliga', country: 'Germania', tier: 1 },
  { code: 'D2', competition: 'Bundesliga 2', country: 'Germania', tier: 2 },
  { code: 'F1', competition: 'Ligue 1', country: 'Francia', tier: 1 },
  { code: 'F2', competition: 'Ligue 2', country: 'Francia', tier: 2 },
  { code: 'N1', competition: 'Eredivisie', country: 'Paesi Bassi', tier: 1 },
  { code: 'B1', competition: 'Jupiler Pro League', country: 'Belgio', tier: 1 },
  { code: 'P1', competition: 'Primeira Liga', country: 'Portogallo', tier: 1 },
  { code: 'T1', competition: 'Süper Lig', country: 'Turchia', tier: 1 },
]

export const V4_LEAGUE_BY_CODE: Readonly<Record<string, V4League>> = Object.fromEntries(
  V4_LEAGUES.map((l) => [l.code, l]),
)

export function leagueName(code: string): string {
  return V4_LEAGUE_BY_CODE[code]?.competition ?? code
}

// --- Selezione -------------------------------------------------------------------

export const V4_PROFIT_MARGIN = 0.03
export const V4_MAX_PLAYS_PER_DAY = 50
export const V4_TOP_PLAYS = 15
export const V4_MIN_QUOTA = 1.2
export const V4_API_DAILY_STOP = 7000

// --- Verdetti (colori fissi) --------------------------------------------------------

export const V4_VERDICT_LABELS: Record<V4Verdict, string> = {
  giocabile: 'Giocabile',
  prezzo_giusto: 'Prezzo giusto',
  incertezza_alta: 'Incertezza alta',
  non_quotato: 'Non quotato',
  solo_descrittivo: 'Solo descrittivo',
  formazioni_non_note: 'Formazioni non note',
}

export const V4_VERDICT_CHIP: Record<V4Verdict, string> = {
  giocabile: 'bg-emerald-100 text-emerald-800 ring-emerald-200',
  prezzo_giusto: 'bg-slate-100 text-slate-700 ring-slate-200',
  incertezza_alta: 'bg-amber-100 text-amber-800 ring-amber-200',
  non_quotato: 'bg-slate-200 text-slate-600 ring-slate-300',
  solo_descrittivo: 'bg-sky-100 text-sky-800 ring-sky-200',
  formazioni_non_note: 'bg-amber-100 text-amber-800 ring-amber-200',
}

/** Motivo dell'astensione in parole minuscole, da leggere dopo "Nessuna giocata:". */
export const V4_NO_PLAY_REASON_LABELS: Record<string, string> = {
  prezzo_giusto: 'prezzo giusto',
  incertezza_alta: 'incertezza alta',
  formazioni_non_note: 'formazioni non note',
  non_quotato: 'mercato non quotato',
  solo_descrittivo: 'statistica solo descrittiva',
}

export function noPlayReasonLabel(reason: string | null | undefined): string {
  if (!reason) return 'nessun margine'
  return V4_NO_PLAY_REASON_LABELS[reason] ?? reason.replaceAll('_', ' ')
}

// --- Statistiche e famiglie ------------------------------------------------------------

export const V4_STAT_LABELS: Record<string, string> = {
  shots: 'tiri',
  sot: 'tiri in porta',
  corners: 'corner',
  cards: 'cartellini',
  fouls: 'falli',
}

export function statLabel(stat: string): string {
  return V4_STAT_LABELS[stat] ?? stat
}

export const V4_FAMILY_LABELS: Record<string, string> = {
  FT_1X2: 'Esito finale',
  DOUBLE_CHANCE: 'Doppia chance',
  FT_OVER_UNDER: 'Over/Under gol',
  HT_1X2: 'Primo tempo',
  AH: 'Handicap asiatico',
  STAT_shots: 'Tiri',
  STAT_sot: 'Tiri in porta',
  STAT_corners: 'Corner',
  STAT_cards: 'Cartellini',
  STAT_fouls: 'Falli',
  'STAT:shots': 'Tiri',
  'STAT:sot': 'Tiri in porta',
  'STAT:corners': 'Corner',
  'STAT:cards': 'Cartellini',
  'STAT:fouls': 'Falli',
}

export function familyLabel(family: string): string {
  return V4_FAMILY_LABELS[family] ?? family.replaceAll('_', ' ')
}

// --- Formazioni, incertezza ---------------------------------------------------------------

export const V4_LINEUPS_LABELS: Record<V4LineupsStatus, string> = {
  non_note: 'Formazioni non note',
  probabili: 'Formazioni probabili',
  ufficiali: 'Formazioni ufficiali',
}

export const V4_LINEUPS_DOT: Record<V4LineupsStatus, string> = {
  non_note: 'bg-slate-300',
  probabili: 'bg-amber-400',
  ufficiali: 'bg-emerald-500',
}

export const V4_UNCERTAINTY_LABELS: Record<V4UncertaintyLevel, string> = {
  bassa: 'Incertezza bassa',
  media: 'Incertezza media',
  alta: 'Incertezza alta',
}

export const V4_UNCERTAINTY_BAR: Record<V4UncertaintyLevel, string> = {
  bassa: 'bg-emerald-500',
  media: 'bg-amber-400',
  alta: 'bg-red-500',
}

// --- Shortlist -----------------------------------------------------------------------------------

export const V4_SHORTLIST_STATUS_LABELS: Record<V4ShortlistItemStatus, string> = {
  provvisoria: 'Provvisoria',
  confermata: 'Confermata',
  ritirata: 'Ritirata',
  regolata: 'Regolata',
}

export const V4_SHORTLIST_STATUS_CHIP: Record<V4ShortlistItemStatus, string> = {
  provvisoria: 'bg-amber-100 text-amber-800 ring-amber-200',
  confermata: 'bg-emerald-100 text-emerald-800 ring-emerald-200',
  ritirata: 'bg-red-100 text-red-800 ring-red-200',
  regolata: 'bg-slate-100 text-slate-700 ring-slate-200',
}

export const V4_PLAY_RESULT_LABELS: Record<V4PlayResult, string> = {
  vinta: 'Vinta',
  persa: 'Persa',
  void: 'Void',
  mezza_vinta: 'Mezza vinta',
  mezza_persa: 'Mezza persa',
}

export const V4_PLAY_RESULT_CHIP: Record<V4PlayResult, string> = {
  vinta: 'bg-emerald-100 text-emerald-800 ring-emerald-200',
  persa: 'bg-red-100 text-red-800 ring-red-200',
  void: 'bg-slate-100 text-slate-600 ring-slate-200',
  mezza_vinta: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  mezza_persa: 'bg-red-50 text-red-700 ring-red-200',
}

export const V4_TREND_ARROW: Record<string, string> = {
  'in crescita': '↑',
  'in calo': '↓',
  stabile: '→',
}

// --- Motore ----------------------------------------------------------------------------------------

export const V4_EXAM_OUTCOME_LABELS: Record<V4ExamOutcome, string> = {
  superato: 'Superato',
  non_superato: 'Non superato',
  in_attesa: 'In attesa',
}

export const V4_EXAM_OUTCOME_CHIP: Record<V4ExamOutcome, string> = {
  superato: 'bg-emerald-100 text-emerald-800 ring-emerald-200',
  non_superato: 'bg-red-100 text-red-800 ring-red-200',
  in_attesa: 'bg-amber-100 text-amber-800 ring-amber-200',
}

export function examOutcomeFromPassed(passed: boolean | null): V4ExamOutcome {
  if (passed === true) return 'superato'
  if (passed === false) return 'non_superato'
  return 'in_attesa'
}

export const V4_CHALLENGER_STATUS_LABELS: Record<V4ChallengerStatus, string> = {
  candidato: 'Candidato',
  superato: 'Superato',
  non_superato: 'Non superato',
}

export const V4_CHALLENGER_STATUS_CHIP: Record<V4ChallengerStatus, string> = {
  candidato: 'bg-slate-100 text-slate-700 ring-slate-200',
  superato: 'bg-emerald-100 text-emerald-800 ring-emerald-200',
  non_superato: 'bg-red-100 text-red-800 ring-red-200',
}

// --- Viste ---------------------------------------------------------------------------------------------

export const V4_VIEWS = ['partite', 'shortlist', 'misura', 'motore'] as const
export type V4View = (typeof V4_VIEWS)[number]

export const V4_VIEW_LABELS: Record<V4View, string> = {
  partite: 'Partite',
  shortlist: 'Shortlist',
  misura: 'Misura',
  motore: 'Motore',
}

export function parseV4View(raw: string | null | undefined): V4View {
  return (V4_VIEWS as readonly string[]).includes(raw ?? '') ? (raw as V4View) : 'partite'
}

/** I sei blocchi del Ragionamento, nell'ordine di lettura. */
export const V4_BLOCK_TITLES = [
  'Chi sono',
  'Come giocano',
  'Contesto',
  'Cosa prevede',
  'Perché sì, perché no',
  'Come è andata',
] as const

/** Classi comuni: etichetta 16 px in maiuscoletto pesante, mai testo piccolo. */
export const v4Label = 'text-base font-semibold uppercase tracking-wide text-slate-500'
export const v4Chip =
  'inline-flex items-center whitespace-nowrap rounded-full px-3 py-0.5 text-base font-semibold ring-1'
export const v4Title = 'text-2xl font-bold text-slate-900'
export const v4SectionTitle = 'text-xl font-semibold text-slate-900'
