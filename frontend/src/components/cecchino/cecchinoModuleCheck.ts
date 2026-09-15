import type { LiveModelPrediction } from '../../lib/cecchinoLiveApi'

/**
 * Controllo dei moduli sul mercato indicato da un pattern.
 * I moduli ragionano da soli (probabilità del modello, Intensità Goal, Equilibrio, valore alla quota):
 * qui si legge solo se la loro lettura va nella stessa direzione del pattern o no.
 */

export type CheckOutcome = 1 | 0 | -1
export type ModuleCheck = { name: string; outcome: CheckOutcome; text: string }
export type ModuleVerdictKey = 'confirmed' | 'denied' | 'mixed' | 'neutral'
export type ModuleVerdict = { key: ModuleVerdictKey; label: string; checks: ModuleCheck[] }

const RESULT_SETS: Record<string, string[]> = {
  HOME: ['1'], DRAW: ['X'], AWAY: ['2'], ONE_X: ['1', 'X'], X_TWO: ['X', '2'], ONE_TWO: ['1', '2'],
}
const OUTCOME_KEY: Record<string, string> = { '1': 'HOME', X: 'DRAW', '2': 'AWAY' }
const OUTCOME_NAME: Record<string, string> = { '1': 'la vittoria in casa', X: 'il pareggio', '2': "la vittoria dell'ospite" }

// classi V2/V2.5 (inglese) e V3 (italiano) sulla stessa scala
const HIGH = new Set(['high', 'very_high', 'alto', 'molto_alto'])
const LOW = new Set(['low', 'very_low', 'basso', 'molto_basso'])

/** Oltre questo scarto negativo il modello vede il mercato in perdita alla quota Bet365. */
const EV_LOSS_PCT = -5

function pct(v: number): string {
  return `${(v * 100).toLocaleString('it-IT', { maximumFractionDigits: 1, minimumFractionDigits: 1 })}%`
}

function outcomeCheck(p: LiveModelPrediction, marketKey: string): ModuleCheck | null {
  const pt = marketKey.endsWith('_PT')
  const base = marketKey.replace(/_PT$/, '')
  const set = RESULT_SETS[base]
  // la X secca si legge con la credibilità del pareggio, non con il favorito
  if (!set || base === 'DRAW') return null
  const markets = p.markets ?? {}
  const probs = Object.fromEntries(
    ['1', 'X', '2'].map((o) => [o, markets[`${OUTCOME_KEY[o]}${pt ? '_PT' : ''}`]?.probability ?? null]),
  ) as Record<string, number | null>
  if (Object.values(probs).some((v) => v == null)) return null
  const fav = (['1', 'X', '2'] as const).reduce((a, b) => ((probs[b] as number) > (probs[a] as number) ? b : a))
  const favProb = probs[fav] as number
  const name = pt ? 'Esito primo tempo del modello' : 'Esito più probabile per il modello'
  if (set.includes(fav)) {
    return { name, outcome: 1, text: `Il modello vede favorito ${OUTCOME_NAME[fav]} (${pct(favProb)}).` }
  }
  if (set.length === 1 || favProb >= 0.5) {
    return { name, outcome: -1, text: `Il modello vede favorito ${OUTCOME_NAME[fav]} (${pct(favProb)}), fuori da questo mercato.` }
  }
  return { name, outcome: 0, text: `Il modello vede favorito ${OUTCOME_NAME[fav]} (${pct(favProb)}), ma senza dominare.` }
}

function drawCheck(p: LiveModelPrediction, marketKey: string): ModuleCheck | null {
  const set = RESULT_SETS[marketKey]
  if (!set) return null
  const cls = p.modules?.balance_classes?.draw_credibility ?? p.modules?.indices?.pareggio?.class ?? null
  if (!cls) return null
  const high = HIGH.has(cls)
  const low = LOW.has(cls)
  if (!high && !low) return { name: 'Credibilità del pareggio', outcome: 0, text: 'Pareggio nella media dello storico.' }
  const wantsDraw = set.includes('X')
  if (high) {
    return wantsDraw
      ? { name: 'Credibilità del pareggio', outcome: 1, text: 'Pareggio più credibile della media: sostiene il mercato.' }
      : { name: 'Credibilità del pareggio', outcome: -1, text: 'Pareggio più credibile della media: il mercato lo esclude.' }
  }
  return wantsDraw
    ? { name: 'Credibilità del pareggio', outcome: set.length === 1 ? -1 : 0, text: 'Pareggio meno credibile della media.' }
    : { name: 'Credibilità del pareggio', outcome: 1, text: 'Pareggio poco credibile: sostiene un esito secco.' }
}

function coherenceCheck(p: LiveModelPrediction, marketKey: string): ModuleCheck | null {
  if (!RESULT_SETS[marketKey.replace(/_PT$/, '')]) return null
  const cls = p.modules?.balance_classes?.gap_coherence
  if (!cls) return null
  if (cls === 'confirmed' || cls === 'strongly_confirmed') {
    return { name: 'Coerenza picchetti / modello gol', outcome: 1, text: 'Picchetti e modello gol leggono la partita allo stesso modo.' }
  }
  if (cls === 'weak' || cls === 'not_confirmed' || cls === 'very_weak') {
    return { name: 'Coerenza picchetti / modello gol', outcome: -1, text: 'Picchetti e modello gol leggono la partita in modo diverso: lettura poco affidabile.' }
  }
  return { name: 'Coerenza picchetti / modello gol', outcome: 0, text: 'Picchetti e modello gol concordano solo in parte.' }
}

function goalCheck(p: LiveModelPrediction, marketKey: string): ModuleCheck | null {
  const m = /^(OVER|UNDER)_(\d+)_(\d+)$/.exec(marketKey)
  if (!m) return null
  const line = Number(`${m[2]}.${m[3]}`)
  if (line < 1.5) return null
  const cls = p.modules?.goal_intensity_final ?? p.modules?.indices?.intensita_goal?.class ?? null
  if (!cls) return null
  const over = m[1] === 'OVER'
  const name = 'Intensità Goal'
  if (HIGH.has(cls)) {
    return { name, outcome: over ? 1 : -1, text: `Partita da più gol della media del campionato: ${over ? 'sostiene' : 'va contro'} il mercato.` }
  }
  if (LOW.has(cls)) {
    return { name, outcome: over ? -1 : 1, text: `Partita da meno gol della media del campionato: ${over ? 'va contro' : 'sostiene'} il mercato.` }
  }
  return { name, outcome: 0, text: 'Gol attesi nella media del campionato.' }
}

function valueCheck(p: LiveModelPrediction, marketKey: string): ModuleCheck | null {
  const m = p.markets?.[marketKey]
  if (!m || m.edge_pct == null || m.probability == null) return null
  const ev = m.edge_pct
  const evText = `${ev > 0 ? '+' : ''}${ev.toLocaleString('it-IT', { maximumFractionDigits: 1, minimumFractionDigits: 1 })}%`
  const name = 'Valore alla quota Bet365'
  if (ev > 0) return { name, outcome: 1, text: `Con la sua probabilità (${pct(m.probability)}) il modello vede il mercato in profitto: ${evText} per giocata.` }
  if (ev <= EV_LOSS_PCT) return { name, outcome: -1, text: `Con la sua probabilità (${pct(m.probability)}) il modello vede il mercato in perdita: ${evText} per giocata.` }
  return { name, outcome: 0, text: `Con la sua probabilità (${pct(m.probability)}) il modello è vicino al pareggio: ${evText} per giocata.` }
}

export function moduleVerdict(p: LiveModelPrediction | undefined, marketKey: string): ModuleVerdict {
  const checks = p
    ? [outcomeCheck, drawCheck, coherenceCheck, goalCheck, valueCheck]
        .map((fn) => fn(p, marketKey))
        .filter((c): c is ModuleCheck => c != null)
    : []
  const plus = checks.filter((c) => c.outcome === 1).length
  const minus = checks.filter((c) => c.outcome === -1).length
  if (plus > 0 && minus === 0) return { key: 'confirmed', label: 'Pattern confermato dai moduli', checks }
  if (minus > 0 && plus === 0) return { key: 'denied', label: 'Pattern smentito dai moduli', checks }
  if (plus > 0 && minus > 0) return { key: 'mixed', label: 'Moduli discordanti', checks }
  return { key: 'neutral', label: 'Moduli senza indicazione', checks }
}
