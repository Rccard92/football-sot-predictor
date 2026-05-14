/** Etichette IT per classificazione catalogo model-relevant (badge compatto). */

const CATEGORY_BADGE_SHORT: Record<string, string> = {
  TENERE_MODELLO_DIRETTO: 'Modello diretto',
  TENERE_MODELLO_CONTESTO: 'Modello contesto',
  TENERE_FUTURO_MODELLO: 'Futuro modello',
  SORGENTE_DERIVATA_TECNICA: 'Fonte tecnica',
}

/** Tooltip sul badge categoria (a capo in tooltip CSS). */
export const CATEGORY_STATISTICA_TOOLTIP = [
  'Modello diretto: variabile che può entrare direttamente nel calcolo statistico.',
  'Modello contesto: variabile utile per rischio, motivazione o contesto, ma non sempre entra nel numero finale.',
  'Futuro modello: variabile interessante per versioni successive o altri mercati.',
  'Fonte tecnica: dato utile per calcolare altre variabili, ma non selezionabile come variabile statistica.',
].join('\n\n')

export function labelModelRelevantClassification(c: string): string {
  return CATEGORY_BADGE_SHORT[c] ?? c
}

export function categoryBadgeShort(c: string): string {
  return CATEGORY_BADGE_SHORT[c] ?? c
}
