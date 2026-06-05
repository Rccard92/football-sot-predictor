import { useEffect, useState } from 'react'

function getVisibleCount(): number {
  if (typeof window === 'undefined') return 7
  if (window.matchMedia('(min-width: 1024px)').matches) return 7
  if (window.matchMedia('(min-width: 768px)').matches) return 5
  return 3
}

export function useTimelineVisibleCount(): number {
  const [visibleCount, setVisibleCount] = useState(getVisibleCount)

  useEffect(() => {
    const lg = window.matchMedia('(min-width: 1024px)')
    const md = window.matchMedia('(min-width: 768px)')

    const update = () => setVisibleCount(getVisibleCount())
    lg.addEventListener('change', update)
    md.addEventListener('change', update)
    return () => {
      lg.removeEventListener('change', update)
      md.removeEventListener('change', update)
    }
  }, [])

  return visibleCount
}

function clampWindowStart(start: number, visibleCount: number, totalDays: number): number {
  if (totalDays <= visibleCount) return 0
  const maxStart = totalDays - visibleCount
  return Math.max(0, Math.min(start, maxStart))
}

export function centerWindowOnToday(
  days: Array<{ date: string; is_today?: boolean }>,
  visibleCount: number,
): number {
  if (!days.length) return 0
  const todayIndex = days.findIndex((d) => d.is_today)
  const anchor = todayIndex >= 0 ? todayIndex : 0
  return clampWindowStart(anchor - Math.floor(visibleCount / 2), visibleCount, days.length)
}

export { clampWindowStart }
