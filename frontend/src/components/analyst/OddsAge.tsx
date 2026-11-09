import { oddsAge, STALE_HOURS } from './oddsAgeText'

/** Ora della quota del tool sopra le quote, in arancio scuro se ha piu' di 6 ore (09/11/2026). */
export function OddsAge({ iso, className = '' }: { iso?: string | null; className?: string }) {
  const age = oddsAge(iso)
  if (!age) return null
  return (
    <p className={`text-[12px] ${age.stale ? 'font-medium text-amber-700' : 'text-slate-500'} ${className}`} title="Quota del book letta dal tool">
      {age.text}
      {age.stale ? ` · più di ${STALE_HOURS} ore: controlla la quota dal bookmaker` : ''}
    </p>
  )
}
