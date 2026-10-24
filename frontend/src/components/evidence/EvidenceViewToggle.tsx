import React, { useState } from 'react'
import {
  Lock,
  Unlock,
  AlertTriangle,
  FileCheck,
  Download,
  Clock,
  ShieldAlert,
  Info,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { api } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Countdown } from '@/components/ui/Countdown'
import type { EvidenceAccessInfo } from '@/api/types'
import { toast } from 'sonner'

export type ViewTier = 'skeleton' | 'blurred' | 'unblurred'

export interface EvidenceViewToggleProps {
  incidentId: string
  accessInfo?: EvidenceAccessInfo
  currentView: ViewTier
  onViewChange: (view: ViewTier) => void
  onAccessGranted?: () => void
  cameraName?: string
}

export const EvidenceViewToggle: React.FC<EvidenceViewToggleProps> = ({
  incidentId,
  accessInfo,
  currentView,
  onViewChange,
  onAccessGranted,
  cameraName,
}) => {
  const { user } = useAuthStore()
  const role = user?.role || 'guard'

  // Modals state
  const [breakglassModalOpen, setBreakglassModalOpen] = useState(false)
  const [breakglassReason, setBreakglassReason] = useState('')
  const [breakglassLoading, setBreakglassLoading] = useState(false)

  const [revealModalOpen, setRevealModalOpen] = useState(false)
  const [revealReason, setRevealReason] = useState('')
  const [revealLoading, setRevealLoading] = useState(false)

  const [emergencyModalOpen, setEmergencyModalOpen] = useState(false)
  const [emergencyReason, setEmergencyReason] = useState('')
  const [emergencyLoading, setEmergencyLoading] = useState(false)

  const [exportLoading, setExportLoading] = useState(false)

  // Break-glass grant countdown
  const [breakglassRemaining, setBreakglassRemaining] = useState<number | null>(() => {
    if (accessInfo?.blurred_grant_expires_at) {
      const diff = Math.floor(
        (new Date(accessInfo.blurred_grant_expires_at).getTime() - Date.now()) / 1000
      )
      return diff > 0 ? diff : null
    }
    return null
  })

  // Identity-reveal countdown
  const [revealRemaining, setRevealRemaining] = useState<number | null>(() => {
    if (accessInfo?.unblurred_grant_expires_at) {
      const diff = Math.floor(
        (new Date(accessInfo.unblurred_grant_expires_at).getTime() - Date.now()) / 1000
      )
      return diff > 0 ? diff : null
    }
    return null
  })

  // Emergency intruder reveal state
  const [emergencyIntruderActive, setEmergencyIntruderActive] = useState(false)
  const [emergencyIntruderRemaining, setEmergencyIntruderRemaining] = useState<number | null>(null)

  const [breakglassToken, setBreakglassToken] = useState<string | null>(null)

  // Permissions logic
  const isAuditor = role === 'auditor'
  const isGuard = role === 'guard'
  const isOwner = role === 'owner'

  // Can access blurred:
  // If org default is blurred, or active breakglass, or emergency context eligible
  const hasBreakglass = Boolean(breakglassRemaining || accessInfo?.active_grants?.breakglass)
  const hasEmergencyContext = Boolean(accessInfo?.emergency_context_eligible || accessInfo?.emergency_context_available)
  const isDefaultBlurred = accessInfo?.default_view === 'blurred'

  const isBlurredLocked = !isDefaultBlurred && !hasBreakglass && !hasEmergencyContext && (accessInfo?.locked_views?.includes('blurred') ?? true)

  // Unblurred (Raw) access:
  // Only available if identity reveal approved or emergency reveal active
  const hasIdentityReveal = Boolean(revealRemaining || accessInfo?.active_grants?.identity_reveal)
  const hasEmergencyReveal = Boolean(emergencyIntruderActive || emergencyIntruderRemaining || accessInfo?.active_grants?.emergency_reveal)

  const isUnblurredLocked = !hasIdentityReveal && !hasEmergencyReveal && (accessInfo?.locked_views?.includes('raw') ?? true)

  const handleSelectTier = (tier: ViewTier) => {
    if (tier === 'skeleton') {
      onViewChange('skeleton')
      return
    }

    if (tier === 'blurred') {
      if (isAuditor) {
        toast.error('Auditors are restricted to skeleton privacy view.')
        return
      }
      if (isBlurredLocked) {
        setBreakglassModalOpen(true)
      } else {
        onViewChange('blurred')
      }
      return
    }

    if (tier === 'unblurred') {
      if (isAuditor || isGuard) {
        toast.error('Guards and auditors are restricted from full unblurred view.')
        return
      }
      if (isUnblurredLocked) {
        setRevealModalOpen(true)
      } else {
        onViewChange('unblurred')
      }
    }
  }

  // Submit Breakglass
  const handleSubmitBreakglass = async (e: React.FormEvent) => {
    e.preventDefault()
    if (breakglassReason.trim().length < 10) {
      toast.error('Please enter at least 10 characters explaining why footage is needed.')
      return
    }
    setBreakglassLoading(true)
    try {
      const res = await api.privacy.breakglass({
        incident_id: incidentId,
        reason: breakglassReason,
      })
      toast.success('Break-glass access granted (logged). Available for 10 minutes.')
      setBreakglassModalOpen(false)
      setBreakglassReason('')
      setBreakglassRemaining(600) // 10 minutes
      onViewChange('blurred')
      if (onAccessGranted) onAccessGranted()
    } catch (err: any) {
      toast.error(err.message || 'Failed to submit breakglass request')
    } finally {
      setBreakglassLoading(false)
    }
  }

  // Submit Identity Reveal Request
  const handleSubmitReveal = async (e: React.FormEvent) => {
    e.preventDefault()
    if (revealReason.trim().length < 20) {
      toast.error('Please provide a detailed justification (min 20 characters).')
      return
    }
    setRevealLoading(true)
    try {
      const res = await api.privacy.requestIdentityReveal({
        incident_id: incidentId,
        reason: revealReason,
      })
      toast.info('Request submitted. Waiting for approval by another administrator/owner.')
      setRevealModalOpen(false)
      setRevealReason('')
      if (onAccessGranted) onAccessGranted()
    } catch (err: any) {
      toast.error(err.message || 'Failed to request identity reveal')
    } finally {
      setRevealLoading(false)
    }
  }

  // Submit Emergency Intruder Reveal
  const handleSubmitEmergencyReveal = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!emergencyReason.trim()) {
      toast.error('Please provide a short reason for emergency access.')
      return
    }
    setEmergencyLoading(true)
    try {
      await api.privacy.emergencyReveal({
        incident_id: incidentId,
        reason: emergencyReason,
      })
      toast.success('Emergency intruder reveal activated. Access logged for admin review.')
      setEmergencyModalOpen(false)
      setEmergencyReason('')
      setEmergencyIntruderActive(true)
      setEmergencyIntruderRemaining(300) // 5 minutes
      onViewChange('unblurred')
      if (onAccessGranted) onAccessGranted()
    } catch (err: any) {
      toast.error(err.message || 'Failed to activate emergency reveal')
    } finally {
      setEmergencyLoading(false)
    }
  }

  // Export for Police
  const handleExportPolice = async () => {
    setExportLoading(true)
    try {
      const res = await api.evidence.exportPolice(incidentId)
      toast.success('Export generated with cryptographic chain-of-custody log.', {
        description: `Chain hash: ${res.chain_of_custody_hash.slice(0, 16)}…`,
      })
    } catch (err: any) {
      toast.error(err.message || 'Export failed')
    } finally {
      setExportLoading(false)
    }
  }

  return (
    <div className="space-y-3">
      {/* Emergency Context Banner (Yellow) */}
      {(accessInfo?.emergency_context_eligible || accessInfo?.emergency_context_available) && (
        <div className="p-3 bg-status-high-tint border border-status-high/30 rounded-card flex items-center justify-between text-[13px] text-status-high">
          <div className="flex items-center gap-2">
            <AlertTriangle size={16} className="shrink-0" />
            <span className="font-medium">
              Emergency context view: faces hidden, access logged
            </span>
          </div>
          <span className="font-mono text-[12px] bg-card px-2 py-0.5 rounded shadow-soft">
            10-min active
          </span>
        </div>
      )}

      {/* Identity Reveal Pending Status Banner */}
      {accessInfo?.identity_reveal_status === 'pending' && (
        <div className="p-3 bg-fill-subtle border border-border-card rounded-card flex items-center justify-between text-[13px] text-content-body">
          <div className="flex items-center gap-2">
            <Clock size={16} className="text-status-medium shrink-0" />
            <span>Identity reveal requested: Awaiting review by second administrator in Approvals inbox.</span>
          </div>
          <a href="/approvals" className="text-primary hover:underline font-medium text-[12px]">
            Approvals inbox &rarr;
          </a>
        </div>
      )}

      {/* Emergency Intruder Active Banner (Red) */}
      {emergencyIntruderActive && emergencyIntruderRemaining && (
        <div className="p-3 bg-critical-tint border border-critical-border rounded-card flex items-center justify-between text-[13px] text-critical">
          <div className="flex items-center gap-2">
            <ShieldAlert size={16} className="shrink-0" />
            <span className="font-medium">
              Emergency access: Only intruder unblurred · logged and reviewed by admin
            </span>
          </div>
          <div className="flex items-center gap-1.5 font-mono text-[12px]">
            <Clock size={13} />
            <Countdown
              secondsLeft={emergencyIntruderRemaining}
              onExpire={() => {
                setEmergencyIntruderActive(false)
                setEmergencyIntruderRemaining(null)
                onViewChange('skeleton')
                toast.info('Emergency intruder view expired. Reverted to skeleton view.')
              }}
            />
          </div>
        </div>
      )}

      {/* Main View Tier Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Toggle [ Skeleton | Blurred | Unblurred ] */}
        <div className="inline-flex items-center bg-fill-active p-1 rounded-[8px]">
          {/* Skeleton */}
          <button
            type="button"
            onClick={() => handleSelectTier('skeleton')}
            className={`px-3 py-1.5 text-[13px] font-medium rounded-[6px] transition-all ${
              currentView === 'skeleton'
                ? 'bg-card text-content-primary shadow-soft'
                : 'text-content-secondary hover:text-content-primary'
            }`}
          >
            Skeleton
          </button>

          {/* Blurred */}
          <button
            type="button"
            onClick={() => handleSelectTier('blurred')}
            title={
              isBlurredLocked
                ? 'Requires a logged reason to break glass'
                : 'Real footage with faces blurred'
            }
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium rounded-[6px] transition-all ${
              currentView === 'blurred'
                ? 'bg-card text-content-primary shadow-soft'
                : 'text-content-secondary hover:text-content-primary'
            }`}
          >
            {isBlurredLocked && <Lock size={12} className="text-content-muted" />}
            <span>Blurred</span>
            {breakglassRemaining && (
              <span className="font-mono text-[11px] text-status-high ml-1">
                <Countdown
                  secondsLeft={breakglassRemaining}
                  onExpire={() => {
                    setBreakglassRemaining(null)
                    onViewChange('skeleton')
                  }}
                />
              </span>
            )}
          </button>

          {/* Unblurred */}
          {!isAuditor && (
            <button
              type="button"
              onClick={() => handleSelectTier('unblurred')}
              title={
                isUnblurredLocked
                  ? 'Requires approval by a second admin'
                  : 'Full resolution with identity revealed'
              }
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium rounded-[6px] transition-all ${
                currentView === 'unblurred'
                  ? 'bg-card text-content-primary shadow-soft'
                  : 'text-content-secondary hover:text-content-primary'
              }`}
            >
              {isUnblurredLocked && <Lock size={12} className="text-content-muted" />}
              <span>Unblurred</span>
              {revealRemaining && (
                <span className="font-mono text-[11px] text-critical ml-1">
                  <Countdown
                    secondsLeft={revealRemaining}
                    onExpire={() => {
                      setRevealRemaining(null)
                      onViewChange('skeleton')
                    }}
                  />
                </span>
              )}
            </button>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          {/* Emergency intruder button (only for intruder/breach incidents when eligible) */}
          {accessInfo?.emergency_reveal_eligible && !emergencyIntruderActive && !isAuditor && (
            <Button
              variant="danger"
              size="sm"
              icon={<ShieldAlert size={14} />}
              onClick={() => setEmergencyModalOpen(true)}
            >
              EMERGENCY: Show intruder's face
            </Button>
          )}

          {/* Police export (owner only when unblurred or verified) */}
          {isOwner && (
            <Button
              variant="secondary"
              size="sm"
              isLoading={exportLoading}
              icon={<Download size={14} />}
              onClick={handleExportPolice}
              title="Download watermarked evidence clip and cryptographic chain of custody"
            >
              Export for police
            </Button>
          )}
        </div>
      </div>

      {/* 1. Modal: Break-glass for Blurred View */}
      <Modal
        isOpen={breakglassModalOpen}
        onClose={() => setBreakglassModalOpen(false)}
        title="Why do you need to view footage?"
        description="Detection runs automatically on full video. Raw visual access requires an accountable reason."
      >
        <form onSubmit={handleSubmitBreakglass} className="space-y-4">
          <div className="p-3 bg-fill-subtle rounded-card border border-border-card text-[13px] text-content-body flex items-start gap-2.5">
            <Info size={16} className="text-primary shrink-0 mt-0.5" />
            <p>
              This break-glass access is <strong>cryptographically logged</strong> on the tamper-proof audit chain.
              Faces will remain blurred to protect bystanders. Access will stay active for 10 minutes.
            </p>
          </div>

          <div>
            <label className="block text-[13px] font-medium text-content-body mb-1">
              Reason for viewing (min 10 characters)
            </label>
            <textarea
              required
              rows={3}
              value={breakglassReason}
              onChange={(e) => setBreakglassReason(e.target.value)}
              placeholder="e.g. Verifying physical altercation reported on Terrace North"
              className="w-full px-3 py-2 text-[14px] bg-card border border-border-input rounded-input focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
            <p className="text-[11px] text-content-muted mt-1">
              {breakglassReason.length}/10 characters minimum
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setBreakglassModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              isLoading={breakglassLoading}
              disabled={breakglassReason.trim().length < 10}
            >
              Confirm and log access
            </Button>
          </div>
        </form>
      </Modal>

      {/* 2. Modal: Request Identity Reveal (Two-Person Approval) */}
      <Modal
        isOpen={revealModalOpen}
        onClose={() => setRevealModalOpen(false)}
        title="Request identity reveal"
        description="Requires dual approval by a second hostel administrator or owner."
      >
        <form onSubmit={handleSubmitReveal} className="space-y-4">
          <div className="p-3 bg-critical-tint rounded-card border border-critical-border text-[13px] text-critical flex items-start gap-2.5">
            <AlertTriangle size={16} className="shrink-0 mt-0.5" />
            <p>
              Unblurred video reveals students' faces. In accordance with student privacy policy,
              identity reveal is restricted to safety incidents and requires approval from an independent administrator.
            </p>
          </div>

          <div>
            <label className="block text-[13px] font-medium text-content-body mb-1">
              Detailed formal justification (min 20 characters)
            </label>
            <textarea
              required
              rows={4}
              value={revealReason}
              onChange={(e) => setRevealReason(e.target.value)}
              placeholder="e.g. Unswiped perimeter entry detected with door forced open. Required for police reporting and student safety."
              className="w-full px-3 py-2 text-[14px] bg-card border border-border-input rounded-input focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
            <p className="text-[11px] text-content-muted mt-1">
              {revealReason.length}/20 characters minimum
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setRevealModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              isLoading={revealLoading}
              disabled={revealReason.trim().length < 20}
            >
              Submit for dual approval
            </Button>
          </div>
        </form>
      </Modal>

      {/* 3. Modal: Emergency Intruder Reveal */}
      <Modal
        isOpen={emergencyModalOpen}
        onClose={() => setEmergencyModalOpen(false)}
        title="Emergency intruder reveal"
        description="Immediate face unblurring for unexplained intruders or perimeter breaches."
      >
        <form onSubmit={handleSubmitEmergencyReveal} className="space-y-4">
          <div className="p-3 bg-critical-tint rounded-card border border-critical-border text-[13px] text-critical flex items-start gap-2.5">
            <ShieldAlert size={18} className="shrink-0 mt-0.5" />
            <p>
              Only the intruder's bounding box will be unblurred. Bystanders will remain protected.
              This access is immediately flagged for mandatory 24-hour review by hostel administration.
            </p>
          </div>

          <div>
            <label className="block text-[13px] font-medium text-content-body mb-1">
              Reason for immediate emergency unblur
            </label>
            <input
              type="text"
              required
              value={emergencyReason}
              onChange={(e) => setEmergencyReason(e.target.value)}
              placeholder="e.g. Intruder climbing perimeter wall near Block B"
              className="w-full px-3 py-2 text-[14px] bg-card border border-border-input rounded-input focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setEmergencyModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="danger"
              isLoading={emergencyLoading}
              disabled={!emergencyReason.trim()}
            >
              Reveal intruder face (5-min)
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
