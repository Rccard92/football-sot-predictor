import { HEATMAP_COLUMNS, HEATMAP_SIGNAL_ROWS } from './cecchinoSignalsApi'

export type SourceColumn = (typeof HEATMAP_COLUMNS)[number]

export type CecchinoSignalFormulaEntry = {
  signal_group: string
  signal_label: string
  source_column: SourceColumn
  source_cell: string | null
  excel_formula: string | null
  readable_formula: string
  target_market_label: string | null
  evaluation_rule: string | null
  is_active_column: boolean
}

export const CECCHINO_HEATMAP_FORMULA_INTRO = {
  description:
    'Ogni cella della heatmap aggrega tutte le partite in cui quel segnale si è acceso su quella specifica colonna Excel. Il valore principale indica quante volte il segnale è stato attivato. Il rapporto W/L indica quante volte il target associato è andato a buon fine dopo il risultato finale della partita.',
  formulas: [
    'Attivazioni = count(signal_value = SI)',
    'Valutati = won + lost',
    'Success rate = won / valutati × 100',
    'Pending e non valutabili non entrano nel success rate.',
  ],
} as const

export const CECCHINO_SCALA_MAPPING_NOTE =
  'Nota importante: la colonna SCALA è prevista solo per 1X e X2. La cella G48 appartiene a 1X/SCALA, mentre G54 appartiene a X2/SCALA. Le righe 1 e 2 non hanno segnali SCALA.'

const INACTIVE_READABLE = 'Colonna non prevista per questo segnale'

function inactive(
  signal_group: string,
  signal_label: string,
  source_column: SourceColumn,
  target: string | null,
  evaluation: string | null,
): CecchinoSignalFormulaEntry {
  return {
    signal_group,
    signal_label,
    source_column,
    source_cell: null,
    excel_formula: null,
    readable_formula: INACTIVE_READABLE,
    target_market_label: target,
    evaluation_rule: evaluation,
    is_active_column: false,
  }
}

function active(
  signal_group: string,
  signal_label: string,
  source_column: SourceColumn,
  source_cell: string,
  excel_formula: string,
  readable_formula: string,
  target: string,
  evaluation: string,
): CecchinoSignalFormulaEntry {
  return {
    signal_group,
    signal_label,
    source_column,
    source_cell,
    excel_formula,
    readable_formula,
    target_market_label: target,
    evaluation_rule: evaluation,
    is_active_column: true,
  }
}

const UNDER_TARGET = 'Under 2.5 FT'
const UNDER_EVAL = 'W se totale gol FT ≤ 2 · L se totale gol FT ≥ 3'

const DRAW_TARGET = 'Segno X FT'
const DRAW_EVAL = 'W se FT casa = FT trasferta · L se FT casa ≠ FT trasferta'

const OVER_TARGET = 'Over 2.5 FT'
const OVER_EVAL = 'W se totale gol FT ≥ 3 · L se totale gol FT ≤ 2'

const HOME_TARGET = '1 FT'
const HOME_EVAL = 'W se FT casa > FT trasferta · L altrimenti'

const ONE_X_TARGET = '1X FT'
const ONE_X_EVAL = 'W se casa vince o pareggia · L se vince trasferta'

const AWAY_TARGET = '2 FT'
const AWAY_EVAL = 'W se FT trasferta > FT casa · L altrimenti'

const X_TWO_TARGET = 'X2 FT'
const X_TWO_EVAL = 'W se trasferta vince o pareggia · L se vince casa'

const ONE_TWO_TARGET = '12 FT'
const ONE_TWO_EVAL = 'W se non esce pareggio · L se esce pareggio'

export const CECCHINO_SIGNAL_FORMULA_LEGEND: CecchinoSignalFormulaEntry[] = [
  // UNDER 2.5
  active(
    'UNDER_UNDER_PT',
    'UNDER 2.5',
    'EXCEL_D',
    'D39',
    '=IF(AND(F36<0.9,F36>-0.8),"SI","NO")',
    'Si accende quando il delta F36 è vicino allo zero, quindi quando quota 1 e quota 2 sono molto vicine.\n\nCondizione: F36 < 0.90 AND F36 > -0.80',
    UNDER_TARGET,
    UNDER_EVAL,
  ),
  active(
    'UNDER_UNDER_PT',
    'UNDER 2.5',
    'EXCEL_E',
    'E39',
    '=IFERROR(IF(AND(F32/F35>0.88,F33/F35>0.88,F34/F35>0.88,F32/F35<1.2,F33/F35<1.2,F34/F35<1.2),"SI","NO"),"NO")',
    'Si accende quando le quote matematiche 1, X e 2 sono tutte vicine alla media F35, quindi la partita è molto equilibrata sui tre esiti.\n\nCondizione: F32/F35 tra 0.88 e 1.20 · F33/F35 tra 0.88 e 1.20 · F34/F35 tra 0.88 e 1.20',
    UNDER_TARGET,
    UNDER_EVAL,
  ),
  active(
    'UNDER_UNDER_PT',
    'UNDER 2.5',
    'EXCEL_F',
    'F39',
    '=IF(AND(F36<=1.53,F36>=-1.5,F33<=3),"SI","NO")',
    'Si accende quando F36 è contenuto e la quota X Cecchino è bassa o interessante.\n\nCondizione: F36 tra -1.50 e 1.53 · Quota X F33 <= 3.00',
    UNDER_TARGET,
    UNDER_EVAL,
  ),
  active(
    'UNDER_UNDER_PT',
    'UNDER 2.5',
    'EXCEL_G',
    'G39',
    '=IF(AND(F36<=1.33,F36>=-1.23,F33<4),"SI","NO")',
    'Si accende quando F36 è contenuto e la quota X non è troppo alta.\n\nCondizione: F36 tra -1.23 e 1.33 · Quota X F33 < 4.00',
    UNDER_TARGET,
    UNDER_EVAL,
  ),
  inactive('UNDER_UNDER_PT', 'UNDER 2.5', 'SCALA', UNDER_TARGET, UNDER_EVAL),

  // SEGNO X
  active(
    'DRAW',
    'SEGNO X',
    'EXCEL_D',
    'D42',
    '=IF(AND(F36<0.6,F36>-0.57),"SI","NO")',
    'Si accende quando F36 è quasi neutro, quindi quota 1 e quota 2 sono estremamente vicine.\n\nCondizione: F36 < 0.60 AND F36 > -0.57',
    DRAW_TARGET,
    DRAW_EVAL,
  ),
  active(
    'DRAW',
    'SEGNO X',
    'EXCEL_E',
    'E42',
    '=IF(AND(F33<3.3,F36<=1.47,F36>=-1.4),"SI","NO")',
    'Si accende quando la quota X Cecchino è bassa e F36 resta in area equilibrio.\n\nCondizione: Quota X F33 < 3.30 · F36 tra -1.40 e 1.47',
    DRAW_TARGET,
    DRAW_EVAL,
  ),
  active(
    'DRAW',
    'SEGNO X',
    'EXCEL_F',
    'F42',
    '=IF(AND(F33<=2.4,F36>-1.7),"SI","NO")',
    'Si accende quando la quota X è molto bassa e F36 non spinge troppo verso il 2.\n\nCondizione: Quota X F33 <= 2.40 · F36 > -1.70',
    DRAW_TARGET,
    DRAW_EVAL,
  ),
  active(
    'DRAW',
    'SEGNO X',
    'EXCEL_G',
    'G42',
    '=IF(AND(F33<=3,F36<2,F36>-1.6),"SI","NO")',
    'Si accende quando la quota X è buona e F36 resta entro una fascia compatibile con equilibrio.\n\nCondizione: Quota X F33 <= 3.00 · F36 tra -1.60 e 2.00',
    DRAW_TARGET,
    DRAW_EVAL,
  ),
  inactive('DRAW', 'SEGNO X', 'SCALA', DRAW_TARGET, DRAW_EVAL),

  // OVER 2.5
  active(
    'OVER_OVER_PT',
    'OVER 2.5',
    'EXCEL_D',
    'D45',
    '=IF(AND(OR(F36>1.7,F36<-1.5),F33>=6),"SI","NO")',
    'Si accende quando F36 indica forte squilibrio tra 1 e 2 e la quota X è molto alta.\n\nCondizione: (F36 > 1.70 OR F36 < -1.50) AND quota X F33 >= 6.00',
    OVER_TARGET,
    OVER_EVAL,
  ),
  active(
    'OVER_OVER_PT',
    'OVER 2.5',
    'EXCEL_E',
    'E45',
    '=IF(OR(D60="SI",E60="SI"),"SI","NO")',
    'Si accende quando almeno uno dei segnali 12 è attivo, quindi quando il modello esclude maggiormente il pareggio.\n\nCondizione: D60 = SI OR E60 = SI',
    OVER_TARGET,
    OVER_EVAL,
  ),
  active(
    'OVER_OVER_PT',
    'OVER 2.5',
    'EXCEL_F',
    'F45',
    '=IF(AND(F33>=5,F36>2),"SI",IF(AND(F33>=5,F36<-2.1),"SI","NO"))',
    'Si accende quando la quota X è alta e F36 indica forte sbilanciamento verso uno dei due lati.\n\nCondizione: Quota X F33 >= 5.00 AND (F36 > 2.00 OR F36 < -2.10)',
    OVER_TARGET,
    OVER_EVAL,
  ),
  active(
    'OVER_OVER_PT',
    'OVER 2.5',
    'EXCEL_G',
    'G45',
    '=IF(AND(F33>=4,F36>2.55),"SI",IF(AND(F33>=4,F36<-2.4),"SI","NO"))',
    'Si accende quando la quota X è alta e F36 mostra squilibrio molto forte.\n\nCondizione: Quota X F33 >= 4.00 AND (F36 > 2.55 OR F36 < -2.40)',
    OVER_TARGET,
    OVER_EVAL,
  ),
  inactive('OVER_OVER_PT', 'OVER 2.5', 'SCALA', OVER_TARGET, OVER_EVAL),

  // 1
  active(
    'HOME',
    '1',
    'EXCEL_D',
    'D48',
    '=IF(AND(G48="SI",F32<F34-4,F32<F33-2.5),"SI","NO")',
    'Si accende quando la scala 1X è attiva e la quota 1 Cecchino è molto più bassa sia della quota 2 sia della quota X.\n\nCondizione: G48 = SI AND F32 < F34 - 4 AND F32 < F33 - 2.5\n\nNota: G48 non è un segnale SCALA della riga 1. G48 appartiene alla riga 1X, colonna SCALA.',
    HOME_TARGET,
    HOME_EVAL,
  ),
  inactive('HOME', '1', 'EXCEL_E', HOME_TARGET, HOME_EVAL),
  inactive('HOME', '1', 'EXCEL_F', HOME_TARGET, HOME_EVAL),
  inactive('HOME', '1', 'EXCEL_G', HOME_TARGET, HOME_EVAL),
  inactive('HOME', '1', 'SCALA', HOME_TARGET, HOME_EVAL),

  // 1X
  active(
    'ONE_X',
    '1X',
    'EXCEL_D',
    'D51',
    '=IF(AND(F32<2.8,F33<=4,F35>4),"SI","NO")',
    'Si accende quando la quota 1 è bassa, la quota X è ancora contenuta e la media delle quote indica uno scenario favorevole alla doppia chance 1X.\n\nCondizione: F32 < 2.80 · F33 <= 4.00 · F35 > 4.00',
    ONE_X_TARGET,
    ONE_X_EVAL,
  ),
  active(
    'ONE_X',
    '1X',
    'EXCEL_E',
    'E51',
    '=IF(AND(G48="SI"),"SI","NO")',
    'Si accende quando la scala 1X è attiva.\n\nCondizione: G48 = SI',
    ONE_X_TARGET,
    ONE_X_EVAL,
  ),
  active(
    'ONE_X',
    '1X',
    'EXCEL_F',
    'F51',
    '=IF(AND(F32<=1.8,F36>=2.5,F34>F33),"SI","NO")',
    'Si accende quando la quota 1 è molto bassa, F36 spinge verso il lato casa e la quota 2 è più alta della quota X.\n\nCondizione: F32 <= 1.80 · F36 >= 2.50 · F34 > F33',
    ONE_X_TARGET,
    ONE_X_EVAL,
  ),
  active(
    'ONE_X',
    '1X',
    'EXCEL_G',
    'G51',
    '=IF(AND(F32<=2,F34>=4),"SI","NO")',
    'Si accende quando la quota 1 è bassa e la quota 2 è alta.\n\nCondizione: F32 <= 2.00 · F34 >= 4.00',
    ONE_X_TARGET,
    ONE_X_EVAL,
  ),
  active(
    'ONE_X',
    '1X',
    'SCALA',
    'G48',
    '=IFERROR(IF(AND(F32<F33,F33<F34,F32<F34),"SI","NO"),"NO")',
    'Si accende quando le quote sono in scaletta 1-X-2, cioè quota 1 più bassa di X e X più bassa di 2.\n\nCondizione: F32 < F33 · F33 < F34 · F32 < F34',
    ONE_X_TARGET,
    ONE_X_EVAL,
  ),

  // 2
  active(
    'AWAY',
    '2',
    'EXCEL_D',
    'D54',
    '=IF(AND(G54="SI",F34<F32-4.5,F34<F33-3),"SI","NO")',
    'Si accende quando la scala X2 è attiva e la quota 2 Cecchino è molto più bassa sia della quota 1 sia della quota X.\n\nCondizione: G54 = SI AND F34 < F32 - 4.5 AND F34 < F33 - 3\n\nNota: G54 non è un segnale SCALA della riga 2. G54 appartiene alla riga X2, colonna SCALA.',
    AWAY_TARGET,
    AWAY_EVAL,
  ),
  inactive('AWAY', '2', 'EXCEL_E', AWAY_TARGET, AWAY_EVAL),
  inactive('AWAY', '2', 'EXCEL_F', AWAY_TARGET, AWAY_EVAL),
  inactive('AWAY', '2', 'EXCEL_G', AWAY_TARGET, AWAY_EVAL),
  inactive('AWAY', '2', 'SCALA', AWAY_TARGET, AWAY_EVAL),

  // X2
  active(
    'X_TWO',
    'X2',
    'EXCEL_D',
    'D57',
    '=IF(AND(F34<=1.8,F32>=3.5,F34<F33),"SI","NO")',
    'Si accende quando la quota 2 è molto bassa, la quota 1 è alta e la quota 2 è più bassa della quota X.\n\nCondizione: F34 <= 1.80 · F32 >= 3.50 · F34 < F33',
    X_TWO_TARGET,
    X_TWO_EVAL,
  ),
  active(
    'X_TWO',
    'X2',
    'EXCEL_E',
    'E57',
    '=IF(AND(F34+3<F32,F34<F33,F33<F32,F33<4),"SI","NO")',
    'Si accende quando la quota 2 è nettamente più bassa della quota 1, più bassa della X, e la X resta sotto 4.\n\nCondizione: F34 + 3 < F32 · F34 < F33 · F33 < F32 · F33 < 4.00',
    X_TWO_TARGET,
    X_TWO_EVAL,
  ),
  active(
    'X_TWO',
    'X2',
    'EXCEL_F',
    'F57',
    '=IF(AND(F34<=2,F32>=4),"SI","NO")',
    'Si accende quando la quota 2 è bassa e la quota 1 è alta.\n\nCondizione: F34 <= 2.00 · F32 >= 4.00',
    X_TWO_TARGET,
    X_TWO_EVAL,
  ),
  active(
    'X_TWO',
    'X2',
    'EXCEL_G',
    'G57',
    '=IF(AND(G54="SI"),"SI","NO")',
    'Si accende quando la scala X2 è attiva.\n\nCondizione: G54 = SI',
    X_TWO_TARGET,
    X_TWO_EVAL,
  ),
  active(
    'X_TWO',
    'X2',
    'SCALA',
    'G54',
    '=IFERROR(IF(AND(F32>F33,F33>F34,F32>F34),"SI","NO"),"NO")',
    'Si accende quando le quote sono in scaletta 2-X-1, cioè quota 2 più bassa di X e X più bassa di 1.\n\nCondizione: F32 > F33 · F33 > F34 · F32 > F34',
    X_TWO_TARGET,
    X_TWO_EVAL,
  ),

  // 12
  active(
    'ONE_TWO',
    '12',
    'EXCEL_D',
    'D60',
    '=IF(AND(F32<=1.8,F33>3.5),"SI",IF(AND(F34<1.7,F33>3.5),"SI","NO"))',
    'Si accende quando uno dei due lati 1 o 2 è molto basso e la quota X è alta, quindi il pareggio è meno probabile.\n\nCondizione: (F32 <= 1.80 AND F33 > 3.50) OR (F34 < 1.70 AND F33 > 3.50)',
    ONE_TWO_TARGET,
    ONE_TWO_EVAL,
  ),
  active(
    'ONE_TWO',
    '12',
    'EXCEL_E',
    'E60',
    '=IF(AND(F33>=5.5,F32<2.5,F36<-1.5),"SI",IF(AND(F33>=5.5,F34<2.3,F36>1.5),"SI","NO"))',
    'Si accende quando la quota X è molto alta e uno dei due lati è nettamente favorito.\n\nCondizione: (F33 >= 5.50 AND F32 < 2.50 AND F36 < -1.50) OR (F33 >= 5.50 AND F34 < 2.30 AND F36 > 1.50)',
    ONE_TWO_TARGET,
    ONE_TWO_EVAL,
  ),
  inactive('ONE_TWO', '12', 'EXCEL_F', ONE_TWO_TARGET, ONE_TWO_EVAL),
  inactive('ONE_TWO', '12', 'EXCEL_G', ONE_TWO_TARGET, ONE_TWO_EVAL),
  inactive('ONE_TWO', '12', 'SCALA', ONE_TWO_TARGET, ONE_TWO_EVAL),
]

export function getSignalTabs() {
  return HEATMAP_SIGNAL_ROWS.map((row) => ({
    signal_group: row.group,
    signal_label: row.label,
  }))
}

export function getLegendEntriesForSignal(signalGroup: string): CecchinoSignalFormulaEntry[] {
  const byGroup = CECCHINO_SIGNAL_FORMULA_LEGEND.filter((e) => e.signal_group === signalGroup)
  return HEATMAP_COLUMNS.map((col) => {
    const found = byGroup.find((e) => e.source_column === col)
    if (found) return found
    const label = HEATMAP_SIGNAL_ROWS.find((r) => r.group === signalGroup)?.label ?? signalGroup
    return inactive(signalGroup, label, col, null, null)
  })
}

export const COLUMN_DISPLAY_LABELS: Record<SourceColumn, string> = {
  EXCEL_D: 'Excel D',
  EXCEL_E: 'Excel E',
  EXCEL_F: 'Excel F',
  EXCEL_G: 'Excel G',
  SCALA: 'Scala',
}
