import { Outlet, useLocation } from 'react-router-dom'
import { CompetitionProvider } from '../contexts/CompetitionContext'
import { ModelSelectionProvider } from '../contexts/ModelSelectionContext'
import { SidebarLayoutProvider } from '../contexts/SidebarLayoutContext'
import { MobileNavDrawer } from './MobileNavDrawer'
import { MobileTopBar } from './MobileTopBar'
import { Sidebar } from './Sidebar'

const CECCHINO_TODAY_PATH = '/cecchino-today'

export function Layout() {
  const location = useLocation()
  const isCecchinoTodayWorkspace =
    location.pathname === CECCHINO_TODAY_PATH ||
    location.pathname.startsWith(`${CECCHINO_TODAY_PATH}/`)

  const contentClass = isCecchinoTodayWorkspace
    ? 'w-full max-w-none px-3 py-4 sm:px-4 lg:px-5'
    : 'content-container mx-auto w-full max-w-[1320px] px-4 py-6 sm:px-6 sm:py-8 lg:px-8'

  return (
    <CompetitionProvider>
      <ModelSelectionProvider>
        <SidebarLayoutProvider>
          <div className="flex min-h-screen overflow-x-hidden bg-[#F6F7F9] md:h-screen md:overflow-hidden">
            <Sidebar />
            <div className="flex min-h-0 min-w-0 flex-1 flex-col md:overflow-hidden">
              <MobileTopBar />
              <MobileNavDrawer />
              <main className="min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto">
                <div className={contentClass}>
                  <Outlet />
                </div>
              </main>
            </div>
          </div>
        </SidebarLayoutProvider>
      </ModelSelectionProvider>
    </CompetitionProvider>
  )
}
