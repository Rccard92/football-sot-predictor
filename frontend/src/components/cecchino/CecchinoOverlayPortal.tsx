import { createPortal } from 'react-dom'
import type { ReactNode } from 'react'

type Props = {
  children: ReactNode
  className?: string
}

export function CecchinoOverlayPortal({ children, className }: Props) {
  if (typeof document === 'undefined') return null
  return createPortal(
    <div className={className ?? 'fixed inset-0 z-[60]'}>{children}</div>,
    document.body,
  )
}
