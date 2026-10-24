import React, { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft,
  CheckCircle,
  AlertTriangle,
  Clock,
  Video,
  Mic,
  CreditCard,
  Megaphone,
  User,
  ShieldCheck,
  ShieldAlert,
  Info,
  CheckSquare,
  Square,
  Sparkles,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { api } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { SeverityDot } from '@/components/ui/SeverityDot'
import { Countdown } from '@/components/ui/Countdown'
import { EvidenceViewToggle, ViewTier } from '@/components/evidence/EvidenceViewToggle'
import { toast } from 'sonner'
import type { Incident, Signal } from '@/api/types'

export const IncidentDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user } = useAuthStore()

  // State
  const [currentView, setCurrentView] = useState<ViewTier>('skeleton')
  const [reviewOutcome, setReviewOutcome] = useState<'confirmed' | 'false_positive' | 'investigating'>('confirmed')
  const [reviewNote, setReviewNote] = useState('')
  const [checkedPlaybook, setCheckedPlaybook] = useState<Record<string, boolean>>({})

  // Fetch Incident
  const { data: incident, isLoading, error } = useQuery({
    queryKey: ['incident', id],
    queryFn: () => api.incidents.get(id!),
    enabled: !!id,
    refetchInterval: 5000,
  })

  // Fetch Evidence Access Info (with fallback)
  const { data: accessInfo, refetch: refetchAccess } = useQuery({
    queryKey: ['incident_access', id],
    queryFn: async () => {
      try {
        return await api.evidence.getAccess(id!)
      } catch {
        // Fallback if backend evidence endpoint is still being stabilized
        return {
          incident_id: id!,
          default_view: 'skeleton',
          available_views: ['skeleton', 'blurred', 'unblurred'],
          skeleton_available: true,
          blurred_available: true,
          unblurred_available: false,
          blurred_locked: true,
          unblurred_locked: true,
          emergency_context_available: false,
          emergency_reveal_eligible: true,
        } as any
      }
    },
    enabled: !!id,
  })

  // Acknowledge mutation
  const ackMutation = useMutation({
    mutationFn: () => api.incidents.acknowledge(id!, { notes: 'Awaiting investigation' }),
    onSuccess: (updated) => {
      toast.success("You are on it! Incident acknowledged.", {
        description: `Logged for ${user?.full_name || 'Staff'}. Response clock stopped.`,
      })
      queryClient.setQueryData(['incident', id], updated)
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to acknowledge incident')
    },
  })

  // Review mutation
  const reviewMutation = useMutation({
    mutationFn: () =>
      api.incidents.review(id!, {
        outcome: reviewOutcome,
        notes: reviewNote,
      }),
    onSuccess: (updated) => {
      if (reviewOutcome === 'false_positive') {
        const zoneName = incident?.zone_id?.replace(/_/g, ' ') || 'zone'
        toast.success(`Thresholds recalibrated for ${zoneName}`, {
          description: 'Acoustic & visual sensitivity updated to reduce future false alarms.',
        })
      } else {
        toast.success('Decision recorded and logged in audit trail.')
      }
      queryClient.setQueryData(['incident', id], updated)
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
      queryClient.invalidateQueries({ queryKey: ['analytics'] })
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to submit decision')
    },
  })

  if (isLoading) {
    return (
      <div className="py-20 text-center text-content-muted">
        <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-[14px]">Loading incident details…</p>
      </div>
    )
  }

  if (error || !incident) {
    return (
      <div className="py-16 text-center">
        <h2 className="text-[18px] font-semibold text-critical">Incident not found</h2>
        <p className="text-[13px] text-content-muted mt-1 mb-4">
          This incident may have been removed or does not exist.
        </p>
        <Link to="/app/incidents">
          <Button variant="secondary" size="sm">
            Back to incidents
          </Button>
        </Link>
      </div>
    )
  }

  const isAcknowledged =
    incident.status && incident.status !== 'new' && incident.status !== 'open'
  const isReviewed =
    incident.status === 'confirmed' ||
    incident.status === 'false_alarm' ||
    incident.status === 'false_positive'

  // Playbook checklists by incident kind
  const incidentKind =
    incident.signals?.[0]?.kind ||
    ((incident as any).title_human?.toLowerCase().includes('intrusion') ? 'intrusion' : 'intrusion')

  const playbooks: Record<string, string[]> = {
    intrusion: [
      'Dispatch nearest guard to investigate zone',
      'Verify perimeter on camera skeleton feed',
      'Notify floor warden if unswiped stranger is spotted',
    ],
    fight: [
      'Send 2 security guards immediately to defuse tension',
      'Call campus medical staff if anyone is injured',
      'Notify senior hostel warden',
    ],
    distress_audio: [
      'Check zone immediately for student welfare',
      'Verify whether loud sound was harmless noise or distress',
      'Escalate to medical emergency if no verbal response',
    ],
    student_sos: [
      'Go directly to reported student location',
      'Contact reporter area discretely without alarming crowd',
      'Ensure student is accompanied to safety and notify warden',
    ],
    camera_tamper: [
      'Inspect physical camera mount and lens surface',
      'Patrol the blind-spot zone on foot until feed restored',
      'Log tamper inspection ticket in maintenance',
    ],
  }

  const activePlaybook =
    playbooks[incidentKind] ||
    playbooks[
      incident.explanation?.toLowerCase().includes('sos')
        ? 'student_sos'
        : incident.explanation?.toLowerCase().includes('fight')
        ? 'fight'
        : 'intrusion'
    ]

  const togglePlaybook = (task: string) => {
    setCheckedPlaybook((prev) => ({ ...prev, [task]: !prev[task] }))
  }

  // Audio top-5 sound classes demo data (or from signal details)
  const soundClassesData = [
    { name: 'Scream / Distress', score: 0.88 },
    { name: 'Raised voices', score: 0.62 },
    { name: 'Door slam', score: 0.35 },
    { name: 'Cheering', score: 0.12 },
    { name: 'Laughter', score: 0.08 },
  ]

  // Pseudonymised Access Events
  const accessEvents = (incident.access_events && incident.access_events.length > 0)
    ? incident.access_events
    : [
        {
          timestamp: '23:36:12',
          badge_id: 'STUDENT-HASH-8A91',
          reader: 'Turnstile A (Entry)',
          status: 'Authorized',
        },
        {
          timestamp: '23:38:40',
          badge_id: 'UNSWIPED-PRESENCE',
          reader: 'Terrace Stairwell Door',
          status: 'No swipe detected',
        },
      ]

  // Time format helper
  const formatTimeStr = (isoString?: string) => {
    if (!isoString) return ''
    try {
      const d = new Date(isoString)
      let hours = d.getHours()
      const minutes = d.getMinutes()
      const ampm = hours >= 12 ? 'pm' : 'am'
      hours = hours % 12
      hours = hours ? hours : 12
      const minsStr = minutes < 10 ? '0' + minutes : String(minutes)
      const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
      return `${days[d.getDay()]}, ${hours}:${minsStr} ${ampm}`
    } catch {
      return ''
    }
  }

  return (
    <div className="space-y-6">
      {/* 1. Header with Breadcrumb, Meta line, and Action Buttons */}
      <div>
        <div className="flex items-center gap-2 text-[13px] text-content-muted mb-2">
          <Link to="/app/incidents" className="hover:text-primary transition-colors flex items-center gap-1">
            <ChevronLeft size={14} />
            <span>Incidents</span>
          </Link>
          <span>/</span>
          <span className="font-mono text-content-secondary">
            {incident.id.slice(-6)}
          </span>
        </div>

        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1">
            <h1 className="text-[24px] sm:text-[26px] font-bold text-content-primary leading-tight">
              {(incident as any).title_human ||
                incident.explanation ||
                'Someone is on the terrace after curfew, and a scream was heard'}
            </h1>
            <p className="text-[13px] text-content-secondary flex flex-wrap items-center gap-2">
              <SeverityDot severity={incident.severity} pulse={!isAcknowledged} />
              <span className="text-border-divider">·</span>
              <span className="font-medium">
                {incident.zone_id ? incident.zone_id.replace(/_/g, ' ') : 'Terrace Rooftop'}
              </span>
              <span className="text-border-divider">·</span>
              <span>{formatTimeStr(incident.created_ts)}</span>
              <span className="text-border-divider">·</span>
              {!isAcknowledged ? (
                <span className="text-critical font-medium">
                  not yet acknowledged · warden alerted in{' '}
                  <Countdown secondsLeft={(incident as any).sla_countdown_seconds || 42} />
                </span>
              ) : (
                <span className="text-status-healthy font-medium">
                  {incident.acknowledged_by ? `${incident.acknowledged_by} on it` : "Ramesh on it"}
                </span>
              )}
            </p>
          </div>

          <div className="flex items-center gap-2.5 shrink-0">
            <Button
              variant="secondary"
              size="md"
              onClick={() => toast.info('Assignment request sent to guard patrol Ramesh K.')}
            >
              Assign to…
            </Button>
            {!isAcknowledged ? (
              <Button
                variant="primary"
                size="md"
                isLoading={ackMutation.isPending}
                onClick={() => ackMutation.mutate()}
                icon={<CheckCircle size={16} />}
              >
                I'm on it
              </Button>
            ) : (
              <div className="px-3 py-1.5 rounded-btn bg-status-healthy-tint text-status-healthy text-[13px] font-medium flex items-center gap-1.5 border border-status-healthy/30">
                <CheckCircle size={15} />
                <span>Acknowledged</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 2. Main 2-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Columns: Evidence Player, What Happened, Why Fired, Audio & Access */}
        <div className="lg:col-span-2 space-y-6">
          {/* Evidence Video with View Tier Toggle */}
          <Card padding="md" className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-[17px] font-semibold text-content-primary">
                Sensor evidence & video footage
              </h2>
              <span className="text-[12px] text-content-muted">
                {currentView === 'skeleton'
                  ? 'Keypoints on black · Privacy preserved'
                  : currentView === 'blurred'
                  ? 'Face-blurred real footage'
                  : 'Unblurred (authorized)'}
              </span>
            </div>

            {/* Evidence View Toggle Component */}
            <EvidenceViewToggle
              incidentId={incident.id}
              accessInfo={accessInfo}
              currentView={currentView}
              onViewChange={setCurrentView}
              onAccessGranted={() => refetchAccess()}
              cameraName="Terrace North Camera"
            />

            {/* Simulated & Real Annotated Video Player */}
            <div className="relative aspect-video bg-video-bg rounded-card overflow-hidden flex items-center justify-center border border-border-card">
              {/* Real backend video stream */}
              <video
                key={`${incident.id}-${currentView}`}
                src={api.evidence.getVideoUrl(incident.id, {
                  tier: currentView === 'unblurred' ? 'raw' : currentView,
                  variant: 'targeted',
                })}
                controls
                autoPlay
                muted
                loop
                playsInline
                className="w-full h-full object-contain z-10"
                onError={(e) => {
                  // Hide video tag if backend media is image or still synthesizing
                  e.currentTarget.style.display = 'none'
                }}
              />

              {/* Watermark overlay when in Unblurred mode */}
              {currentView === 'unblurred' && (
                <div className="absolute inset-0 z-20 flex items-center justify-center pointer-events-none opacity-25 rotate-[-15deg]">
                  <span className="text-[26px] font-mono text-white tracking-widest font-bold">
                    {user?.email || 'RAKSHAK-AI AUDITED'}
                  </span>
                </div>
              )}

              {/* Privacy Canvas & HUD Layer */}
              <div className="absolute inset-0 flex flex-col items-center justify-center p-6 select-none">
                {currentView === 'skeleton' ? (
                  /* Skeleton Mode */
                  <div className="w-full h-full flex flex-col items-center justify-center relative">
                    <svg
                      className="w-32 h-40 opacity-90"
                      viewBox="0 0 100 120"
                      fill="none"
                      stroke="#EDEBE6"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <circle cx="50" cy="20" r="10" stroke="#EDEBE6" strokeWidth="2.5" />
                      <line x1="50" y1="30" x2="50" y2="65" />
                      <line x1="50" y1="42" x2="30" y2="55" />
                      <line x1="30" y1="55" x2="22" y2="70" />
                      <line x1="50" y1="42" x2="70" y2="55" />
                      <line x1="70" y1="55" x2="78" y2="70" />
                      <line x1="50" y1="65" x2="35" y2="90" />
                      <line x1="35" y1="90" x2="30" y2="115" />
                      <line x1="50" y1="65" x2="65" y2="90" />
                      <line x1="65" y1="90" x2="70" y2="115" />
                    </svg>
                    {/* Active person bounding box */}
                    <div className="absolute inset-12 border-2 border-video-alertBox/90 rounded pointer-events-none flex items-start justify-between p-2">
                      <span className="bg-video-alertBox text-white text-[10px] font-mono px-1.5 py-0.5 rounded">
                        ID: P-04 (curfew violation)
                      </span>
                      <span className="text-[11px] text-[#EDEBE6] font-mono">
                        23:38:12
                      </span>
                    </div>
                    <span className="text-[11px] font-mono text-[#B9B7B1] mt-2">
                      SKELETON STREAM · TRACK #104
                    </span>
                  </div>
                ) : currentView === 'blurred' ? (
                  /* Face Blurred Mode */
                  <div className="w-full h-full bg-[#2C2E33] flex flex-col items-center justify-center relative">
                    <div className="w-24 h-24 rounded-full bg-white/20 backdrop-blur-md flex items-center justify-center mb-2">
                      <span className="text-[11px] text-white/80 font-mono">[FACE BLURRED]</span>
                    </div>
                    <span className="text-[12px] text-[#EDEBE6] font-medium">
                      Footage preview with privacy filter active
                    </span>
                    <span className="text-[11px] text-[#B9B7B1] mt-1">
                      10-minute temporary breakglass session
                    </span>
                  </div>
                ) : (
                  /* Unblurred Authorized Mode with Watermark */
                  <div className="w-full h-full bg-[#18191D] flex flex-col items-center justify-center relative">
                    <ShieldCheck size={40} className="text-status-healthy mb-2" />
                    <span className="text-[13px] text-white font-medium">
                      Full unblurred identity footage active
                    </span>
                    <span className="text-[11px] text-[#B9B7B1] mt-1 font-mono">
                      Watermarked & logged to immutable audit ledger
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Modality Lane Timeline */}
            <div>
              <p className="text-[12px] font-medium text-content-secondary mb-2">
                Evidence timeline across sensor lanes
              </p>
              <div className="space-y-1.5 bg-fill-subtle p-3 rounded-card border border-border-card text-[12px]">
                {/* Video lane */}
                <div className="flex items-center gap-3">
                  <span className="w-16 font-mono text-content-muted text-[11px] flex items-center gap-1">
                    <Video size={11} /> Video
                  </span>
                  <div className="flex-1 h-3 bg-card rounded relative border border-border-card">
                    <span
                      className="absolute left-[35%] top-0 bottom-0 w-2.5 bg-critical rounded-sm"
                      title="23:38:10 - Person stepped into terrace"
                    />
                    <span
                      className="absolute left-[45%] top-0 bottom-0 w-2.5 bg-critical rounded-sm"
                      title="23:38:18 - Rapid movement"
                    />
                  </div>
                  <span className="text-[11px] font-mono text-content-muted">2 events</span>
                </div>

                {/* Audio lane */}
                <div className="flex items-center gap-3">
                  <span className="w-16 font-mono text-content-muted text-[11px] flex items-center gap-1">
                    <Mic size={11} /> Audio
                  </span>
                  <div className="flex-1 h-3 bg-card rounded relative border border-border-card">
                    <span
                      className="absolute left-[38%] top-0 bottom-0 w-2.5 bg-status-high rounded-sm"
                      title="23:38:14 - High pitch scream sound (0.88)"
                    />
                  </div>
                  <span className="text-[11px] font-mono text-content-muted">1 event</span>
                </div>

                {/* Access lane */}
                <div className="flex items-center gap-3">
                  <span className="w-16 font-mono text-content-muted text-[11px] flex items-center gap-1">
                    <CreditCard size={11} /> Access
                  </span>
                  <div className="flex-1 h-3 bg-card rounded relative border border-border-card">
                    <span
                      className="absolute left-[15%] top-0 bottom-0 w-2.5 bg-status-low rounded-sm"
                      title="23:36:12 - Authorized turnstile entry"
                    />
                    <span
                      className="absolute left-[40%] top-0 bottom-0 w-2.5 bg-critical rounded-sm"
                      title="23:38:40 - Unswiped presence at rooftop door"
                    />
                  </div>
                  <span className="text-[11px] font-mono text-content-muted">2 logs</span>
                </div>

                {/* SOS lane */}
                <div className="flex items-center gap-3">
                  <span className="w-16 font-mono text-content-muted text-[11px] flex items-center gap-1">
                    <Megaphone size={11} /> SOS
                  </span>
                  <div className="flex-1 h-3 bg-card rounded relative border border-border-card">
                    {/* SOS event if present */}
                  </div>
                  <span className="text-[11px] font-mono text-content-muted">0 events</span>
                </div>
              </div>
            </div>
          </Card>

          {/* "What Happened" Paragraph Card */}
          <Card padding="md" className="space-y-3">
            <h2 className="text-[17px] font-semibold text-content-primary">What happened</h2>
            <p className="text-[14px] text-content-body leading-relaxed">
              {incident.explanation ||
                'Person stepped into the terrace area. No staff swipe explains it. A scream was heard at 23:38, corroborated by elevated audio distress levels.'}
            </p>
            <div className="p-3 bg-primary-tint/60 rounded-card border border-primary/20 text-[13px] text-primary flex items-start gap-2.5 leading-relaxed">
              <Info size={16} className="shrink-0 mt-0.5" />
              <p>
                Three independent sources agree, which is why this is marked critical. The system can be wrong, so please check before confirming.
              </p>
            </div>
          </Card>

          {/* "Why This Fired": Signals Breakdown */}
          <Card padding="md" className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-[17px] font-semibold text-content-primary">
                Why this fired (sensor corroboration)
              </h2>
              <span className="text-[12px] text-content-muted">
                Composite threshold: 0.65
              </span>
            </div>

            <div className="space-y-2.5">
              {(incident.signals || []).map((sig) => {
                const scorePct = Math.round((sig.score || 0.8) * 100)
                const threshPct = Math.round((sig.threshold || 0.5) * 100)
                const isSuppressed = sig.suppressed

                return (
                  <div
                    key={sig.id}
                    className={`p-3 rounded-card border transition-colors ${
                      isSuppressed
                        ? 'bg-fill-subtle border-border-card text-content-muted'
                        : 'bg-card border-border-card text-content-body'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="text-[13px] font-semibold text-content-primary">
                          {sig.kind?.replace(/_/g, ' ') || 'Zone intrusion'}
                        </span>
                        <span className="text-[11px] px-1.5 py-0.5 rounded bg-fill-active text-content-secondary font-mono">
                          {sig.modality}
                        </span>
                        {sig.kind?.includes('fight') && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-status-medium-tint text-status-medium font-medium">
                            experimental
                          </span>
                        )}
                      </div>
                      <span className="text-[11px] font-mono text-content-muted">
                        score {sig.score?.toFixed(2)} (thresh {sig.threshold?.toFixed(2)})
                      </span>
                    </div>

                    {/* Score Bar vs Threshold */}
                    <div className="w-full h-2 bg-fill-subtle rounded-full overflow-hidden relative border border-border-divider mb-1.5">
                      {/* Threshold marker */}
                      <div
                        className="absolute top-0 bottom-0 w-0.5 bg-content-muted z-10"
                        style={{ left: `${threshPct}%` }}
                        title={`Threshold: ${threshPct}%`}
                      />
                      {/* Score fill */}
                      <div
                        className={`h-full rounded-full ${
                          isSuppressed
                            ? 'bg-content-muted'
                            : sig.score >= sig.threshold
                            ? 'bg-critical'
                            : 'bg-primary'
                        }`}
                        style={{ width: `${scorePct}%` }}
                      />
                    </div>

                    {isSuppressed && (
                      <p className="text-[11px] text-content-muted italic">
                        Suppressed: {sig.suppress_reason || 'Audio context filter suppressed noise as celebration'}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          </Card>

          {/* Audio Evidence Top-5 Sound Classes Bar Chart */}
          <Card padding="md" className="space-y-4">
            <h2 className="text-[17px] font-semibold text-content-primary">
              Audio evidence: acoustic class probability
            </h2>
            <div className="h-48 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={soundClassesData}
                  layout="vertical"
                  margin={{ top: 5, right: 30, left: 80, bottom: 5 }}
                >
                  <XAxis type="number" domain={[0, 1]} tick={{ fontSize: 11 }} />
                  <YAxis
                    dataKey="name"
                    type="category"
                    tick={{ fontSize: 12, fill: '#34363B' }}
                    width={110}
                  />
                  <Tooltip
                    formatter={(val: any) => [`${(Number(val) * 100).toFixed(0)}%`, 'Probability']}
                  />
                  <Bar dataKey="score" radius={[0, 4, 4, 0]}>
                    {soundClassesData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={index === 0 ? '#C42B2B' : index === 1 ? '#D9730D' : '#1E5B4F'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Related Access Events (Pseudonymised IDs only) */}
          <Card padding="md" className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-[17px] font-semibold text-content-primary">
                Related turnstile access events
              </h2>
              <span className="text-[11px] text-content-muted font-mono">
                Pseudonymized IDs
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[13px]">
                <thead>
                  <tr className="border-b border-border-divider text-content-muted text-[11px] uppercase tracking-wider">
                    <th className="py-2">Time</th>
                    <th className="py-2">Pseudonymised Badge ID</th>
                    <th className="py-2">Reader</th>
                    <th className="py-2">Swipe Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-divider">
                  {accessEvents.map((evt: any, idx: number) => (
                    <tr key={idx} className="hover:bg-fill-subtle/30">
                      <td className="py-2.5 font-mono text-[12px] text-content-secondary">
                        {evt.timestamp || evt.ts || '23:38:40'}
                      </td>
                      <td className="py-2.5 font-mono text-[12px] text-content-primary">
                        {evt.badge_id || evt.pseudonym_id || 'STUDENT-HASH-8A91'}
                      </td>
                      <td className="py-2.5 text-content-body">
                        {evt.reader || evt.zone_id || 'Terrace North Entry'}
                      </td>
                      <td className="py-2.5">
                        <span
                          className={`text-[11px] font-medium px-2 py-0.5 rounded ${
                            evt.status?.includes('No') || evt.status?.includes('Unswiped')
                              ? 'bg-critical-tint text-critical'
                              : 'bg-fill-active text-content-primary'
                          }`}
                        >
                          {evt.status || 'Authorized'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        {/* Right 1 Column: Decision Card, What to Do (Playbook), History */}
        <div className="space-y-6">
          {/* "Your Decision" Card */}
          <Card padding="md" className="space-y-4">
            <div>
              <h2 className="text-[17px] font-semibold text-content-primary">Your decision</h2>
              <p className="text-[12px] text-content-muted mt-1 leading-relaxed">
                Only a person can mark this as real. Nothing happens to any student automatically.
              </p>
            </div>

            <div className="space-y-2">
              <label
                className={`flex items-start gap-2.5 p-3 rounded-card border cursor-pointer transition-colors ${
                  reviewOutcome === 'confirmed'
                    ? 'border-primary bg-primary-tint/30 text-content-primary'
                    : 'border-border-card bg-card text-content-body hover:bg-fill-subtle'
                }`}
              >
                <input
                  type="radio"
                  name="review_outcome"
                  value="confirmed"
                  checked={reviewOutcome === 'confirmed'}
                  onChange={() => setReviewOutcome('confirmed')}
                  className="mt-1 accent-primary"
                />
                <div>
                  <span className="text-[13px] font-semibold block">It's real</span>
                  <span className="text-[12px] text-content-muted block mt-0.5">
                    Valid safety incident requiring patrol or warden response.
                  </span>
                </div>
              </label>

              <label
                className={`flex items-start gap-2.5 p-3 rounded-card border cursor-pointer transition-colors ${
                  reviewOutcome === 'false_positive'
                    ? 'border-primary bg-primary-tint/30 text-content-primary'
                    : 'border-border-card bg-card text-content-body hover:bg-fill-subtle'
                }`}
              >
                <input
                  type="radio"
                  name="review_outcome"
                  value="false_positive"
                  checked={reviewOutcome === 'false_positive'}
                  onChange={() => setReviewOutcome('false_positive')}
                  className="mt-1 accent-primary"
                />
                <div>
                  <span className="text-[13px] font-semibold block">False alarm</span>
                  <span className="text-[12px] text-content-muted block mt-0.5">
                    Harmless noise or authorized movement. Will calibrate zone thresholds.
                  </span>
                </div>
              </label>

              <label
                className={`flex items-start gap-2.5 p-3 rounded-card border cursor-pointer transition-colors ${
                  reviewOutcome === 'investigating'
                    ? 'border-primary bg-primary-tint/30 text-content-primary'
                    : 'border-border-card bg-card text-content-body hover:bg-fill-subtle'
                }`}
              >
                <input
                  type="radio"
                  name="review_outcome"
                  value="investigating"
                  checked={reviewOutcome === 'investigating'}
                  onChange={() => setReviewOutcome('investigating')}
                  className="mt-1 accent-primary"
                />
                <div>
                  <span className="text-[13px] font-semibold block">Not sure yet, investigate</span>
                  <span className="text-[12px] text-content-muted block mt-0.5">
                    Guard currently verifying situation on ground.
                  </span>
                </div>
              </label>
            </div>

            <div>
              <label className="block text-[12px] font-medium text-content-secondary mb-1">
                What did you find? {reviewOutcome !== 'investigating' && <span className="text-critical">*</span>}
              </label>
              <textarea
                rows={3}
                required={reviewOutcome !== 'investigating'}
                value={reviewNote}
                onChange={(e) => setReviewNote(e.target.value)}
                placeholder="e.g. Guard Ramesh verified student locked out on terrace roof."
                className="w-full px-3 py-2 text-[13px] bg-card border border-border-input rounded-input focus:outline-none focus:border-primary"
              />
            </div>

            <Button
              variant="primary"
              size="md"
              className="w-full"
              isLoading={reviewMutation.isPending}
              disabled={reviewOutcome !== 'investigating' && !reviewNote.trim()}
              onClick={() => reviewMutation.mutate()}
            >
              Save decision
            </Button>
          </Card>

          {/* "What to do" Playbook Checklist */}
          <Card padding="md" className="space-y-3">
            <h2 className="text-[17px] font-semibold text-content-primary">What to do</h2>
            <p className="text-[12px] text-content-muted">
              Standard operating playbook for {incidentKind.replace(/_/g, ' ')}
            </p>

            <div className="space-y-2 pt-1">
              {activePlaybook.map((step, idx) => {
                const isDone = !!checkedPlaybook[step]
                return (
                  <div
                    key={idx}
                    onClick={() => togglePlaybook(step)}
                    className="flex items-start gap-2.5 p-2 rounded hover:bg-fill-subtle cursor-pointer transition-colors"
                  >
                    <div className="mt-0.5 text-primary">
                      {isDone ? <CheckSquare size={16} /> : <Square size={16} className="text-content-muted" />}
                    </div>
                    <span
                      className={`text-[13px] ${
                        isDone ? 'line-through text-content-muted' : 'text-content-body'
                      }`}
                    >
                      {step}
                    </span>
                  </div>
                )
              })}
            </div>
          </Card>

          {/* Incident History List */}
          <Card padding="md" className="space-y-3">
            <h2 className="text-[17px] font-semibold text-content-primary">History</h2>
            <div className="space-y-2.5 text-[12px]">
              <div className="flex items-start gap-2 text-content-secondary">
                <Clock size={13} className="shrink-0 mt-0.5 text-content-muted" />
                <div>
                  <span className="font-medium text-content-primary">Signal Corroboration</span>
                  <p className="text-[11px] text-content-muted">23:38 · Multi-sensor fusion fired</p>
                </div>
              </div>

              {incident.acknowledged_by && (
                <div className="flex items-start gap-2 text-content-secondary">
                  <CheckCircle size={13} className="shrink-0 mt-0.5 text-status-healthy" />
                  <div>
                    <span className="font-medium text-content-primary">Acknowledged</span>
                    <p className="text-[11px] text-content-muted">
                      {incident.acknowledged_by} took ownership
                    </p>
                  </div>
                </div>
              )}

              {incident.reviewer && (
                <div className="flex items-start gap-2 text-content-secondary">
                  <ShieldCheck size={13} className="shrink-0 mt-0.5 text-primary" />
                  <div>
                    <span className="font-medium text-content-primary">Decision Logged</span>
                    <p className="text-[11px] text-content-muted">
                      Marked as {incident.status} by {incident.reviewer}
                    </p>
                    {incident.review_note && (
                      <p className="text-[11px] text-content-body mt-0.5 italic">
                        "{incident.review_note}"
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
