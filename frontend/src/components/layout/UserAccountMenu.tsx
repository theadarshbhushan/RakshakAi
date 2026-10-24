import React, { useState, useRef, useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { ChevronDown, LogOut, ArrowRight, LayoutDashboard, Check } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { toast } from 'sonner'

export const ROLE_LABELS: Record<string, string> = {
  owner: 'Owner',
  admin: 'Administrator',
  warden: 'Warden',
  guard: 'Security guard',
  auditor: 'Auditor',
}

const DEMO_ACCOUNTS = [
  { label: 'Owner', email: 'owner@sunrise.demo', pass: 'Owner@12345' },
  { label: 'Admin', email: 'admin@sunrise.demo', pass: 'Admin@12345' },
  { label: 'Warden', email: 'warden@sunrise.demo', pass: 'Warden@12345' },
  { label: 'Guard', email: 'guard@sunrise.demo', pass: 'Guard@12345' },
  { label: 'Auditor', email: 'auditor@sunrise.demo', pass: 'Auditor@12345' },
  { label: 'Green Valley', email: 'owner@greenvalley.demo', pass: 'Owner@12345' },
]

export interface UserAccountMenuProps {
  /**
   * If true, switching accounts will keep the user on the current page instead of redirecting to /app.
   * Default is false on dashboard, true on landing page.
   */
  stayOnPageAfterSwitch?: boolean
  /**
   * If true, signing out keeps the user on the current page instead of redirecting to /login.
   * Default is false on dashboard, true on landing page.
   */
  stayOnPageAfterSignOut?: boolean
  /**
   * Optional control to force show or hide "Go to dashboard".
   * By default, it is shown on "/" (landing page) and hidden on any "/app" dashboard route.
   */
  showGoToDashboard?: boolean
  /**
   * Optional custom class for the outer trigger container.
   */
  className?: string
}

export const UserAccountMenu: React.FC<UserAccountMenuProps> = ({
  stayOnPageAfterSwitch = false,
  stayOnPageAfterSignOut = false,
  showGoToDashboard,
  className = '',
}) => {
  const { user, login, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [isOpen, setIsOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  const isInsideApp = location.pathname.startsWith('/app')
  const shouldShowDashboard =
    showGoToDashboard !== undefined ? showGoToDashboard : !isInsideApp

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleOutsideClick)
    return () => document.removeEventListener('mousedown', handleOutsideClick)
  }, [])

  const handleQuickSwitch = async (email: string, pass: string) => {
    setIsOpen(false)
    try {
      await login(email, pass)
      toast.success('Switched demo account', {
        description: `Logged in as ${email}`,
      })
      if (!stayOnPageAfterSwitch) {
        navigate('/app')
      }
    } catch (err: any) {
      toast.error('Failed to switch demo account', {
        description: err.message,
      })
    }
  }

  const handleSignOut = async () => {
    setIsOpen(false)
    try {
      await logout()
      toast.info('Signed out successfully')
      if (!stayOnPageAfterSignOut) {
        navigate('/login')
      }
    } catch {
      if (!stayOnPageAfterSignOut) {
        navigate('/login')
      }
    }
  }

  const initial = user?.full_name ? user.full_name.charAt(0).toUpperCase() : 'U'
  const displayRole = ROLE_LABELS[user?.role || ''] || user?.role || 'User'

  return (
    <div className={`relative ${className}`} ref={menuRef}>
      {/* Trigger Button: Avatar + Name + Role */}
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className="flex items-center gap-2 pl-1.5 pr-2 py-1 rounded-btn hover:bg-fill-subtle border border-border-card/70 transition-colors"
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        <div className="w-7 h-7 rounded-full bg-primary/10 text-primary font-bold text-[13px] flex items-center justify-center shrink-0">
          {initial}
        </div>
        <span className="text-[13px] font-medium text-content-primary max-w-[120px] truncate">
          {user?.full_name || user?.email}
        </span>
        <span className="hidden sm:inline-block text-[11px] font-medium px-2 py-0.5 rounded-[5px] bg-fill-subtle border border-border-card text-content-secondary shrink-0">
          {displayRole}
        </span>
        <ChevronDown size={14} className="text-content-muted shrink-0" />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute right-0 mt-1.5 w-64 bg-card rounded-card border border-border-card shadow-lg py-1.5 z-50 text-[13px] animate-in fade-in slide-in-from-top-1">
          {/* User Details */}
          <div className="px-3.5 py-2.5 border-b border-border-divider">
            <p className="font-semibold text-content-primary truncate">{user?.full_name || 'User'}</p>
            <p className="text-[12px] text-content-muted truncate mt-0.5">{user?.email}</p>
            <div className="mt-1.5 inline-block text-[11px] px-2 py-0.5 rounded bg-fill-subtle text-content-secondary font-medium">
              {displayRole}
            </div>
          </div>

          {/* Go to Dashboard Link (Shown only on landing page / outside dashboard) */}
          {shouldShowDashboard && (
            <div className="p-1 border-b border-border-divider">
              <Link
                to="/app"
                onClick={() => setIsOpen(false)}
                className="w-full flex items-center justify-between px-2.5 py-2 text-content-primary hover:bg-fill-subtle rounded-btn font-medium text-[13px] transition-colors group"
              >
                <span className="flex items-center gap-2">
                  <LayoutDashboard size={15} className="text-primary" />
                  <span>Go to dashboard</span>
                </span>
                <ArrowRight size={13} className="text-content-muted group-hover:translate-x-0.5 transition-transform" />
              </Link>
            </div>
          )}

          {/* Switch Demo Account Grid */}
          <div className="px-3.5 py-2 border-b border-border-divider">
            <p className="text-[11px] font-semibold text-content-muted uppercase tracking-wider mb-1.5">
              Switch demo account
            </p>
            <div className="grid grid-cols-2 gap-1 text-[12px]">
              {DEMO_ACCOUNTS.map((acc) => {
                const isActive = user?.email === acc.email
                return (
                  <button
                    key={acc.email}
                    onClick={() => handleQuickSwitch(acc.email, acc.pass)}
                    className={`flex items-center justify-between px-2 py-1 rounded text-left font-medium transition-colors ${
                      isActive
                        ? 'bg-primary-tint text-primary font-semibold'
                        : 'text-content-body hover:bg-fill-subtle'
                    }`}
                  >
                    <span className="truncate">{acc.label}</span>
                    {isActive && <Check size={12} className="shrink-0 text-primary" />}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Sign Out Action */}
          <div className="p-1">
            <button
              onClick={handleSignOut}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-content-secondary hover:text-critical hover:bg-critical-tint/50 rounded-btn transition-colors text-left"
            >
              <LogOut size={15} />
              <span>Sign out</span>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
