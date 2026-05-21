import { Outlet } from 'react-router-dom'
import { SidebarLayoutProvider } from '../contexts/SidebarLayoutContext'
import { MobileNavDrawer } from './MobileNavDrawer'
import { MobileTopBar } from './MobileTopBar'
import { Sidebar } from './Sidebar'

export function Layout() {
  return (
    <SidebarLayoutProvider>
      <div className="flex min-h-screen bg-[#F6F7F9]">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <MobileTopBar />
          <MobileNavDrawer />
          <main className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto">
            <div className="content-container mx-auto w-full max-w-[1320px] px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </SidebarLayoutProvider>
  )
}
