export type ChangelogType = 'major' | 'minor' | 'patch'

export type ChangelogEntry = {
  version: string
  date: string
  title: string
  type: ChangelogType
  summary: string
  highlights: string[]
  visible_to_user: boolean
}

export const MODEL_CHANGELOG: ChangelogEntry[] = [
  {
    version: '2.0.0',
    date: '2026-05-19',
    title: 'v2.0 SOT Lineup Impact',
    type: 'major',
    summary:
      'Nuovo modello che applica l’impatto formazione (SportAPI) sulla base v1.1: fattore offensivo e debolezza difensiva avversaria.',
    highlights: [
      'Formula: base v1.1 × fattore offensivo × debolezza difensiva avversario',
      'Filtro rosa attuale (player_team_seasons) nei Top 5',
      'Fallback sicuro a v1.1 se lineups SportAPI assenti',
      'Pre-match readiness in payload upcoming',
    ],
    visible_to_user: true,
  },
  {
    version: '1.1.0',
    date: '2026-04-01',
    title: 'v1.1 SOT — modello stabile',
    type: 'minor',
    summary:
      'Versione stabile con 6 termini: offensiva, difensiva, split, forma, xG e player layer.',
    highlights: [
      'Nessuna chiamata API live in generazione',
      'Player layer con qualità e fallback tracciati',
      'Raccomandato quando coverage upcoming completa',
    ],
    visible_to_user: true,
  },
  {
    version: '1.0.0',
    date: '2025-12-01',
    title: 'v1.0 SOT (xG)',
    type: 'minor',
    summary: 'Versione parallela con correzione expected goals.',
    highlights: ['Allineamento opzionale con v0.4'],
    visible_to_user: false,
  },
  {
    version: '0.4.0',
    date: '2025-10-01',
    title: 'v0.4 offensive core',
    type: 'patch',
    summary: 'Core offensivo legacy.',
    highlights: [],
    visible_to_user: false,
  },
]

export function visibleChangelogEntries(): ChangelogEntry[] {
  return MODEL_CHANGELOG.filter((e) => e.visible_to_user)
}

export function legacyChangelogEntries(): ChangelogEntry[] {
  return MODEL_CHANGELOG.filter((e) => !e.visible_to_user)
}
