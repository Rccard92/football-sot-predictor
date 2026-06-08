export type BalanceLegendSeverity = 'positive' | 'warning' | 'negative' | 'neutral'

export type BalanceOperationalLegendRow = {
  f36: string
  dominantSide: string
  dominance: string
  quotaX: string
  reading: string
  severity: BalanceLegendSeverity
}

export const BALANCE_LEGEND_INTRO =
  'Questa tabella spiega come viene letta la partita combinando F36, Dominanza contestualizzata, segno dominante e Quota X Cecchino.'

export const BALANCE_LEGEND_VERSION = 'balance_operational_legend_v3_delta_force'

export const BALANCE_LEGEND_NOTES = [
  'Nota: la Dominanza non viene letta da sola. Se domina la X, una Dominanza alta rafforza l\'equilibrio. Se domina 1 o 2, una Dominanza alta può indicare falso equilibrio o squilibrio confermato.',
  'F36 misura solo la distanza tra quota 1 e quota 2. La Dominanza misura invece quanto il modello preferisce il primo scenario rispetto al secondo, considerando anche la X.',
]

export type DeltaForceLegendRow = {
  deltaRange: string
  classLabel: string
  reading: string
  severity: BalanceLegendSeverity
}

export const DELTA_FORCE_LEGEND_NOTE =
  'Il Delta Forza non sostituisce F36 e Dominanza. Serve a capire se la lettura del match è lineare o distorta rispetto al book.'

export const DELTA_FORCE_LEGEND_ROWS: DeltaForceLegendRow[] = [
  {
    deltaRange: '< 17%',
    classLabel: 'Partita statistica',
    reading: 'Lettura lineare: il modello e il book sono relativamente allineati.',
    severity: 'positive',
  },
  {
    deltaRange: '17% - 31%',
    classLabel: 'Partita non statistica',
    reading:
      'Lettura non lineare: attenzione agli esiti fissi, valutare doppie chance o mercati goal.',
    severity: 'warning',
  },
  {
    deltaRange: '> 31%',
    classLabel: 'Forte favorita / forte distorsione',
    reading: 'Disallineamento forte: il book sta comprimendo o allargando molto una quota.',
    severity: 'negative',
  },
]

export const BALANCE_OPERATIONAL_LEGEND_RULES: BalanceOperationalLegendRow[] = [
  {
    f36: '< 0,75',
    dominantSide: 'X',
    dominance: '0 - 5',
    quotaX: '≤ 3,50',
    reading: '✅ X forte — equilibrio reale, X/Under interessante',
    severity: 'positive',
  },
  {
    f36: '< 0,75',
    dominantSide: 'X',
    dominance: '6 - 10',
    quotaX: '≤ 3,50',
    reading: '✅ X molto interessante — la X rafforza l\'equilibrio',
    severity: 'positive',
  },
  {
    f36: '< 0,75',
    dominantSide: 'X',
    dominance: '> 10',
    quotaX: '≤ 3,50',
    reading: '✅ X molto forte — tipica partita da X / Under',
    severity: 'positive',
  },
  {
    f36: '< 0,75',
    dominantSide: 'X',
    dominance: 'qualsiasi',
    quotaX: '3,51 - 4,20',
    reading: '⚠ X possibile — equilibrio presente ma quota X meno forte',
    severity: 'warning',
  },
  {
    f36: '< 0,75',
    dominantSide: 'X',
    dominance: 'qualsiasi',
    quotaX: '> 4,20',
    reading: '⚠ X prima ma poco affidabile — quota X troppo alta',
    severity: 'warning',
  },
  {
    f36: '< 0,75',
    dominantSide: '1 o 2',
    dominance: '0 - 5',
    quotaX: '≤ 3,50',
    reading: '✅ X possibile — equilibrio tra 1 e 2 ancora pulito',
    severity: 'positive',
  },
  {
    f36: '< 0,75',
    dominantSide: '1 o 2',
    dominance: '6 - 10',
    quotaX: '≤ 3,50',
    reading: '⚠ Equilibrio con lieve tendenza verso 1 o 2',
    severity: 'warning',
  },
  {
    f36: '< 0,75',
    dominantSide: '1 o 2',
    dominance: '> 10',
    quotaX: 'qualsiasi',
    reading: '❌ Falso equilibrio — 1 e 2 sono vicini, ma il modello spinge su un lato',
    severity: 'negative',
  },
  {
    f36: '0,75 - 1,50',
    dominantSide: 'X',
    dominance: 'qualsiasi',
    quotaX: '≤ 3,50',
    reading: '✅ X interessante — non perfetto equilibrio laterale, ma X forte nel modello',
    severity: 'positive',
  },
  {
    f36: '0,75 - 1,50',
    dominantSide: 'X',
    dominance: 'qualsiasi',
    quotaX: '> 3,50',
    reading: '⚠ X possibile ma meno pulita',
    severity: 'warning',
  },
  {
    f36: '0,75 - 1,50',
    dominantSide: '1 o 2',
    dominance: '0 - 5',
    quotaX: '≤ 3,50',
    reading: '⚠ Partita equilibrata ma meno pulita',
    severity: 'warning',
  },
  {
    f36: '0,75 - 1,50',
    dominantSide: '1 o 2',
    dominance: '6 - 10',
    quotaX: 'qualsiasi',
    reading: '⚠ Zona grigia — tendenza leggera verso 1 o 2',
    severity: 'warning',
  },
  {
    f36: '0,75 - 1,50',
    dominantSide: '1 o 2',
    dominance: '> 10',
    quotaX: 'qualsiasi',
    reading: '➡ Tendenza verso 1 o 2',
    severity: 'neutral',
  },
  {
    f36: '> 1,50',
    dominantSide: 'X',
    dominance: 'qualsiasi',
    quotaX: '≤ 3,50',
    reading: '⚠ Partita anomala — F36 dice squilibrio, ma la X domina',
    severity: 'warning',
  },
  {
    f36: '> 1,50',
    dominantSide: 'X',
    dominance: 'qualsiasi',
    quotaX: '> 3,50',
    reading: '⚠ Anomalia da verificare — X prima ma quadro laterale squilibrato',
    severity: 'warning',
  },
  {
    f36: '> 1,50',
    dominantSide: '1 o 2',
    dominance: '0 - 5',
    quotaX: '≤ 3,50',
    reading: '⚠ Partita anomala — squilibrio quote ma X ancora bassa',
    severity: 'warning',
  },
  {
    f36: '> 1,50',
    dominantSide: '1 o 2',
    dominance: '6 - 10',
    quotaX: 'qualsiasi',
    reading: '➡ Squilibrio moderato',
    severity: 'neutral',
  },
  {
    f36: '> 1,50',
    dominantSide: '1 o 2',
    dominance: '> 10',
    quotaX: 'qualsiasi',
    reading: '✅ Squilibrio confermato — partita orientata verso 1 o 2',
    severity: 'positive',
  },
]
