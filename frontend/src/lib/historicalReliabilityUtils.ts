import type { HistoricalReliabilityItem } from './cecchinoKpiSignalsApi'

export function mapHistoricalReliabilityForFixture(
  items: Record<string, HistoricalReliabilityItem>,
  todayFixtureId: number | null | undefined,
): Record<string, HistoricalReliabilityItem> {
  const byMarket: Record<string, HistoricalReliabilityItem> = {}
  for (const [key, item] of Object.entries(items)) {
    if (
      todayFixtureId != null &&
      item.today_fixture_id != null &&
      Number(item.today_fixture_id) !== Number(todayFixtureId)
    ) {
      continue
    }
    const marketKey = item.market_key || item.selection
    if (marketKey) byMarket[marketKey] = item
    const colon = key.indexOf(':')
    if (colon > 0) {
      const mk = key.slice(colon + 1)
      if (mk) byMarket[mk] = item
    }
  }
  return byMarket
}
