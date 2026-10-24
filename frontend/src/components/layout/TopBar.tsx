import React, { useState, useRef, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Bell,
  Volume2,
  VolumeX,
  Menu,
  ChevronDown,
  LogOut,
  UserCheck,
  Shield,
  Inbox,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useSoundStore } from '@/store/soundStore'
import { useClock } from '@/hooks/useClock'
import { ConnectionStatus } from '@/hooks/useWebSocket'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

interface TopBarProps {
  wsStatus: ConnectionStatus
  onToggleMobileMenu: () => void
}

export const TopBar: React.FC<TopBarProps> = ({ wsStatus, onToggleMobileMenu }) => {
  const clock = useClock()
  const navigate = useNavigate()
  const { user, logout, login } = useAuthStore()
  const { soundEnabled, toggleSound } = useSoundStore()
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

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

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleOutsideClick)
    return () => document.removeEventListener('mousedown', handleOutsideClick)
  }, [])

  const handleQuickSwitch = async (email: string, pass: string) => {
    setUserMenuOpen(false)
    try {
      await login(email, pass)
      navigate('/')
    } catch {
      // ignore
    }
  }

  const roleLabels: Record<string, string> = {
    owner: 'Owner',
    admin: 'Administrator',
    warden: 'Warden',
    guard: 'Security guard',
    auditor: 'Auditor',
  }

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
                : wsStatus === 'connecting'
                ? 'bg-status-medium animate-pulse'
                : 'bg-critical'
            }`}
            title={`WebSocket: ${wsStatus}`}
          />
          <span className="hidden sm:inline">
            {wsStatus === 'connected'
              ? 'Live'
              : wsStatus === 'connecting'
              ? 'Connecting…'
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
            to="/approvals"
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
          to="/incidents"
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

        {/* Role badge */}
        <div className="hidden sm:flex items-center px-2.5 py-1 rounded-[6px] bg-fill-subtle border border-border-card text-[12px] font-medium text-content-body">
          {roleLabels[user?.role || ''] || user?.role || 'Guest'}
        </div>

        {/* User profile menu */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setUserMenuOpen((prev) => !prev)}
            className="flex items-center gap-2 pl-2 pr-1.5 py-1.5 rounded-btn hover:bg-fill-subtle transition-colors"
          >
            <div className="w-7 h-7 rounded-full bg-primary/10 text-primary font-medium text-[13px] flex items-center justify-center">
              {user?.full_name ? user.full_name.charAt(0).toUpperCase() : 'U'}
            </div>
            <span className="hidden md:inline text-[13px] font-medium text-content-primary">
              {user?.full_name || user?.email}
            </span>
            <ChevronDown size={14} className="text-content-muted" />
          </button>

          {userMenuOpen && (
            <div className="absolute right-0 mt-1.5 w-64 bg-card rounded-card border border-border-card shadow-lg py-1.5 z-50 text-[13px]">
              <div className="px-3.5 py-2 border-b border-border-divider">
                <p className="font-semibold text-content-primary">{user?.full_name}</p>
                <p className="text-[12px] text-content-muted truncate">{user?.email}</p>
                <div className="mt-1 inline-block text-[11px] px-2 py-0.5 rounded bg-fill-subtle text-content-secondary font-medium">
                  {roleLabels[user?.role || ''] || user?.role}
                </div>
              </div>

              {/* Demo Fast Switch */}
              <div className="px-3.5 py-2 border-b border-border-divider">
                <p className="text-[11px] font-semibold text-content-muted uppercase tracking-wider mb-1.5">
                  Switch demo account
                </p>
                <div className="grid grid-cols-2 gap-1 text-[12px]">
                  <button
                    onClick={() => handleQuickSwitch('owner@sunrise.demo', 'Owner@12345')}
                    className="text-left px-2 py-1 rounded hover:bg-fill-subtle text-content-body font-medium"
                  >
                    Owner
                  </button>
                  <button
                    onClick={() => handleQuickSwitch('admin@sunrise.demo', 'Admin@12345')}
                    className="text-left px-2 py-1 rounded hover:bg-fill-subtle text-content-body font-medium"
                  >
                    Admin
                  </button>
                  <button
                    onClick={() => handleQuickSwitch('warden@sunrise.demo', 'Warden@12345')}
                    className="text-left px-2 py-1 rounded hover:bg-fill-subtle text-content-body font-medium"
                  >
                    Warden
                  </button>
                  <button
                    onClick={() => handleQuickSwitch('guard@sunrise.demo', 'Guard@12345')}
                    className="text-left px-2 py-1 rounded hover:bg-fill-subtle text-content-body font-medium"
                  >
                    Guard
                  </button>
                  <button
                    onClick={() => handleQuickSwitch('auditor@sunrise.demo', 'Auditor@12345')}
                    className="text-left px-2 py-1 rounded hover:bg-fill-subtle text-content-body font-medium"
                  >
                    Auditor
                  </button>
                  <button
                    onClick={() => handleQuickSwitch('owner@greenvalley.demo', 'Owner@12345')}
                    className="text-left px-2 py-1 rounded hover:bg-fill-subtle text-content-body font-medium"
                  >
                    Green Valley
                  </button>
                </div>
              </div>

              <div className="p-1">
                <button
                  onClick={() => {
                    setUserMenuOpen(false)
                    logout()
                    navigate('/login')
                  }}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-content-secondary hover:text-critical hover:bg-critical-tint/50 rounded-btn transition-colors text-left"
                >
                  <LogOut size={16} />
                  <span>Sign out</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
