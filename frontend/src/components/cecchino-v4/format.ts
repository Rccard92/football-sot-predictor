/** Formattazione italiana per Cecchino V4: virgola decimale, percentuali intere, orari su Europe/Rome. */

const ROME = 'Europe/Rome'
const MINUS = '−'
const EN_DASH = '–'

export const V4_EMPTY = '–'

function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

/** "1,2" (una cifra) o "1,85" (due cifre). */
export function fmtDecimal(v: number | null | undefined, digits = 1): string {
  if (!isNum(v)) return V4_EMPTY
  return v.toFixed(digits).replace('.', ',')
}

/** Quota con la virgola, due decimali: 1.85 → "1,85". */
export function fmtQuota(q: number | null | undefined): string {
  return fmtDecimal(q, 2)
}

/** Linea con mezzo: 6.5 → "6,5". */
export function fmtLine(line: number | string): string {
  const n = typeof line === 'string' ? Number(line) : line
  return fmtDecimal(n, 1)
}

/** Percentuale intera: 0.61 → "61%". */
export function fmtPct(p: number | null | undefined): string {
  if (!isNum(p)) return V4_EMPTY
  return `${Math.round(p * 100)}%`
}

/** Probabilita' con intervallo: "61% (55–66)". */
export function fmtInterval(
  p: number | null | undefined,
  lo: number | null | undefined,
  hi: number | null | undefined,
): string {
  if (!isNum(p)) return V4_EMPTY
  if (!isNum(lo) || !isNum(hi)) return fmtPct(p)
  return `${fmtPct(p)} (${Math.round(lo * 100)}${EN_DASH}${Math.round(hi * 100)})`
}

/** Percentuale con segno: 0.13 → "+13%", -0.012 con 1 cifra → "−1,2%". */
export function fmtSignedPct(v: number | null | undefined, digits = 0): string {
  if (!isNum(v)) return V4_EMPTY
  const factor = 10 ** digits
  const rounded = Math.round(v * 100 * factor) / factor
  const abs = Math.abs(rounded).toFixed(digits).replace('.', ',')
  if (rounded > 0) return `+${abs}%`
  if (rounded < 0) return `${MINUS}${abs}%`
  return `${abs}%`
}

/** Numero con segno senza percento: 0.18 → "+0,18". */
export function fmtSigned(v: number | null | undefined, digits = 2): string {
  if (!isNum(v)) return V4_EMPTY
  const abs = Math.abs(v).toFixed(digits).replace('.', ',')
  if (v > 0) return `+${abs}`
  if (v < 0) return `${MINUS}${abs}`
  return abs
}

/** Profitto atteso intero con segno: "+13%". */
export function fmtProfit(v: number | null | undefined): string {
  return fmtSignedPct(v, 0)
}

/** ROI con una cifra: "−1,2%". */
export function fmtRoi(v: number | null | undefined): string {
  return fmtSignedPct(v, 1)
}

/** ROI con intervallo: "−1,2% (−4,0 · +1,8)". */
export function fmtRoiWithCi(
  roi: number | null | undefined,
  lo: number | null | undefined,
  hi: number | null | undefined,
): string {
  if (!isNum(roi)) return V4_EMPTY
  if (!isNum(lo) || !isNum(hi)) return fmtRoi(roi)
  const bound = (v: number) => fmtSignedPct(v, 1).replace('%', '')
  return `${fmtRoi(roi)} (${bound(lo)} · ${bound(hi)})`
}

/** Conteggio con il punto delle migliaia: 7000 → "7.000". */
export function fmtCount(n: number | null | undefined): string {
  if (!isNum(n)) return V4_EMPTY
  // Non si usa Intl: il locale italiano non raggruppa i numeri a quattro cifre (7000 → "7000").
  const abs = Math.abs(Math.round(n))
  const grouped = String(abs).replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return n < 0 ? `${MINUS}${grouped}` : grouped
}

/** Gol attesi: "1,2 - 1,6". */
export function fmtGoalsRange(home: number | null | undefined, away: number | null | undefined): string {
  return `${fmtDecimal(home, 1)} - ${fmtDecimal(away, 1)}`
}

/** Punteggio: "1 - 2". */
export function fmtScore(home: number | null | undefined, away: number | null | undefined): string {
  if (!isNum(home) || !isNum(away)) return V4_EMPTY
  return `${home} - ${away}`
}

function safeDate(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Orario su Europe/Rome: "20:45". */
export function fmtTimeRome(iso: string | null | undefined): string {
  const d = safeDate(iso)
  if (!d) return V4_EMPTY
  return new Intl.DateTimeFormat('it-IT', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: ROME,
  }).format(d)
}

/** Data e ora su Europe/Rome: "21/09 alle 19:30". */
export function fmtDateTimeRome(iso: string | null | undefined): string {
  const d = safeDate(iso)
  if (!d) return V4_EMPTY
  const day = new Intl.DateTimeFormat('it-IT', {
    day: '2-digit',
    month: '2-digit',
    timeZone: ROME,
  }).format(d)
  return `${day} alle ${fmtTimeRome(iso)}`
}

/** Data ISO su Europe/Rome della partita: "2026-09-21". */
export function isoDateRome(iso: string): string {
  const d = safeDate(iso)
  if (!d) return ''
  return new Intl.DateTimeFormat('en-CA', { timeZone: ROME }).format(d)
}

function localNoon(dateIso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateIso)
  if (!m) return null
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12)
}

/** Etichetta giorno: "lun 21/09". */
export function fmtDayLabel(dateIso: string): string {
  const d = localNoon(dateIso)
  if (!d) return dateIso
  const weekday = new Intl.DateTimeFormat('it-IT', { weekday: 'short' }).format(d).replace('.', '')
  const [, m, day] = dateIso.split('-')
  return `${weekday} ${day}/${m}`
}

/** Data lunga: "lunedì 21 settembre". */
export function fmtDayLong(dateIso: string): string {
  const d = localNoon(dateIso)
  if (!d) return dateIso
  return new Intl.DateTimeFormat('it-IT', { weekday: 'long', day: 'numeric', month: 'long' }).format(d)
}

/** Data breve "21/09" da ISO YYYY-MM-DD. */
export function fmtDateShort(dateIso: string | null | undefined): string {
  if (!dateIso) return V4_EMPTY
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateIso)
  if (!m) return dateIso
  return `${m[3]}/${m[2]}`
}

/** Prime 12 cifre esadecimali dell'impronta, senza prefisso "sha256:". */
export function digestShort(digest: string | null | undefined, length = 12): string {
  if (!digest) return V4_EMPTY
  const hex = digest.replace(/^sha256[:\s]*/i, '')
  return `${hex.slice(0, length)}…`
}

/** Ordinale italiano compatto: 3 → "3º". */
export function fmtOrdinal(n: number | null | undefined): string {
  if (!isNum(n)) return V4_EMPTY
  return `${Math.round(n)}º`
}

export function isIsoDate(value: string | null | undefined): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const d = localNoon(value)
  return d != null && !Number.isNaN(d.getTime())
}

export function capitalize(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s
}
