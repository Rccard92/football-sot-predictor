/** Ora della quota del tool (documento "Modifiche" di Giovanni, 09/11/2026): si vede sopra le quote, con un
 *  avviso se ha piu' di 6 ore (la quota del mattino nel pomeriggio, o quella di ieri per le partite di oggi). */

export const STALE_HOURS = 6

export function oddsAge(iso: string | null | undefined, now: number = Date.now()): { text: string; hours: number; stale: boolean } | null {
  if (!iso) return null
  const t = new Date(iso).getTime()
  if (!Number.isFinite(t)) return null
  const hours = Math.max(0, (now - t) / 3600000)
  const time = new Date(t).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Rome' })
  const day = (d: number) => new Date(d).toLocaleDateString('sv-SE', { timeZone: 'Europe/Rome' })
  const when =
    day(t) === day(now)
      ? `oggi alle ${time}`
      : day(t) === day(now - 86400000)
        ? `ieri alle ${time}`
        : `il ${new Date(t).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', timeZone: 'Europe/Rome' })} alle ${time}`
  const whole = Math.floor(hours)
  const ago = hours < 1 ? 'meno di un’ora fa' : `${whole} ${whole === 1 ? 'ora' : 'ore'} fa`
  return { text: `Quote lette ${when} (${ago})`, hours, stale: hours > STALE_HOURS }
}
