import React from 'react'
import { NavLink, Link } from 'react-router-dom'
import {
  Activity,
  Video,
  AlertTriangle,
  MapPin,
  Camera,
  Sliders,
  Gauge,
  BarChart2,
  Lock,
  Settings,
  ShieldCheck,
  Inbox,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'

interface SidebarProps {
  onCloseMobile?: () => void
}

export const Sidebar: React.FC<SidebarProps> = ({ onCloseMobile }) => {
  const { user, org } = useAuthStore()
  const isOwnerOrAdmin = user?.role === 'owner' || user?.role === 'admin'

  const navItems = [
    { label: 'Live Monitor', to: '/app', icon: <Activity size={18} /> },
    { label: 'Analyze Footage', to: '/app/analyze', icon: <Video size={18} /> },
    { label: 'Incidents', to: '/app/incidents', icon: <AlertTriangle size={18} /> },
    ...(isOwnerOrAdmin
      ? [{ label: 'Approvals Inbox', to: '/app/approvals', icon: <Inbox size={18} /> }]
      : []),
    { label: 'Map & Patrol', to: '/app/map', icon: <MapPin size={18} /> },
    { label: 'Cameras', to: '/app/cameras', icon: <Camera size={18} /> },
    { label: 'Rules & Zones', to: '/app/rules', icon: <Sliders size={18} /> },
    { label: 'Calibration', to: '/app/calibration', icon: <Gauge size={18} /> },
    { label: 'Evaluation', to: '/app/evaluation', icon: <BarChart2 size={18} /> },
    { label: 'Privacy & Audit', to: '/app/privacy', icon: <Lock size={18} /> },
    { label: 'Settings', to: '/app/settings', icon: <Settings size={18} /> },
  ]

  return (
    <aside className="w-[240px] shrink-0 bg-sidebar border-r border-border-card flex flex-col h-screen sticky top-0 overflow-y-auto">
      <div className="flex flex-col">
        {/* Brand & Org */}
        <div className="p-5 border-b border-border-divider">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="w-8 h-8 rounded-[8px] bg-primary flex items-center justify-center text-white shadow-soft shrink-0">
              <ShieldCheck size={20} strokeWidth={2.4} />
            </div>
            <div>
              <span className="text-[17px] font-bold tracking-tight text-content-primary block leading-none group-hover:text-primary transition-colors">
                RakshakAI
              </span>
              <span className="text-[11px] font-medium text-primary tracking-wide block mt-1">
                Privacy-First Safety
              </span>
            </div>
          </Link>

          <div className="mt-3.5 pt-2 border-t border-border-divider/60">
            <p className="text-[12px] font-medium text-content-secondary truncate">
              {org?.name || 'Sunrise Residency'}
            </p>
            <p className="text-[11px] text-content-muted truncate">
              Block B Hostel
            </p>
          </div>
        </div>

        {/* Navigation links */}
        <nav className="p-3 space-y-1 pb-6">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/app'}
              onClick={onCloseMobile}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 text-[14px] font-medium rounded-btn transition-colors ${
                  isActive
                    ? 'bg-fill-active text-content-primary'
                    : 'text-content-secondary hover:text-content-primary hover:bg-fill-subtle'
                }`
              }
            >
              <span className="text-content-muted">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </aside>
  )
}
