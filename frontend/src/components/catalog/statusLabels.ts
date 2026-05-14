/** Etichette italiane per badge catalogo API. */

export function labelApiStatus(s: string): string {
  const m: Record<string, string> = {
    available: 'Disponibile API',
    verify: 'Da verificare',
    not_in_provider: 'Non disponibile nel provider attuale',
    external_provider: 'Richiede provider esterno',
  }
  return m[s] ?? s
}

export function labelDbStatus(s: string): string {
  const m: Record<string, string> = {
    saved: 'Salvato nel DB',
    raw_json_only: 'Salvato solo in raw_json',
    not_imported: 'Non ancora importato',
    not_available: 'Non disponibile',
  }
  return m[s] ?? s
}

export function labelModelV04(s: string): string {
  const m: Record<string, string> = {
    used: 'Usato nella v0.4',
    indirect: 'Usato indirettamente nella v0.4',
    implemented_not_used: 'Implementato, non usato',
    to_implement: 'Da implementare',
    not_available: 'Non disponibile',
    verify: 'Da verificare',
  }
  return m[s] ?? s
}

export function labelImplementation(s: string): string {
  const m: Record<string, string> = {
    implemented: 'Implementato',
    partial: 'Parzialmente implementato',
    to_implement: 'Da implementare',
    to_verify: 'Da verificare',
  }
  return m[s] ?? s
}

export function labelDifficulty(s: string): string {
  const m: Record<string, string> = {
    bassa: 'Bassa',
    media: 'Media',
    alta: 'Alta',
    molto_alta: 'Molto alta',
  }
  return m[s] ?? s
}

export function labelMarket(slug: string): string {
  const m: Record<string, string> = {
    tutti: 'Tutti i mercati',
    tiri_in_porta: 'Tiri in porta',
    tiri_totali: 'Tiri totali',
    goal: 'Goal',
    over_under: 'Over/under',
    corner: 'Corner',
    cartellini: 'Cartellini',
    falli: 'Falli',
    player_props: 'Player props',
    contesto_rischio: 'Contesto/rischio',
    verifica_post_match: 'Verifica post-match',
    pressione_offensiva: 'Pressione offensiva',
    ritmo: 'Ritmo',
    andamento_gara: 'Andamento gara',
    live: 'Live',
    post_match: 'Post-match',
    motivation: 'Motivazione',
    contesto: 'Contesto',
    forza_squadra: 'Forza squadra',
    forma: 'Forma',
    value_betting: 'Value betting',
    difesa: 'Difesa',
    attacco_profondita: 'Attacco in profondità',
    portiere: 'Portiere',
    verifica_sot_avversari: 'Verifica SOT avversari',
    possesso: 'Possesso',
    qualita_palleggio: 'Qualità palleggio',
    controllo_partita: 'Controllo partita',
    affidabilita_campione: 'Affidabilità campione',
    tiri_squadra: 'Tiri squadra',
    lineup: 'Formazioni',
    tattica: 'Tattica',
    cambio_allenatore: 'Cambio allenatore',
    turnover: 'Turnover',
    game_state: 'Stato gara',
    arbitro: 'Arbitro',
    rigori: 'Rigori',
  }
  return m[slug] ?? slug.replace(/_/g, ' ')
}
