/** Etichette badge italiane per catalogo diretto API. */

export function labelApiFound(): string {
  return 'Trovato nello scan API'
}

export function labelDbStatus(s: string): string {
  const m: Record<string, string> = {
    saved_column: 'Salvato in colonna DB',
    raw_json_only: 'Presente in raw_json',
    not_saved: 'Non salvato',
    unknown: 'DB: sconosciuto',
  }
  return m[s] ?? s
}

export function labelModelV04(s: string): string {
  const m: Record<string, string> = {
    used_v04: 'Usato da v0.4',
    not_used_v04: 'Non usato da v0.4',
  }
  return m[s] ?? s
}

export function labelSampleType(s: string): string {
  const m: Record<string, string> = {
    stringa: 'stringa',
    numero: 'numero',
    percentuale: 'percentuale',
    boolean: 'boolean',
    data: 'data',
    null: 'null',
  }
  return m[s] ?? s
}
