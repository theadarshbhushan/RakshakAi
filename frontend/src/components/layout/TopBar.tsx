import React from 'react'
import { Link } from 'react-router-dom'
import {
  Bell,
  Volume2,
  VolumeX,
  Menu,
  Inbox,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useSoundStore } from '@/store/soundStore'
import { useClock } from '@/hooks/useClock'
import { ConnectionStatus } from '@/hooks/useWebSocket'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { UserAccountMenu } from '@/components/layout/UserAccountMenu'

interface TopBarProps {
  wsStatus: ConnectionStatus
  onToggleMobileMenu: () => void
}

export const TopBar: React.FC<TopBarProps> = ({ wsStatus, onToggleMobileMenu }) => {
  const clock = useClock()
  const { user } = useAuthStore()
  const { soundEnabled, toggleSound } = useSoundStore()

  // Fetch count of open incidents for notification bell
  const { data: incidentData } = useQuery({
    queryKey: ['incidents', 'open_count'],
    queryFn: () => api.incidents.list({ status: 'open', limit: 100 }),
    refetchInterval: 15000,
  })

  // Fetch count of pending approvals for owner/admin
  const isOwnerOrAdmin = user?.role === 'owner' || user?.role === 'admin'
  const { data: pendingApprovals } = useQuery({
    queryKey: ['approvals', 'pending_count'],
    queryFn: () => api.privacy.listIdentityReveals('pending'),
    enabled: isOwnerOrAdmin,
    refetchInterval: 15000,
  })

  const openCount = incidentData?.total || 0
  const pendingCount = Array.isArray(pendingApprovals) ? pendingApprovals.length : 0

  return (
    <header className="h-[60px] bg-card border-b border-border-divider px-6 flex items-center justify-between sticky top-0 z-30">
      <div className="flex items-center gap-4">
        {/* Mobile menu button */}
        <button
          onClick={onToggleMobileMenu}
          className="lg:hidden p-1.5 rounded-btn text-content-secondary hover:text-content-primary hover:bg-fill-subtle"
          aria-label="Open navigation"
        >
          <Menu size={20} />
        </button>

        {/* Live status dot */}
        <div className="flex items-center gap-2 text-[13px] text-content-secondary">
          <span
            className={`w-2.5 h-2.5 rounded-full ${
              wsStatus === 'connected'
                ? 'bg-status-healthy'
                : wsStatus === 'connecting' || wsStatus === 'reconnecting'
                ? 'bg-status-medium animate-pulse'
                : 'bg-critical'
            }`}
            title={`WebSocket: ${wsStatus}`}
          />
          <span className="hidden sm:inline">
            {wsStatus === 'connected'
              ? 'Live'
              : wsStatus === 'connecting' || wsStatus === 'reconnecting'
              ? 'Reconnecting…'
              : 'Offline'}
          </span>
        </div>

        {/* Live formatted clock */}
        <div className="hidden md:flex items-center text-[13px] font-mono text-content-muted pl-3 border-l border-border-divider">
          {clock}
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* Alert sound toggle */}
        <button
          onClick={toggleSound}
          className="p-2 rounded-btn text-content-muted hover:text-content-primary hover:bg-fill-subtle transition-colors"
          title={soundEnabled ? 'Alert chimes enabled (click to mute)' : 'Alert chimes muted (click to enable)'}
          aria-label="Toggle alert sound"
        >
          {soundEnabled ? <Volume2 size={18} /> : <VolumeX size={18} />}
        </button>

        {/* Approvals inbox badge for owner/admin */}
        {isOwnerOrAdmin && (
          <Link
            to="/app/approvals"
            className="relative p-2 rounded-btn text-content-secondary hover:text-content-primary hover:bg-fill-subtle transition-colors"
            title="Approvals inbox"
          >
            <Inbox size={18} />
            {pendingCount > 0 && (
              <span className="absolute top-1 right-1 px-1.5 py-0.2 bg-critical text-white text-[11px] font-bold rounded-full min-w-[16px] text-center leading-tight">
                {pendingCount}
              </span>
            )}
          </Link>
        )}

        {/* Notifications bell */}
        <Link
          to="/app/incidents"
          className="relative p-2 rounded-btn text-content-secondary hover:text-content-primary hover:bg-fill-subtle transition-colors"
          title="Open incidents"
        >
          <Bell size={18} />
          {openCount > 0 && (
            <span className="absolute top-1 right-1 px-1.5 py-0.2 bg-primary text-white text-[11px] font-bold rounded-full min-w-[16px] text-center leading-tight">
              {openCount}
            </span>
          )}
        </Link>

        {/* User profile menu */}
        <UserAccountMenu />
      </div>
    </header>
  )
}
