import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Printer,
  Compass,
  AlertTriangle,
  Clock,
  Shield,
  ShieldAlert,
  Info,
  Maximize2,
  Download,
  ShieldCheck,
  AlertCircle,
  QrCode,
} from 'lucide-react'
import { api } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Modal } from '@/components/ui/Modal'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { SeverityDot } from '@/components/ui/SeverityDot'
import { StatStrip } from '@/components/ui/StatStrip'
import { toast } from 'sonner'
import type { Zone } from '@/api/types'

interface ZoneDetailModalProps {
  zoneId: string | null
  onClose: () => void
  zones: Zone[]
}

const ZoneDetailModal: React.FC<ZoneDetailModalProps> = ({ zoneId, onClose, zones }) => {
  const navigate = useNavigate()
  const [qrUrl, setQrUrl] = useState<string | null>(null)
  const [blob, setBlob] = useState<Blob | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const zone = zones.find((z) => z.zone_id === zoneId)
  const zoneName = zone?.name || (zoneId ? zoneId.replace(/_/g, ' ') : 'Zone')

  useEffect(() => {
    if (!zoneId) {
      setQrUrl(null)
      setBlob(null)
      return
    }

    let active = true
    let createdUrl: string | null = null

    setIsLoading(true)
    setError(null)

    api.sos.getZoneQrBlob(zoneId)
      .then((dataBlob) => {
        if (!active) return
        createdUrl = URL.createObjectURL(dataBlob)
        setBlob(dataBlob)
        setQrUrl(createdUrl)
        setIsLoading(false)
      })
      .catch((err) => {
        if (!active) return
        setError(err.message || 'Failed to generate QR')
        setIsLoading(false)
      })

    return () => {
      active = false
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl)
      }
    }
  }, [zoneId])

  const handleDownload = () => {
    if (!blob || !zoneId) {
      toast.error('QR code is still loading')
      return
    }
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `sos-qr-${zoneId}.png`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    toast.success(`Downloaded SOS QR for ${zoneName}`)
  }

  if (!zoneId) return null

  return (
    <Modal
      isOpen={!!zoneId}
      onClose={onClose}
      title={zoneName}
      description={`Zone ID: ${zoneId} · ${zone?.type ? zone.type.toUpperCase() : 'HOSTEL ZONE'}`}
      maxWidth="md"
    >
      <div className="space-y-4">
        {/* Student SOS QR Code Poster View */}
        <div className="bg-white rounded-[12px] border-2 border-border-card p-5 flex flex-col items-center text-center shadow-soft">
          <div className="flex items-center gap-1.5 text-[11px] font-mono text-primary uppercase tracking-wider mb-1">
            <ShieldCheck size={14} />
            <span>Student Anonymous SOS Code</span>
          </div>

          <div className="my-2 p-2 bg-white rounded-[8px] flex items-center justify-center min-h-[170px]">
            {isLoading ? (
              <div className="flex flex-col items-center justify-center gap-2 py-6 text-content-muted">
                <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                <span className="text-[12px]">Generating zone QR…</span>
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center gap-2 py-6 text-status-high">
                <AlertCircle size={22} />
                <span className="text-[12px]">{error}</span>
              </div>
            ) : qrUrl ? (
              <img
                src={qrUrl}
                alt={`SOS QR code for ${zoneName}`}
                className="w-40 h-40 object-contain shadow-soft"
              />
            ) : null}
          </div>

          <div className="mt-2 pt-2 border-t border-border-divider w-full space-y-1">
            <p className="text-[14px] font-bold text-content-primary">
              Feeling unsafe? Scan for help. Anonymous.
            </p>
            <p className="text-[11px] text-content-secondary leading-tight">
              Scanned on smartphone by students in this zone to trigger silent alerts.
            </p>
          </div>

          <div className="mt-3 pt-2 border-t border-border-divider/50 flex items-center gap-3">
            <button
              type="button"
              onClick={handleDownload}
              disabled={isLoading || !blob}
              className="inline-flex items-center gap-1 text-[12px] font-medium text-primary hover:underline disabled:opacity-50"
            >
              <Download size={13} />
              Download PNG
            </button>
            <span className="text-content-muted text-[11px]">·</span>
            <button
              type="button"
              onClick={() => {
                onClose()
                navigate('/settings/sos-qr')
              }}
              className="inline-flex items-center gap-1 text-[12px] font-medium text-content-secondary hover:text-content-primary hover:underline"
            >
              <Printer size={13} />
              Print all posters
            </button>
          </div>
        </div>

        {/* Modal footer actions */}
        <div className="flex items-center justify-between pt-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              onClose()
              navigate(`/incidents?zone=${zoneId}`)
            }}
          >
            View incidents for this zone
          </Button>

          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export const MapPatrolPage: React.FC = () => {
  const navigate = useNavigate()
  const [heatmapMode, setHeatmapMode] = useState<'raw' | 'verified'>('raw')
  const [selectedZone, setSelectedZone] = useState<string | null>(null)

  // Fetch Zones
  const { data: zones = [] } = useQuery({
    queryKey: ['zones_list'],
    queryFn: () => api.zones.list(),
  })

  // Fetch Heatmap data
  const { data: heatmapData } = useQuery({
    queryKey: ['analytics_heatmap'],
    queryFn: () => api.analytics.getHeatmap(30),
  })

  // Fetch Patrol Plan
  const { data: patrolPlanData } = useQuery({
    queryKey: ['analytics_patrol_plan'],
    queryFn: () => api.analytics.getPatrolPlan(),
  })

  // Fetch Summary
  const { data: summary } = useQuery({
    queryKey: ['analytics_summary'],
    queryFn: () => api.analytics.getSummary(),
  })

  // Zones open incidents map (for styling floor plan)
  const zoneStatus: Record<
    string,
    { severity: 'critical' | 'high' | 'medium' | 'low' | 'healthy'; count: number; blindSpot?: boolean }
  > = {
    terrace: { severity: 'critical', count: 6 },
    block_b_entry: { severity: 'high', count: 3 },
    common_room: { severity: 'medium', count: 3 },
    corridor_2f: { severity: 'low', count: 1 },
    server_room: { severity: 'healthy', count: 0 },
    back_wall: { severity: 'healthy', count: 0, blindSpot: false },
  }

  // Heatmap color scale function (#F1EFEA → #F6D9C3 → #EDB085 → #D9784A → #A8402A)
  const getCellColor = (value: number) => {
    if (value <= 0) return '#F1EFEA'
    if (value <= 2) return '#F6D9C3'
    if (value <= 5) return '#EDB085'
    if (value <= 10) return '#D9784A'
    return '#A8402A'
  }

  const getTextColor = (value: number) => {
    return value > 5 ? '#FFFFFF' : '#34363B'
  }

  const patrolItems = (patrolPlanData as any)?.plan || []
  const heatmapRows = (heatmapData as any)?.zones || []

  const handlePrint = () => {
    window.print()
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-bold text-content-primary">Map & Patrol</h1>
          <p className="text-[14px] text-content-secondary mt-0.5">
            Spatial hostel floor plan, empirical risk heatmaps, and AI-optimized guard patrol routes.
          </p>
        </div>

        <Button
          variant="secondary"
          size="md"
          icon={<Printer size={15} />}
          onClick={handlePrint}
        >
          Print patrol sheet
        </Button>
      </div>

      {/* Summary Cards */}
      <StatStrip
        stats={[
          {
            label: 'Shift Coverage',
            value: '22:00 – 06:00',
            meta: <span>8 curfew hours active</span>,
          },
          {
            label: 'Top Risk Zone',
            value: 'Terrace Rooftop',
            meta: <span>Peak activity 03:00–04:00 am</span>,
          },
          {
            label: 'Scheduled Checks',
            value: `${patrolItems.length} locations`,
            meta: <span>Every 45 minutes</span>,
          },
          {
            label: 'Guard Assigned',
            value: 'Ramesh K.',
            meta: <span>On terrace & perimeter</span>,
          },
        ]}
      />

      {/* 1. Hostel Floor Plan (CSS Grid) */}
      <Card padding="md" className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 className="text-[17px] font-semibold text-content-primary">
              Hostel Floor Plan & Active Zones
            </h2>
            <p className="text-[12px] text-content-muted">
              Click any zone to filter queue. Critical zones pulse; red stripes indicate camera blind spots.
            </p>
          </div>
          <span className="text-[11px] font-mono text-content-muted">
            Block B Hostel · 2 Levels
          </span>
        </div>

        {/* CSS Floor Plan Grid */}
        <div className="relative p-6 bg-fill-subtle rounded-card border border-border-card min-h-[340px] flex flex-col justify-between">
          {/* Top Level (Terrace & Perimeter Wall) */}
          <div className="mb-4">
            <span className="text-[11px] font-semibold text-content-muted uppercase tracking-wider block mb-2">
              Level 3 / Rooftop & Perimeter
            </span>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              {/* Back Wall Perimeter (thick boundary line) */}
              <div
                onClick={() => setSelectedZone('back_wall')}
                className="col-span-1 p-3.5 rounded-card bg-card border-4 border-dashed border-[#5C5F66] flex flex-col justify-between cursor-pointer hover:bg-fill-active transition-all"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-bold text-content-primary">Back Wall</span>
                    <span className="text-[10px] font-mono text-content-muted">PERIMETER</span>
                  </div>
                  <p className="text-[11px] text-content-muted mt-2">
                    Thick boundary line · Infrared tripwire active
                  </p>
                </div>
                <div className="mt-2.5 pt-1.5 border-t border-border-divider/50 flex items-center justify-between text-[11px] text-primary font-medium">
                  <span className="flex items-center gap-1">
                    <QrCode size={12} />
                    SOS QR
                  </span>
                  <span className="text-content-muted text-[10px]">Details →</span>
                </div>
              </div>

              {/* Terrace Rooftop (Critical Pulsing) */}
              <div
                onClick={() => setSelectedZone('terrace')}
                className="col-span-3 p-4 rounded-card bg-card border-2 border-critical shadow-soft cursor-pointer hover:bg-critical-tint/30 transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-critical animate-critical-pulse" />
                      <span className="text-[14px] font-bold text-content-primary">Terrace Rooftop</span>
                    </div>
                    <span className="text-[12px] font-mono text-critical font-semibold">
                      6 active alerts
                    </span>
                  </div>
                  <p className="text-[12px] text-content-body mt-2">
                    Curfew breach detected. Camera, microphone and door log agree.
                  </p>
                </div>
                <div className="mt-2.5 pt-1.5 border-t border-border-divider/50 flex items-center justify-between text-[11px] text-critical font-medium">
                  <span className="flex items-center gap-1">
                    <QrCode size={12} />
                    SOS QR Code
                  </span>
                  <span className="text-content-muted text-[10px]">Tap to view details →</span>
                </div>
              </div>
            </div>
          </div>

          {/* Middle Level: Corridor 2F & Server Room */}
          <div className="mb-4">
            <span className="text-[11px] font-semibold text-content-muted uppercase tracking-wider block mb-2">
              Level 2 / Residential Dormitory
            </span>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {/* Corridor 2F */}
              <div
                onClick={() => setSelectedZone('corridor_2f')}
                className="md:col-span-2 p-3.5 rounded-card bg-card border border-border-card cursor-pointer hover:bg-fill-active transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-status-low" />
                      <span className="text-[13px] font-semibold text-content-primary">
                        Corridor 2F South
                      </span>
                    </div>
                    <span className="text-[11px] font-mono text-content-secondary">
                      1 alert (tailgating)
                    </span>
                  </div>
                  <p className="text-[11px] text-content-muted mt-2">
                    Dorm rooms 201–224 · Passive PIR & video motion active
                  </p>
                </div>
                <div className="mt-2.5 pt-1.5 border-t border-border-divider/50 flex items-center justify-between text-[11px] text-primary font-medium">
                  <span className="flex items-center gap-1">
                    <QrCode size={12} />
                    SOS QR
                  </span>
                  <span className="text-content-muted text-[10px]">Details →</span>
                </div>
              </div>

              {/* Server Room */}
              <div
                onClick={() => setSelectedZone('server_room')}
                className="p-3.5 rounded-card bg-card border border-border-card cursor-pointer hover:bg-fill-active transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-semibold text-content-primary">
                      Server Infrastructure
                    </span>
                    <span className="text-[10px] text-status-healthy font-medium">Quiet</span>
                  </div>
                  <p className="text-[11px] text-content-muted mt-2">
                    Keycard swipe required
                  </p>
                </div>
                <div className="mt-2.5 pt-1.5 border-t border-border-divider/50 flex items-center justify-between text-[11px] text-primary font-medium">
                  <span className="flex items-center gap-1">
                    <QrCode size={12} />
                    SOS QR
                  </span>
                  <span className="text-content-muted text-[10px]">Details →</span>
                </div>
              </div>
            </div>
          </div>

          {/* Ground Level: Entry Turnstile & Common Room */}
          <div>
            <span className="text-[11px] font-semibold text-content-muted uppercase tracking-wider block mb-2">
              Ground Level / Access & Lounge
            </span>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Block B Turnstile Gate */}
              <div
                onClick={() => setSelectedZone('block_b_entry')}
                className="p-4 rounded-card bg-card border border-status-high shadow-soft cursor-pointer hover:bg-status-high-tint/30 transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-status-high" />
                      <span className="text-[14px] font-bold text-content-primary">
                        Block B Main Turnstile Entry
                      </span>
                    </div>
                    <span className="text-[11px] font-mono text-status-high font-semibold">
                      3 active alerts
                    </span>
                  </div>
                  <p className="text-[12px] text-content-body mt-2">
                    Tailgating verification & recent student SOS report.
                  </p>
                </div>
                <div className="mt-2.5 pt-1.5 border-t border-border-divider/50 flex items-center justify-between text-[11px] text-status-high font-medium">
                  <span className="flex items-center gap-1">
                    <QrCode size={12} />
                    SOS QR Code
                  </span>
                  <span className="text-content-muted text-[10px]">Tap to view details →</span>
                </div>
              </div>

              {/* Common Room */}
              <div
                onClick={() => setSelectedZone('common_room')}
                className="p-4 rounded-card bg-card border border-status-medium cursor-pointer hover:bg-status-medium-tint/30 transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-status-medium" />
                      <span className="text-[14px] font-semibold text-content-primary">
                        Common Recreation Lounge
                      </span>
                    </div>
                    <span className="text-[11px] font-mono text-content-secondary">
                      3 active alerts
                    </span>
                  </div>
                  <p className="text-[12px] text-content-muted mt-2">
                    Acoustic context filter suppresses harmless laughter.
                  </p>
                </div>
                <div className="mt-2.5 pt-1.5 border-t border-border-divider/50 flex items-center justify-between text-[11px] text-primary font-medium">
                  <span className="flex items-center gap-1">
                    <QrCode size={12} />
                    SOS QR Code
                  </span>
                  <span className="text-content-muted text-[10px]">Tap to view details →</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* 2. Risk Heatmap: zone x hour-of-day grid */}
      <Card padding="md" className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-[17px] font-semibold text-content-primary">
              {heatmapMode === 'raw'
                ? 'When alarms go off (Every alert)'
                : 'When incidents really happen (Confirmed by guards)'}
            </h2>
            <p className="text-[12px] text-content-muted">
              {heatmapMode === 'raw'
                ? 'Raw multi-sensor alarm triggers over past 30 days.'
                : 'Review-weighted risk score accounting for guard verification.'}
            </p>
          </div>

          {/* Toggle "Raw alerts vs Verified risk" */}
          <div className="inline-flex items-center bg-fill-active p-1 rounded-[8px]">
            <button
              type="button"
              onClick={() => setHeatmapMode('raw')}
              className={`px-3 py-1.5 text-[12px] font-medium rounded-[6px] transition-all ${
                heatmapMode === 'raw'
                  ? 'bg-card text-content-primary shadow-soft'
                  : 'text-content-secondary hover:text-content-primary'
              }`}
            >
              Every alert (Raw)
            </button>
            <button
              type="button"
              onClick={() => setHeatmapMode('verified')}
              className={`px-3 py-1.5 text-[12px] font-medium rounded-[6px] transition-all ${
                heatmapMode === 'verified'
                  ? 'bg-card text-content-primary shadow-soft'
                  : 'text-content-secondary hover:text-content-primary'
              }`}
            >
              Confirmed by guards (Verified)
            </button>
          </div>
        </div>

        {/* 24-hour Matrix Grid */}
        <div className="overflow-x-auto">
          <table className="w-full text-center border-collapse text-[11px]">
            <thead>
              <tr>
                <th className="p-2 text-left text-content-secondary font-medium min-w-[140px]">
                  Zone
                </th>
                {Array.from({ length: 24 }).map((_, h) => (
                  <th key={h} className="p-1 font-mono text-content-muted font-normal w-8">
                    {h}h
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {heatmapRows.map((row: any) => (
                <tr key={row.zone_id} className="border-t border-border-divider/60">
                  <td className="p-2 text-left font-medium text-content-primary text-[12px] whitespace-nowrap">
                    {row.zone_name || row.zone_id}
                  </td>
                  {Array.from({ length: 24 }).map((_, h) => {
                    const hourData = row.hours?.[String(h)] || {}
                    const val =
                      heatmapMode === 'raw'
                        ? hourData.incident_count || 0
                        : Math.round(hourData.risk_score || 0)
                    const bg = getCellColor(val)
                    const tc = getTextColor(val)

                    return (
                      <td
                        key={h}
                        style={{ backgroundColor: bg, color: tc }}
                        title={`${row.zone_name} @ ${h}:00 - ${val} ${
                          heatmapMode === 'raw' ? 'alerts' : 'risk score'
                        }`}
                        className="p-1 font-mono text-[10px] rounded-[3px] border border-white/40 cursor-default"
                      >
                        {val > 0 ? val : ''}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Heatmap Legend */}
        <div className="flex items-center justify-end gap-2 text-[11px] text-content-muted pt-2 border-t border-border-divider">
          <span>Low</span>
          <span className="w-3.5 h-3.5 rounded-[2px]" style={{ backgroundColor: '#F1EFEA' }} />
          <span className="w-3.5 h-3.5 rounded-[2px]" style={{ backgroundColor: '#F6D9C3' }} />
          <span className="w-3.5 h-3.5 rounded-[2px]" style={{ backgroundColor: '#EDB085' }} />
          <span className="w-3.5 h-3.5 rounded-[2px]" style={{ backgroundColor: '#D9784A' }} />
          <span className="w-3.5 h-3.5 rounded-[2px]" style={{ backgroundColor: '#A8402A' }} />
          <span>High Risk</span>
        </div>
      </Card>

      {/* 3. Tonight's Patrol Plan Card */}
      <Card padding="md" className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-[17px] font-semibold text-content-primary">
              Tonight's Patrol Plan
            </h2>
            <p className="text-[12px] text-content-muted">
              Ordered zones based on historical curfew risks and active alerts.
            </p>
          </div>
          <span className="text-[12px] font-mono text-primary font-medium">
            Shift: 22:00 – 06:00
          </span>
        </div>

        <div className="divide-y divide-border-divider">
          {patrolItems.map((item: any, idx: number) => (
            <div key={idx} className="py-3.5 flex items-start justify-between gap-4">
              <div className="flex items-start gap-4">
                <div className="w-16 font-mono text-[13px] font-semibold text-content-primary shrink-0 pt-0.5">
                  {item.suggested_check_time || 'now'}
                </div>

                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[14px] font-bold text-content-primary">
                      {item.zone_name}
                    </span>
                    {item.open_incidents > 0 && (
                      <span className="text-[11px] px-1.5 py-0.2 rounded bg-critical-tint text-critical font-medium">
                        {item.open_incidents} open
                      </span>
                    )}
                    {item.recent_sos && (
                      <span className="text-[11px] px-1.5 py-0.2 rounded bg-status-high-tint text-status-high font-medium">
                        recent SOS
                      </span>
                    )}
                  </div>
                  <p className="text-[13px] text-content-body mt-1 leading-relaxed">
                    {item.reason}
                  </p>
                </div>
              </div>

              <div className="text-right shrink-0">
                <span className="text-[11px] font-mono text-content-muted block">
                  risk index: {Math.round(item.risk_score || 0)}
                </span>
                <span className="text-[11px] text-content-secondary block mt-0.5">
                  peak: {item.peak_hour}:00
                </span>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Zone Detail Modal with SOS QR Code */}
      <ZoneDetailModal
        zoneId={selectedZone}
        onClose={() => setSelectedZone(null)}
        zones={zones}
      />
    </div>
  )
}
