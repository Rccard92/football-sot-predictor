import type { ModelRelevantField } from '../../lib/api'

export function isFutureCandidateField(field: ModelRelevantField): boolean {
  return field.model_v04_status === 'not_used_v04' && field.classification === 'TENERE_FUTURO_MODELLO'
}

/** Badge compatto stato v0.4 / ruolo nel catalogo (solo UI). */
export function badgeV04Display(field: ModelRelevantField): string {
  if (field.classification === 'SORGENTE_DERIVATA_TECNICA' || field.selectable === false) {
    return 'Fonte tecnica'
  }
  const s = field.model_v04_status
  if (s === 'used_v04') return 'Usato da v0.4'
  if (s === 'not_used_v04') {
    if (isFutureCandidateField(field)) return 'Candidata futura'
    return 'Non usato da v0.4'
  }
  if (s === 'implemented_not_used' || s === 'solo_implementato') return 'Implementato, non usato'
  if (s === 'to_implement' || s === 'da_implementare') return 'Da implementare'
  return s.replace(/_/g, ' ')
}
