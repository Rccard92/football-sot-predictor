export type BalanceAnalysisFiltersState = {
  countryName: string
  f36Class: string
  dominanceClass: string
  dominanceSelection: string
  drawCredibilityClass: string
  gapClass: string
}

export const EMPTY_BALANCE_FILTERS: BalanceAnalysisFiltersState = {
  countryName: '',
  f36Class: '',
  dominanceClass: '',
  dominanceSelection: '',
  drawCredibilityClass: '',
  gapClass: '',
}
