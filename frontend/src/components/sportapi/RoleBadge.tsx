import type { SportApiDisplayRole } from '../../types/sportapi'
import { roleBadgeClass } from '../../utils/sportapiRoles'

export function RoleBadge({ role }: { role: SportApiDisplayRole }) {
  return (
    <span
      className={`inline-flex h-5 min-w-[1.25rem] shrink-0 items-center justify-center rounded border px-1 text-[10px] font-bold leading-none ${roleBadgeClass(role)}`}
      title={role}
    >
      {role}
    </span>
  )
}
