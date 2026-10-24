import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Sliders,
  Clock,
  Shield,
  Layers,
  Save,
  RotateCcw,
  Plus,
  Trash2,
  Lock,
  GitCommit,
  Check,
} from 'lucide-react'
import { api } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Modal } from '@/components/ui/Modal'
import { toast } from 'sonner'

export const RulesZonesPage: React.FC = () => {
  const queryClient = useQueryClient()
  const { user } = useAuthStore()
  const isOwnerOrAdmin = user?.role === 'owner' || user?.role === 'admin'

  // Fetch Rules
  const { data: rulesData, isLoading } = useQuery({
    queryKey: ['rules'],
    queryFn: () => api.rules.get(),
  })

  // Local form state
  const [curfewStart, setCurfewStart] = useState('23:00')
  const [curfewEnd, setCurfewEnd] = useState('05:30')
  const [fusionWindow, setFusionWindow] = useState<number>(30)
  const [tailgatingWindow, setTailgatingWindow] = useState<number>(5)
  const [contextRatio, setContextRatio] = useState<number>(0.8)

  // Per-zone thresholds
  const [terraceThreshold, setTerraceThreshold] = useState<number>(0.5)
  const [distressThreshold, setDistressThreshold] = useState<number>(0.35)
  const [fightThreshold, setFightThreshold] = useState<number>(0.6)

  // Polygon editor state
  const [selectedZoneKey, setSelectedZoneKey] = useState('terrace')
  const [polygonPoints, setPolygonPoints] = useState<Array<{ x: number; y: number }>>([
    { x: 120, y: 80 },
    { x: 420, y: 90 },
    { x: 480, y: 260 },
    { x: 100, y: 240 },
  ])
  const [doorLine, setDoorLine] = useState<{ x1: number; y1: number; x2: number; y2: number }>({
    x1: 180,
    y1: 160,
    x2: 360,
    y2: 160,
  })

  // Diff Preview Modal
  const [diffModalOpen, setDiffModalOpen] = useState(false)

  // Sync state once rules load
  React.useEffect(() => {
    if (rulesData) {
      if (rulesData.curfew) {
        setCurfewStart(rulesData.curfew.start || '23:00')
        setCurfewEnd(rulesData.curfew.end || '05:30')
      }
      if (rulesData.fusion) {
        setFusionWindow(rulesData.fusion.window_seconds || 30)
      }
      if (rulesData.tailgating) {
        setTailgatingWindow(rulesData.tailgating.window_seconds || 5)
      }
      if (rulesData.zones?.terrace?.thresholds) {
        setTerraceThreshold(rulesData.zones.terrace.thresholds.zone_intrusion || 0.5)
        setDistressThreshold(rulesData.zones.terrace.thresholds.distress_audio || 0.35)
        setFightThreshold(rulesData.zones.terrace.thresholds.fight || 0.6)
      }
    }
  }, [rulesData])

  // Save Mutation
  const saveMutation = useMutation({
    mutationFn: (updatedPayload: any) => api.rules.update(updatedPayload),
    onSuccess: () => {
      toast.success('Rules updated successfully. New thresholds applied.')
      setDiffModalOpen(false)
      queryClient.invalidateQueries({ queryKey: ['rules'] })
      queryClient.invalidateQueries({ queryKey: ['calibration'] })
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to update rules')
    },
  })

  // Add polygon point
  const handleSvgClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!isOwnerOrAdmin) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = Math.round(e.clientX - rect.left)
    const y = Math.round(e.clientY - rect.top)
    if (polygonPoints.length < 8) {
      setPolygonPoints([...polygonPoints, { x, y }])
    }
  }

  const handleSaveWithDiff = () => {
    setDiffModalOpen(true)
  }

  const handleConfirmSave = () => {
    const payload = {
      ...(rulesData || {}),
      curfew: {
        start: curfewStart,
        end: curfewEnd,
        applies_to_roles: ['resident'],
      },
      fusion: {
        window_seconds: fusionWindow,
      },
      tailgating: {
        window_seconds: tailgatingWindow,
      },
      zones: {
        ...(rulesData?.zones || {}),
        terrace: {
          ...(rulesData?.zones?.terrace || {}),
          thresholds: {
            zone_intrusion: terraceThreshold,
            distress_audio: distressThreshold,
            fight: fightThreshold,
          },
        },
      },
    }
    saveMutation.mutate(payload)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-bold text-content-primary">Rules & Zones</h1>
          <p className="text-[14px] text-content-secondary mt-0.5">
            Hostel curfew hours, multi-sensor fusion windows, polygon detection zones, and sensitivity sliders.
          </p>
        </div>

        {isOwnerOrAdmin && (
          <Button
            variant="primary"
            size="md"
            icon={<Save size={15} />}
            onClick={handleSaveWithDiff}
          >
            Review changes & save
          </Button>
        )}
      </div>

      {!isOwnerOrAdmin && (
        <div className="p-3.5 bg-fill-subtle rounded-card border border-border-card text-[13px] text-content-secondary flex items-center gap-2">
          <Lock size={15} className="text-content-muted" />
          <span>Rules configuration is read-only for security guards and auditors.</span>
        </div>
      )}

      {/* 1. Global Safety & Timing Parameters */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Curfew Rules */}
        <Card padding="md" className="space-y-3">
          <div className="flex items-center gap-2">
            <Clock size={16} className="text-primary" />
            <h2 className="text-[16px] font-semibold text-content-primary">
              Hostel Curfew Hours
            </h2>
          </div>
          <p className="text-[12px] text-content-muted">
            Rooftops and perimeter breaches automatically escalate to Critical during curfew.
          </p>

          <div className="grid grid-cols-2 gap-3 pt-1">
            <div>
              <label className="block text-[11px] font-semibold text-content-secondary uppercase mb-1">
                Curfew Start
              </label>
              <input
                type="text"
                disabled={!isOwnerOrAdmin}
                value={curfewStart}
                onChange={(e) => setCurfewStart(e.target.value)}
                className="w-full px-3 py-1.5 font-mono text-[13px] bg-card border border-border-input rounded-input"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-content-secondary uppercase mb-1">
                Curfew End
              </label>
              <input
                type="text"
                disabled={!isOwnerOrAdmin}
                value={curfewEnd}
                onChange={(e) => setCurfewEnd(e.target.value)}
                className="w-full px-3 py-1.5 font-mono text-[13px] bg-card border border-border-input rounded-input"
              />
            </div>
          </div>
        </Card>

        {/* Fusion Windows */}
        <Card padding="md" className="space-y-3">
          <div className="flex items-center gap-2">
            <Layers size={16} className="text-primary" />
            <h2 className="text-[16px] font-semibold text-content-primary">
              Fusion Time Window
            </h2>
          </div>
          <p className="text-[12px] text-content-muted">
            Maximum time offset between camera, acoustic mic, and swipe logs to corroborate.
          </p>

          <div className="pt-2">
            <div className="flex justify-between text-[13px] mb-1">
              <span className="text-content-body">Window duration:</span>
              <span className="font-mono font-semibold text-primary">{fusionWindow} seconds</span>
            </div>
            <input
              type="range"
              min="10"
              max="60"
              step="5"
              disabled={!isOwnerOrAdmin}
              value={fusionWindow}
              onChange={(e) => setFusionWindow(parseInt(e.target.value))}
              className="w-full accent-primary"
            />
          </div>
        </Card>

        {/* Tailgating & Context Ratio */}
        <Card padding="md" className="space-y-3">
          <div className="flex items-center gap-2">
            <Sliders size={16} className="text-primary" />
            <h2 className="text-[16px] font-semibold text-content-primary">
              Anti-Tailgating Buffer
            </h2>
          </div>
          <p className="text-[12px] text-content-muted">
            Turnstile swipe validity window before flag triggers for unswiped passage.
          </p>

          <div className="pt-2">
            <div className="flex justify-between text-[13px] mb-1">
              <span className="text-content-body">Swipe window:</span>
              <span className="font-mono font-semibold text-primary">{tailgatingWindow} s</span>
            </div>
            <input
              type="range"
              min="2"
              max="15"
              step="1"
              disabled={!isOwnerOrAdmin}
              value={tailgatingWindow}
              onChange={(e) => setTailgatingWindow(parseInt(e.target.value))}
              className="w-full accent-primary"
            />
          </div>
        </Card>
      </div>

      {/* 2. Interactive Polygon & Door-Line Camera Editor */}
      <Card padding="md" className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 className="text-[17px] font-semibold text-content-primary">
              Interactive Restricted Zone Polygon & Door-Line Editor
            </h2>
            <p className="text-[12px] text-content-muted">
              Click anywhere on the camera frame to add boundary points. Detection applies strictly inside polygon.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <select
              value={selectedZoneKey}
              onChange={(e) => setSelectedZoneKey(e.target.value)}
              className="px-3 py-1.5 text-[13px] bg-card border border-border-input rounded-input font-medium"
            >
              <option value="terrace">Terrace North Camera (cam_terrace)</option>
              <option value="block_b_entry">Block B Turnstile Gate (cam_entry)</option>
              <option value="common_room">Common Room Overhead (cam_common)</option>
            </select>
            {isOwnerOrAdmin && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  setPolygonPoints([
                    { x: 100, y: 100 },
                    { x: 400, y: 100 },
                    { x: 400, y: 240 },
                    { x: 100, y: 240 },
                  ])
                }
              >
                Reset polygon
              </Button>
            )}
          </div>
        </div>

        {/* SVG Canvas on Video Frame Background */}
        <div className="relative aspect-video max-w-3xl mx-auto bg-video-bg rounded-card overflow-hidden border border-border-card">
          {/* Simulated Camera Frame Background */}
          <div className="absolute inset-0 flex items-center justify-center opacity-40 select-none pointer-events-none">
            <span className="font-mono text-white text-[13px]">
              LIVE CALIBRATION FRAME: {selectedZoneKey.toUpperCase()}
            </span>
          </div>

          <svg
            className="w-full h-full cursor-crosshair"
            viewBox="0 0 600 340"
            onClick={handleSvgClick}
          >
            {/* Polygon with dashed red stroke and 14% fill */}
            <polygon
              points={polygonPoints.map((p) => `${p.x},${p.y}`).join(' ')}
              fill="rgba(240, 106, 98, 0.14)"
              stroke="#F06A62"
              strokeWidth="2"
              strokeDasharray="6,4"
            />

            {/* Polygon draggable handles */}
            {polygonPoints.map((pt, i) => (
              <circle
                key={i}
                cx={pt.x}
                cy={pt.y}
                r="6"
                fill="#FFFFFF"
                stroke="#C42B2B"
                strokeWidth="2.5"
              />
            ))}

            {/* Door Tripwire line for entry gate */}
            {selectedZoneKey === 'block_b_entry' && (
              <g>
                <line
                  x1={doorLine.x1}
                  y1={doorLine.y1}
                  x2={doorLine.x2}
                  y2={doorLine.y2}
                  stroke="#2E8B57"
                  strokeWidth="3.5"
                />
                <text
                  x={doorLine.x1 + 10}
                  y={doorLine.y1 - 8}
                  fill="#2E8B57"
                  fontSize="12"
                  fontWeight="bold"
                >
                  TURNSTILE ENTRY TRIPWIRE
                </text>
              </g>
            )}
          </svg>

          {/* Canvas overlay instructions */}
          <div className="absolute bottom-2 left-2 z-10 px-2.5 py-1 rounded bg-black/70 text-[#EDEBE6] text-[11px] font-mono">
            Polygon points: {polygonPoints.length}/8 · Dashed red: Restricted active zone
          </div>
        </div>
      </Card>

      {/* 3. Per-Zone Detection Sensitivity Threshold Sliders */}
      <Card padding="md" className="space-y-4">
        <h2 className="text-[17px] font-semibold text-content-primary">
          Per-zone detection sensitivity thresholds
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-1">
          {/* Zone Intrusion */}
          <div className="space-y-2">
            <div className="flex justify-between text-[13px]">
              <span className="font-medium text-content-primary">Zone intrusion (Pose)</span>
              <span className="font-mono text-primary font-semibold">{terraceThreshold.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min="0.2"
              max="0.9"
              step="0.05"
              disabled={!isOwnerOrAdmin}
              value={terraceThreshold}
              onChange={(e) => setTerraceThreshold(parseFloat(e.target.value))}
              className="w-full accent-primary"
            />
            <p className="text-[11px] text-content-muted">
              Higher requires longer pose presence in restricted zone.
            </p>
          </div>

          {/* Distress Audio */}
          <div className="space-y-2">
            <div className="flex justify-between text-[13px]">
              <span className="font-medium text-content-primary">Distress audio (Scream)</span>
              <span className="font-mono text-primary font-semibold">{distressThreshold.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min="0.1"
              max="0.8"
              step="0.05"
              disabled={!isOwnerOrAdmin}
              value={distressThreshold}
              onChange={(e) => setDistressThreshold(parseFloat(e.target.value))}
              className="w-full accent-primary"
            />
            <p className="text-[11px] text-content-muted">
              Lower catches quieter screams; acoustic filter prevents music false alarms.
            </p>
          </div>

          {/* Fight */}
          <div className="space-y-2">
            <div className="flex justify-between text-[13px]">
              <span className="font-medium text-content-primary">Fight detection</span>
              <span className="font-mono text-primary font-semibold">{fightThreshold.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min="0.3"
              max="0.9"
              step="0.05"
              disabled={!isOwnerOrAdmin}
              value={fightThreshold}
              onChange={(e) => setFightThreshold(parseFloat(e.target.value))}
              className="w-full accent-primary"
            />
            <p className="text-[11px] text-content-muted">
              Rapid limb velocity threshold across two bodies.
            </p>
          </div>
        </div>
      </Card>

      {/* Diff Preview Modal */}
      <Modal
        isOpen={diffModalOpen}
        onClose={() => setDiffModalOpen(false)}
        title="Diff preview of proposed rule changes"
        description="Verify changes before saving to live multi-tenant engine."
      >
        <div className="space-y-4">
          <div className="bg-fill-subtle rounded-card p-3 border border-border-card font-mono text-[12px] space-y-1">
            <div className="text-status-healthy">
              + curfew.start: "{curfewStart}" (was "{rulesData?.curfew?.start || '23:00'}")
            </div>
            <div className="text-status-healthy">
              + curfew.end: "{curfewEnd}" (was "{rulesData?.curfew?.end || '05:30'}")
            </div>
            <div className="text-status-healthy">
              + fusion.window_seconds: {fusionWindow}
            </div>
            <div className="text-status-healthy">
              + zones.terrace.thresholds.zone_intrusion: {terraceThreshold.toFixed(2)}
            </div>
            <div className="text-content-muted">
              ~ polygon coordinates updated: {polygonPoints.length} vertices
            </div>
          </div>

          <p className="text-[12px] text-content-muted">
            This configuration revision will be versioned and recorded in the audit history.
          </p>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setDiffModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="primary"
              isLoading={saveMutation.isPending}
              onClick={handleConfirmSave}
            >
              Apply and activate rules
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
