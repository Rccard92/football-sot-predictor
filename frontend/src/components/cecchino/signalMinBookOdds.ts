/** Soglie minime quota book — display read-only allineato al backend. */
export const SIGNAL_MIN_BOOK_ODDS_DISPLAY: Array<{ label: string; minOdd: string }> = [
  { label: 'X', minOdd: '3.00' },
  { label: 'X PT', minOdd: '1.90' },
  { label: '1X', minOdd: '1.37' },
  { label: 'X2', minOdd: '1.45' },
  { label: '1/2', minOdd: '1.37' },
  { label: 'Under 2.5', minOdd: '2.00' },
  { label: 'Over 2.5', minOdd: '1.85' },
]

export const SIGNAL_VALUE_FILTER_NOTE =
  'Il monitoraggio include solo segnali comprabili: quota book ≥ quota Cecchino e quota book ≥ soglia minima del segno.'

export const SIGNAL_LAB_FILTER_NOTE =
  'Filtro operativo: un segnale entra nel Lab solo se ha valore matematico e supera la quota minima operativa.'
