/** Etichette IT per classificazione catalogo model-relevant. */

const CLASSIFICATION_LABELS: Record<string, string> = {
  TENERE_MODELLO_DIRETTO: 'Modello diretto',
  TENERE_MODELLO_CONTESTO: 'Contesto modello',
  TENERE_FUTURO_MODELLO: 'Futuro modello',
  SORGENTE_DERIVATA_TECNICA: 'Fonte tecnica (derivate)',
}

export function labelModelRelevantClassification(c: string): string {
  return CLASSIFICATION_LABELS[c] ?? c
}
