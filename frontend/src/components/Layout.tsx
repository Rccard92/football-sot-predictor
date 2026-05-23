import { Outlet } from 'react-router-dom'
import { SidebarLayoutProvider } from '../contexts/SidebarLayoutContext'
import { MobileNavDrawer } from './MobileNavDrawer'
import { MobileTopBar } from './MobileTopBar'
import { Sidebar } from './Sidebar'

export function Layout() {
  return (
    <SidebarLayoutProvider>
      <div className="flex min-h-screen overflow-x-hidden bg-[#F6F7F9] md:h-screen md:overflow-hidden">
        <Sidebar />
        <div className="flex min-h-0 min-w-0 flex-1 flex-col md:overflow-hidden">
          <MobileTopBar />
          <MobileNavDrawer />
          <main className="min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto">
            <div className="content-container mx-auto w-full max-w-[1320px] px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </SidebarLayoutProvider>
  )
}
