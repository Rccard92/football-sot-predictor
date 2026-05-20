import type { SportApiDisplayRole } from '../types/sportapi'

export function roleLabel(role: SportApiDisplayRole): string {
  switch (role) {
    case 'P':
      return 'Portiere'
    case 'D':
      return 'Difensore'
    case 'C':
      return 'Centrocampista'
    case 'A':
      return 'Attaccante'
    default:
      return role
  }
}

export function roleBadgeClass(role: SportApiDisplayRole): string {
  switch (role) {
    case 'P':
      return 'bg-amber-100 text-amber-950 border-amber-300'
    case 'D':
      return 'bg-emerald-100 text-emerald-950 border-emerald-300'
    case 'C':
      return 'bg-sky-100 text-sky-950 border-sky-300'
    case 'A':
      return 'bg-rose-100 text-rose-950 border-rose-300'
    default:
      return 'bg-slate-100 text-slate-800 border-slate-300'
  }
}
