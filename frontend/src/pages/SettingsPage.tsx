import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Settings as SettingsIcon,
  User,
  Volume2,
  VolumeX,
  QrCode,
  Building,
  ShieldCheck,
  Printer,
  Key,
} from 'lucide-react'
import { api } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { useSoundStore } from '@/store/soundStore'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { toast } from 'sonner'

export const SettingsPage: React.FC = () => {
  const navigate = useNavigate()
  const { user, org } = useAuthStore()
  const { soundEnabled, toggleSound } = useSoundStore()
  const isOwnerOrAdmin = user?.role === 'owner' || user?.role === 'admin'

  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [changingPass, setChangingPass] = useState(false)

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newPassword || newPassword.length < 8) {
      toast.error('New password must be at least 8 characters')
      return
    }
    setChangingPass(true)
    try {
      await api.auth.changePassword({
        old_password: oldPassword,
        new_password: newPassword,
      })
      toast.success('Password updated successfully')
      setOldPassword('')
      setNewPassword('')
    } catch (err: any) {
      toast.error(err.message || 'Failed to update password')
    } finally {
      setChangingPass(false)
    }
  }

  const handlePrintQrSheet = () => {
    navigate('/app/settings/sos-qr')
  }

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-[26px] font-bold text-content-primary">Settings</h1>
        <p className="text-[14px] text-content-secondary mt-0.5">
          User profile preferences, notification chimes, hostel organization details, and printable physical QR posters.
        </p>
      </div>

      {/* 1. Profile & Account */}
      <Card padding="md" className="space-y-4">
        <h2 className="text-[17px] font-semibold text-content-primary flex items-center gap-2">
          <User size={18} className="text-primary" />
          Your profile & role
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-[13px]">
          <div>
            <label className="block text-[11px] font-semibold text-content-muted uppercase mb-1">
              Full name
            </label>
            <p className="p-2.5 rounded bg-fill-subtle border border-border-card text-content-primary font-medium">
              {user?.full_name || 'Staff Member'}
            </p>
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-content-muted uppercase mb-1">
              Email address
            </label>
            <p className="p-2.5 rounded bg-fill-subtle border border-border-card text-content-primary font-mono">
              {user?.email || 'user@sunrise.demo'}
            </p>
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-content-muted uppercase mb-1">
              Assigned role
            </label>
            <p className="p-2.5 rounded bg-fill-subtle border border-border-card text-content-primary capitalize font-medium">
              {user?.role}
            </p>
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-content-muted uppercase mb-1">
              Security organization
            </label>
            <p className="p-2.5 rounded bg-fill-subtle border border-border-card text-content-primary">
              {org?.name || 'Sunrise Residency'}
            </p>
          </div>
        </div>
      </Card>

      {/* 2. Notification Chime Preferences */}
      <Card padding="md" className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-[17px] font-semibold text-content-primary flex items-center gap-2">
              {soundEnabled ? (
                <Volume2 size={18} className="text-primary" />
              ) : (
                <VolumeX size={18} className="text-content-muted" />
              )}
              Audio Alert Chimes
            </h2>
            <p className="text-[13px] text-content-secondary mt-0.5">
              Synthesized soft Web Audio alert chime when critical or high incidents are corroborated.
            </p>
          </div>

          <Button
            variant={soundEnabled ? 'primary' : 'secondary'}
            size="sm"
            onClick={toggleSound}
          >
            {soundEnabled ? 'Enabled' : 'Muted'}
          </Button>
        </div>
      </Card>

      {/* 3. Printable Student SOS QR Codes Sheet (Owner/Admin) */}
      <Card padding="md" className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-[17px] font-semibold text-content-primary flex items-center gap-2">
              <QrCode size={18} className="text-primary" />
              Printable Student SOS QR Code Sheets
            </h2>
            <p className="text-[13px] text-content-secondary mt-0.5">
              Generates ready-to-print posters for each zone with encrypted tokenized links for students to scan.
            </p>
          </div>

          {isOwnerOrAdmin && (
            <Button
              variant="primary"
              size="md"
              icon={<Printer size={15} />}
              onClick={handlePrintQrSheet}
            >
              Print SOS QR codes
            </Button>
          )}
        </div>
      </Card>

      {/* 4. Change Password */}
      <Card padding="md" className="space-y-4">
        <h2 className="text-[17px] font-semibold text-content-primary flex items-center gap-2">
          <Key size={18} className="text-primary" />
          Update password
        </h2>

        <form onSubmit={handlePasswordChange} className="space-y-3 max-w-md">
          <Input
            label="Current password"
            type="password"
            required
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
          />
          <Input
            label="New password (min 8 characters)"
            type="password"
            required
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
          <Button
            type="submit"
            variant="secondary"
            size="sm"
            isLoading={changingPass}
          >
            Change password
          </Button>
        </form>
      </Card>
    </div>
  )
}
