/**
 * Lettura dell'indice Forma V3 (valori logaritmici: 0 = in linea con le attese).
 *
 * Soglie dalla distribuzione delle 31.035 partite della run V3 finale (#11):
 * - Risultati: meta' delle squadre tra -0,20 e +0,21, il 10% oltre +/-0,40;
 * - Gioco: meta' tra -0,12 e +0,12, il 10% oltre +/-0,23.
 * Pesi imparati dalla V3: forma gioco 0,196, forma risultati -0,008 (praticamente nulla).
 */

export type FormLevel = 'molto_sopra' | 'sopra' | 'leggermente_sopra' | 'in_linea' | 'leggermente_sotto' | 'sotto' | 'molto_sotto'

type Thresholds = { inLine: number; quartile: number; decile: number }

export const FORM_THRESHOLDS: Record<'gioco' | 'risultati', Thresholds> = {
  gioco: { inLine: 0.03, quartile: 0.12, decile: 0.23 },
  risultati: { inLine: 0.05, quartile: 0.2, decile: 0.4 },
}

export function formLevel(value: number, kind: 'gioco' | 'risultati'): FormLevel {
  const t = FORM_THRESHOLDS[kind]
  const a = Math.abs(value)
  if (a < t.inLine) return 'in_linea'
  const up = value > 0
  if (a < t.quartile) return up ? 'leggermente_sopra' : 'leggermente_sotto'
  if (a < t.decile) return up ? 'sopra' : 'sotto'
  return up ? 'molto_sopra' : 'molto_sotto'
}

export const FORM_LEVEL_LABEL: Record<FormLevel, string> = {
  molto_sopra: 'Molto sopra le attese',
  sopra: 'Sopra le attese',
  leggermente_sopra: 'Leggermente sopra le attese',
  in_linea: 'In linea con le attese',
  leggermente_sotto: 'Leggermente sotto le attese',
  sotto: 'Sotto le attese',
  molto_sotto: 'Molto sotto le attese',
}

/** Scarto percentuale rispetto alle attese (+15% = il 15% meglio del previsto). */
export function formPercent(value: number): number {
  return Math.round((Math.exp(value) - 1) * 100)
}

export function formTone(level: FormLevel): 'positive' | 'negative' | 'neutral' {
  if (level === 'in_linea') return 'neutral'
  return level.endsWith('sopra') ? 'positive' : 'negative'
}

type Side = { gioco: number; risultati: number } | null | undefined

/** Frase finale: cosa conta per la previsione e se risultati e gioco raccontano storie diverse. */
export function formReading(home: Side, away: Side): string {
  if (!home || !away) return 'Forma non disponibile per una delle due squadre.'
  const parts: string[] = []
  const diff = home.gioco - away.gioco
  if (Math.abs(diff) < FORM_THRESHOLDS.gioco.inLine) {
    parts.push('Per la previsione la V3 guarda il gioco: qui le due squadre sono alla pari.')
  } else {
    const who = diff > 0 ? 'la squadra di casa' : "l'ospite"
    const how = Math.abs(diff) < FORM_THRESHOLDS.gioco.quartile ? 'leggermente ' : ''
    parts.push(`Per la previsione la V3 guarda il gioco: qui favorisce ${how}${who}.`)
  }
  const diverge = (s: NonNullable<Side>) => {
    const r = formTone(formLevel(s.risultati, 'risultati'))
    const g = formTone(formLevel(s.gioco, 'gioco'))
    if (r === 'positive' && g === 'negative') return 'raccoglie più di quanto produce'
    if (r === 'negative' && g === 'positive') return 'produce più di quanto raccoglie'
    return null
  }
  const dh = diverge(home)
  const da = diverge(away)
  if (dh) parts.push(`La squadra di casa ${dh}.`)
  if (da) parts.push(`L'ospite ${da}.`)
  return parts.join(' ')
}
