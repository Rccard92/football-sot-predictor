/** Messaggio leggibile per errori di rete / CORS in fetch verso il backend. */
export function formatFetchError(err: unknown, endpoint?: string): string {
  const raw = err instanceof Error ? err.message : String(err)
  const lower = raw.toLowerCase()
  if (
    lower.includes('failed to fetch') ||
    lower.includes('networkerror') ||
    lower.includes('access-control') ||
    lower.includes('cors')
  ) {
    const ep = endpoint ? ` (${endpoint})` : ''
    return (
      `Backend non raggiungibile o CORS non configurato${ep}. ` +
      'Verifica che il servizio API su Railway sia attivo e che CORS_ORIGINS includa ' +
      'https://frontend-production-9b20.up.railway.app'
    )
  }
  return raw || 'Errore sconosciuto'
}

export function formatExplanationApiError(parsed: {
  message?: string | null
  failed_step?: string | null
  details?: string | null
  status?: string | null
}): string {
  const parts: string[] = []
  if (parsed.message) parts.push(parsed.message)
  if (parsed.failed_step) parts.push(`Step: ${parsed.failed_step}`)
  if (parsed.details) parts.push(String(parsed.details))
  const base = parts.join(' — ') || 'Errore durante il caricamento della spiegazione'
  if (
    parsed.failed_step !== 'build_explanation' &&
    parsed.details &&
    /offensive_production|formula terms assenti|Componente offensiva assente/i.test(parsed.details)
  ) {
    return `${base}. Suggerimento: rigenerare v1.0 (POST generate-v10-sot) se il raw_json è vecchio.`
  }
  return base
}
