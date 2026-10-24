import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Camera as CameraIcon,
  AlertTriangle,
  CheckCircle2,
  Radio,
  Plus,
  RefreshCw,
  ExternalLink,
} from 'lucide-react'
import { api } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Modal } from '@/components/ui/Modal'
import { CameraTile } from '@/components/evidence/CameraTile'
import { toast } from 'sonner'
import type { Camera } from '@/api/types'

export const CamerasPage: React.FC = () => {
  const queryClient = useQueryClient()
  const { user } = useAuthStore()
  const isOwnerOrAdmin = user?.role === 'owner' || user?.role === 'admin'

  const [healthModalOpen, setHealthModalOpen] = useState(false)
  const [selectedCamera, setSelectedCamera] = useState<Camera | null>(null)
  const [newStatus, setNewStatus] = useState<string>('ok')
  const [newReason, setNewReason] = useState<string>('')

  const { data: cameras = [], isLoading } = useQuery({
    queryKey: ['cameras'],
    queryFn: () => api.cameras.list(),
  })

  // Update Camera Health Mutation
  const updateHealthMutation = useMutation({
    mutationFn: (data: { cameraId: string; status: string; reason?: string }) =>
      api.cameras.updateHealth(data.cameraId, { status: data.status, reason: data.reason }),
    onSuccess: (_, variables) => {
      toast.success(`Camera health updated for ${variables.cameraId}`)
      setHealthModalOpen(false)
      setSelectedCamera(null)
      queryClient.invalidateQueries({ queryKey: ['cameras'] })
    },
    onError: (err: any) => {
      toast.error(err.message || 'Health update failed')
    },
  })

  const handleHealthSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedCamera) return
    updateHealthMutation.mutate({
      cameraId: selectedCamera.camera_id,
      status: newStatus,
      reason: newReason || undefined,
    })
  }

  const formatStatus = (status: string, isBlindSpot?: boolean) => {
    if (isBlindSpot || status === 'tampered') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold bg-critical-tint text-critical">
          <AlertTriangle size={12} />
          <span>Tampered (Blind Spot)</span>
        </span>
      )
    }
    if (status === 'degraded') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold bg-status-medium-tint text-status-medium">
          <AlertTriangle size={12} />
          <span>Degraded</span>
        </span>
      )
    }
    if (status === 'offline') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold bg-fill-subtle text-content-muted">
          <Radio size={12} />
          <span>Offline</span>
        </span>
      )
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold bg-status-healthy-tint text-status-healthy">
        <CheckCircle2 size={12} />
        <span>Healthy (OK)</span>
      </span>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-bold text-content-primary">Cameras</h1>
          <p className="text-[14px] text-content-secondary mt-0.5">
            CCTV video streams, automated optical tamper detection, and blind spot management.
          </p>
        </div>
      </div>

      {/* Camera Health Table */}
      <Card padding="none" className="overflow-hidden">
        <div className="p-4 border-b border-border-divider bg-fill-subtle/50">
          <h2 className="text-[16px] font-semibold text-content-primary">
            Camera status and hardware health
          </h2>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-border-divider text-content-muted text-[11px] uppercase tracking-wider">
                <th className="py-3 px-4">Camera</th>
                <th className="py-3 px-4">Zone</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Reason / Diagnosis</th>
                <th className="py-3 px-4">Blind Spot Flag</th>
                <th className="py-3 px-4">Resolution</th>
                {isOwnerOrAdmin && <th className="py-3 px-4 text-right">Action</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border-divider">
              {cameras.map((cam) => {
                const isTampered = cam.status === 'tampered' || (cam as any).is_blind_spot
                return (
                  <tr key={cam.camera_id} className="hover:bg-fill-subtle/30">
                    <td className="py-3 px-4 font-semibold text-content-primary">
                      <div className="flex items-center gap-2">
                        <CameraIcon size={16} className="text-primary shrink-0" />
                        <div>
                          <span>{cam.name}</span>
                          <span className="block text-[11px] font-mono text-content-muted font-normal">
                            {cam.camera_id}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-content-secondary font-medium">
                      {cam.zone_id ? cam.zone_id.replace(/_/g, ' ') : 'Zone'}
                    </td>
                    <td className="py-3 px-4">
                      {formatStatus(cam.status, (cam as any).is_blind_spot)}
                    </td>
                    <td className="py-3 px-4 text-content-body max-w-xs">
                      {cam.health_reason || (cam as any).status_reason || (isTampered ? 'Optical occlusion / sudden lens shift' : 'Nominal exposure & keypoint tracking')}
                    </td>
                    <td className="py-3 px-4">
                      {isTampered ? (
                        <span className="text-[11px] font-semibold text-critical bg-critical-tint px-2 py-0.5 rounded">
                          Blind spot active
                        </span>
                      ) : (
                        <span className="text-[11px] text-content-muted">None</span>
                      )}
                    </td>
                    <td className="py-3 px-4 font-mono text-[12px] text-content-secondary">
                      {(cam as any).resolution || '1920x1080 (30fps)'}
                    </td>
                    {isOwnerOrAdmin && (
                      <td className="py-3 px-4 text-right">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => {
                            setSelectedCamera(cam)
                            setNewStatus(cam.status)
                            setNewReason(cam.health_reason || (cam as any).status_reason || '')
                            setHealthModalOpen(true)
                          }}
                        >
                          Diagnose
                        </Button>
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Live Stream Previews */}
      <div>
        <h2 className="text-[17px] font-semibold text-content-primary mb-3">
          Camera feeds overview
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {cameras.map((cam) => (
            <CameraTile key={cam.camera_id} camera={cam} defaultMode="skeleton" />
          ))}
        </div>
      </div>

      {/* Health Update Modal */}
      <Modal
        isOpen={healthModalOpen}
        onClose={() => setHealthModalOpen(false)}
        title={`Diagnose Camera: ${selectedCamera?.name}`}
        description="Manually simulate optical occlusion, dark lens, blur, or restore health."
      >
        <form onSubmit={handleHealthSubmit} className="space-y-4">
          <div>
            <label className="block text-[13px] font-medium text-content-body mb-1">
              Camera Status
            </label>
            <select
              value={newStatus}
              onChange={(e) => setNewStatus(e.target.value)}
              className="w-full px-3 py-2 text-[14px] bg-card border border-border-input rounded-input"
            >
              <option value="ok">OK (Nominal stream)</option>
              <option value="degraded">Degraded (Low lighting / blur)</option>
              <option value="tampered">Tampered (Covered / Moved blind spot)</option>
              <option value="offline">Offline (Signal lost)</option>
            </select>
          </div>

          <div>
            <label className="block text-[13px] font-medium text-content-body mb-1">
              Reason / Diagnosis
            </label>
            <input
              type="text"
              value={newReason}
              onChange={(e) => setNewReason(e.target.value)}
              placeholder="e.g. Lens covered with tape or spray paint"
              className="w-full px-3 py-2 text-[14px] bg-card border border-border-input rounded-input"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setHealthModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              isLoading={updateHealthMutation.isPending}
            >
              Update camera state
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
