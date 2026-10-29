import type { ReactNode } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { todaySkeleton } from '../cecchino/cecchinoTodayStyles'
import { ChangePasswordDialog } from './ChangePasswordDialog'
import { LoginPage } from './LoginPage'

/** Davanti a tutto il tool: login se serve, cambio password obbligatorio al primo accesso, poi il tool. */
export function AuthShell({ children }: { children: ReactNode }) {
  const { loading, needsLogin, needsPasswordChange } = useAuth()

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#F6F7F9]" aria-busy="true">
        <div className={`${todaySkeleton} h-10 w-48`} />
      </div>
    )
  }
  if (needsLogin) return <LoginPage />
  if (needsPasswordChange) {
    return (
      <div className="min-h-screen bg-[#F6F7F9]">
        <ChangePasswordDialog required />
      </div>
    )
  }
  return <>{children}</>
}
