import React, { useState } from 'react'
import {
  Camera as CameraIcon,
  AlertTriangle,
  Eye,
  ShieldAlert,
  Radio,
  Maximize2,
} from 'lucide-react'
import { api } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Countdown } from '@/components/ui/Countdown'
import type { Camera } from '@/api/types'
import { toast } from 'sonner'

export interface CameraTileProps {
  camera: Camera
  incidentId?: string
  defaultMode?: 'skeleton' | 'blurred'
  onSelect?: () => void
  onEmergencyRevealTrigger?: (cameraId: string) => void
  hasActiveIntrusion?: boolean
}

export const CameraTile: React.FC<CameraTileProps> = ({
  camera,
  incidentId,
  defaultMode = 'skeleton',
  onSelect,
  onEmergencyRevealTrigger,
  hasActiveIntrusion = false,
}) => {
  const [mode, setMode] = useState<'skeleton' | 'blurred'>(defaultMode)
  const [streamError, setStreamError] = useState(false)
  const [emergencyModalOpen, setEmergencyModalOpen] = useState(false)
  const [emergencyReason, setEmergencyReason] = useState('')
  const [emergencySubmitting, setEmergencySubmitting] = useState(false)
  const [intruderUnlocked, setIntruderUnlocked] = useState(false)

  const isTampered = camera.status === 'tampered' || (camera as any).is_blind_spot
  const isOffline = camera.status === 'offline'

  const streamUrl = api.cameras.getStreamUrl(
    camera.camera_id,
    intruderUnlocked ? 'emergency' : mode
  )

  const handleEmergencySubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!emergencyReason.trim()) return
    setEmergencySubmitting(true)
    try {
      if (incidentId) {
        await api.privacy.emergencyReveal({
          incident_id: incidentId,
          reason: emergencyReason,
        })
      }
      setIntruderUnlocked(true)
      setEmergencyModalOpen(false)
      toast.success(`Emergency intruder access active for ${camera.name}. Access logged for admin review.`)
    } catch (err: any) {
      toast.error(err.message || 'Emergency access failed')
    } finally {
      setEmergencySubmitting(false)
    }
  }

  const healthBadge = {
    ok: { label: 'OK', color: 'bg-status-healthy text-white' },
    degraded: { label: 'Degraded', color: 'bg-status-medium text-white' },
    tampered: { label: 'Tampered', color: 'bg-critical text-white' },
    offline: { label: 'Offline', color: 'bg-content-muted text-white' },
  }[camera.status.toLowerCase()] || { label: camera.status, color: 'bg-content-muted text-white' }

  return (
    <div className="bg-video-bg rounded-card overflow-hidden border border-border-card shadow-soft flex flex-col relative group">
      {/* Tile Header */}
      <div className="px-3.5 py-2.5 bg-[#1C1E23] text-white flex items-center justify-between z-10">
        <div className="flex items-center gap-2">
          <CameraIcon size={14} className="text-[#EDEBE6]" />
          <span className="text-[13px] font-medium text-[#EDEBE6] truncate max-w-[150px]">
            {camera.name}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {/* Health Badge */}
          <span
            className={`text-[10px] font-semibold px-1.5 py-0.5 rounded tracking-wide uppercase ${healthBadge.color}`}
          >
            {healthBadge.label}
          </span>
        </div>
      </div>

      {/* Video Stream Container */}
      <div className="relative aspect-video bg-video-bg flex items-center justify-center overflow-hidden">
        {/* Blind Spot Overlay */}
        {isTampered && (
          <div className="absolute inset-0 bg-critical/75 z-20 flex flex-col items-center justify-center text-white p-4 text-center">
            <AlertTriangle size={32} className="mb-2 animate-bounce" />
            <span className="text-[14px] font-bold tracking-wider uppercase">
              BLIND SPOT
            </span>
            <p className="text-[12px] opacity-90 mt-1 max-w-[200px]">
              Camera obscured or degraded. Audio sensitivity auto-raised.
            </p>
          </div>
        )}

        {/* Offline Overlay */}
        {isOffline && !isTampered && (
          <div className="absolute inset-0 bg-[#1C1E23]/90 z-20 flex flex-col items-center justify-center text-[#B9B7B1] p-4 text-center">
            <Radio size={28} className="mb-2 opacity-50" />
            <span className="text-[13px] font-medium">Camera offline</span>
            <span className="text-[11px] text-content-muted mt-0.5">
              Check PoE connection
            </span>
          </div>
        )}

        {/* Live Stream Image */}
        {!streamError && !isOffline ? (
          <img
            src={streamUrl}
            alt={camera.name}
            onError={() => setStreamError(true)}
            className="w-full h-full object-cover"
          />
        ) : (
          /* Simulated Skeleton Placeholder if stream not actively producing frames */
          <div className="w-full h-full flex flex-col items-center justify-center p-4 relative select-none">
            {/* SVG Skeleton representation */}
            <svg
              className="w-24 h-28 opacity-80"
              viewBox="0 0 100 120"
              fill="none"
              stroke="#EDEBE6"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              {/* Head */}
              <circle cx="50" cy="20" r="10" stroke="#EDEBE6" strokeWidth="2.5" />
              {/* Spine */}
              <line x1="50" y1="30" x2="50" y2="65" />
              {/* Arms */}
              <line x1="50" y1="42" x2="30" y2="55" />
              <line x1="30" y1="55" x2="22" y2="70" />
              <line x1="50" y1="42" x2="70" y2="55" />
              <line x1="70" y1="55" x2="78" y2="70" />
              {/* Legs */}
              <line x1="50" y1="65" x2="35" y2="90" />
              <line x1="35" y1="90" x2="30" y2="115" />
              <line x1="50" y1="65" x2="65" y2="90" />
              <line x1="65" y1="90" x2="70" y2="115" />
            </svg>

            {/* Simulated Bounding Box */}
            <div className="absolute inset-8 border border-video-alertBox/80 rounded pointer-events-none flex items-start justify-between p-1">
              <span className="bg-video-alertBox text-white text-[9px] font-mono px-1 rounded">
                ID: P-04
              </span>
              <span className="text-[10px] text-[#EDEBE6] font-mono">
                Terrace · 23:42
              </span>
            </div>

            <span className="text-[11px] font-mono text-[#B9B7B1] mt-1">
              Live stream standby
            </span>
          </div>
        )}

        {/* Intruder Unlocked Red Banner */}
        {intruderUnlocked && (
          <div className="absolute top-2 left-2 right-2 bg-critical text-white text-[11px] font-medium py-1 px-2.5 rounded shadow flex items-center justify-between z-30">
            <span className="flex items-center gap-1.5">
              <ShieldAlert size={12} />
              EMERGENCY INTRUDER VIEW
            </span>
            <Countdown
              secondsLeft={300}
              onExpire={() => setIntruderUnlocked(false)}
            />
          </div>
        )}

        {/* Privacy Mode Badge */}
        <div className="absolute bottom-2 left-2 z-10">
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium tracking-wide bg-black/60 text-[#EDEBE6] backdrop-blur-[2px]">
            {intruderUnlocked
              ? 'EMERGENCY: INTRUDER UNBLURRED'
              : mode === 'skeleton'
              ? 'PRIVACY MODE: SKELETON VIEW'
              : 'PRIVACY MODE: FACES BLURRED'}
          </span>
        </div>

        {/* Emergency Reveal Button on Camera Tile when active intrusion */}
        {hasActiveIntrusion && !intruderUnlocked && (
          <div className="absolute bottom-2 right-2 z-10">
            <button
              onClick={() => setEmergencyModalOpen(true)}
              className="bg-critical-danger hover:bg-critical-danger/90 text-white text-[11px] font-semibold px-2 py-1 rounded shadow flex items-center gap-1"
            >
              <ShieldAlert size={12} />
              <span>Show intruder</span>
            </button>
          </div>
        )}
      </div>

      {/* Emergency Intruder Modal */}
      <Modal
        isOpen={emergencyModalOpen}
        onClose={() => setEmergencyModalOpen(false)}
        title={`Emergency reveal: ${camera.name}`}
        description="Temporarily unblur faces on this live stream during an active safety emergency."
      >
        <form onSubmit={handleEmergencySubmit} className="space-y-4">
          <div className="p-3 bg-critical-tint rounded-card border border-critical-border text-[13px] text-critical">
            This action gives immediate unblurred access for 5 minutes and is logged for mandatory admin audit.
          </div>
          <div>
            <label className="block text-[13px] font-medium text-content-body mb-1">
              Reason for emergency unblur
            </label>
            <input
              type="text"
              required
              value={emergencyReason}
              onChange={(e) => setEmergencyReason(e.target.value)}
              placeholder="e.g. Unknown person scaling fence into courtyard"
              className="w-full px-3 py-2 text-[14px] bg-card border border-border-input rounded-input"
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
              isLoading={emergencySubmitting}
            >
              Activate live reveal
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
