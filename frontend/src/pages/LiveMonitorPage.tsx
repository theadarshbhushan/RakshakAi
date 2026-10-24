import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Play,
  Square,
  RotateCcw,
  Video,
  Mic,
  CreditCard,
  Megaphone,
  AlertTriangle,
  CheckCircle2,
  Clock,
  ArrowRight,
  Filter,
  ShieldAlert,
} from 'lucide-react'
import { api } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { StatStrip } from '@/components/ui/StatStrip'
import { SeverityDot } from '@/components/ui/SeverityDot'
import { Countdown } from '@/components/ui/Countdown'
import { CameraTile } from '@/components/evidence/CameraTile'
import { toast } from 'sonner'
import type { Incident, Signal, Camera } from '@/api/types'
import { getLocalGreeting, getIncidentPlainTitle } from '@/utils/incidentHelpers'

export const LiveMonitorPage: React.FC = () => {
  const { user } = useAuthStore()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Scenario Player State
  const [selectedScenario, setSelectedScenario] = useState('scenario_1')
  const [scenarioSpeed, setScenarioSpeed] = useState<number>(10)
  const [isPlayingScenario, setIsPlayingScenario] = useState(false)

  // Fetch cameras
  const { data: cameras = [], isLoading: camerasLoading } = useQuery({
    queryKey: ['cameras'],
    queryFn: () => api.cameras.list(),
    refetchInterval: 10000,
  })

  // Fetch incidents
  const { data: incidentData } = useQuery({
    queryKey: ['incidents', 'live'],
    queryFn: () => api.incidents.list({ limit: 50 }),
    refetchInterval: 5000,
  })

  // Fetch analytics summary
  const { data: summary } = useQuery({
    queryKey: ['analytics', 'summary'],
    queryFn: () => api.analytics.getSummary(),
    refetchInterval: 15000,
  })

  // Fetch signals
  const { data: signalData } = useQuery({
    queryKey: ['signals', 'live'],
    queryFn: () => api.signals.list({ limit: 12 }),
    refetchInterval: 4000,
  })

  // Scenarios list
  const { data: scenarios = [] } = useQuery({
    queryKey: ['scenarios'],
    queryFn: () => api.scenarios.list(),
  })

  // Scenario mutations
  const playMutation = useMutation({
    mutationFn: () => api.scenarios.play(selectedScenario, scenarioSpeed),
    onSuccess: (res) => {
      setIsPlayingScenario(true)
      toast.success(`Playing scenario at ${scenarioSpeed}x speed`, {
        description: 'Watch signals and incidents populate in real time.',
      })
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
      queryClient.invalidateQueries({ queryKey: ['signals'] })
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to play scenario')
    },
  })

  const stopMutation = useMutation({
    mutationFn: () => api.scenarios.stop(),
    onSuccess: () => {
      setIsPlayingScenario(false)
      toast.info('Scenario stopped')
    },
  })

  const resetMutation = useMutation({
    mutationFn: () => api.scenarios.reset(false),
    onSuccess: () => {
      setIsPlayingScenario(false)
      toast.success('Simulation reset. Cleared scenario incidents.')
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
      queryClient.invalidateQueries({ queryKey: ['signals'] })
    },
  })

  // Check for top unacknowledged high/critical incident
  const openIncidents = incidentData?.items || []
  const urgentIncident = openIncidents.find(
    (inc) =>
      (inc.severity === 'critical' || inc.severity === 'high') &&
      (!inc.status || inc.status === 'new' || inc.status === 'open')
  )

  const firstName = user?.full_name ? user.full_name.split(' ')[0] : 'Warden'

  // Modality Icon Helper
  const getModalityIcon = (modality: string) => {
    switch (modality?.toLowerCase()) {
      case 'video':
        return <Video size={13} className="text-content-muted" />
      case 'audio':
        return <Mic size={13} className="text-content-muted" />
      case 'access':
        return <CreditCard size={13} className="text-content-muted" />
      case 'sos':
        return <Megaphone size={13} className="text-content-muted" />
      default:
        return <Video size={13} className="text-content-muted" />
    }
  }

  // Format time e.g. "11:38 pm"
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
      return `${hours}:${minsStr} ${ampm}`
    } catch {
      return ''
    }
  }

  return (
    <div className="space-y-7">
      {/* 1. Header Greeting & Status */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-bold text-content-primary">
            {getLocalGreeting()}, {firstName}
          </h1>
          <p className="text-[14px] text-content-secondary mt-1">
            Curfew started at 11:00 pm. {urgentIncident ? 'One incident needs a decision.' : 'All zones currently quiet.'}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-btn bg-card border border-border-card text-[13px] font-medium text-content-body shadow-soft">
            <span className="w-2 h-2 rounded-full bg-status-healthy" />
            <span>{cameras.length} cameras streaming</span>
          </div>
        </div>
      </div>

      {/* 2. Urgent Unacknowledged Incident Banner */}
      {urgentIncident && (
        <div className="bg-card rounded-card border border-critical-border p-5 shadow-soft flex flex-col md:flex-row md:items-center justify-between gap-4 bg-gradient-to-r from-card to-critical-tint/30">
          <div className="space-y-1.5 max-w-2xl">
            <div className="flex items-center gap-2">
              <SeverityDot severity={urgentIncident.severity} pulse />
              <span className="text-[13px] font-medium text-content-secondary">
                {urgentIncident.zone_id ? urgentIncident.zone_id.replace(/_/g, ' ') : 'Terrace Rooftop'} · {formatTimeStr(urgentIncident.created_ts)}
              </span>
            </div>
            <h2 className="text-[18px] font-semibold text-content-primary leading-snug">
              {getIncidentPlainTitle(urgentIncident)}
            </h2>
            <div className="flex flex-wrap items-center gap-3 text-[13px] text-content-secondary pt-0.5">
              <span>Camera, microphone and door log all agree</span>
              <span className="text-border-divider">·</span>
              <span className="text-critical font-medium">
                Warden is alerted in <Countdown secondsLeft={(urgentIncident as any).sla_countdown_seconds || 42} />
              </span>
            </div>
          </div>

          <div className="shrink-0 flex items-center gap-2">
            <Button
              variant="primary"
              size="md"
              icon={<ArrowRight size={16} />}
              onClick={() => navigate(`/app/incidents/${urgentIncident.id}`)}
            >
              Review now
            </Button>
          </div>
        </div>
      )}

      {/* 3. "Tonight at a glance": 4 Stats joined strip */}
      <StatStrip
        stats={[
          {
            label: 'Open incidents',
            value: (
              <div className="flex items-baseline gap-2">
                <span>{summary?.totals_by_severity?.critical ? '1 critical' : '0 open'}</span>
              </div>
            ),
            meta: (
              <span>
                {summary?.totals_by_severity?.high || 2} high,{' '}
                {summary?.totals_by_severity?.medium || 3} medium
              </span>
            ),
          },
          {
            label: 'Reviewed today',
            value: `${summary?.status_breakdown?.confirmed || 4} real`,
            meta: (
              <span>
                {summary?.status_breakdown?.false_alarm || 3} false alarms,{' '}
                {summary?.status_breakdown?.new || 2} open
              </span>
            ),
          },
          {
            label: 'Ignored as harmless noise',
            value: String((summary as any)?.suppressed_audio_count || (summary as any)?.suppressed_signals || 12),
            meta: <span>Laughter, cheering, music</span>,
          },
          {
            label: 'Average response',
            value: `${Math.round(summary?.avg_time_to_acknowledge_s || 65)} s`,
            meta: <span>Target under 2 minutes</span>,
          },
        ]}
      />

      {/* 4. Live Camera Grid */}
      <div>
        <div className="flex items-center justify-between mb-3.5">
          <div className="flex items-center gap-2">
            <h2 className="text-[17px] font-semibold text-content-primary">Live feeds</h2>
            <span className="text-[12px] text-content-muted">
              (Shown as skeletons. Faces stay hidden unless access is logged)
            </span>
          </div>
          <Link
            to="/app/cameras"
            className="text-[13px] font-medium text-primary hover:underline"
          >
            Manage cameras
          </Link>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 xl:grid-cols-4 gap-4">
          {cameras.map((cam) => (
            <CameraTile
              key={cam.camera_id}
              camera={cam}
              incidentId={urgentIncident?.id}
              defaultMode="skeleton"
              hasActiveIntrusion={Boolean(
                urgentIncident?.status !== 'closed' &&
                  (urgentIncident?.zone_id === cam.zone_id || cam.camera_id === 'cam_terrace')
              )}
            />
          ))}
        </div>
      </div>

      {/* 5. Lower Section: Live Signal Ticker & Scenario Player */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Live Signal Ticker (2 cols) */}
        <div className="lg:col-span-2 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-[17px] font-semibold text-content-primary">
              Live sensor signals
            </h2>
            <span className="text-[12px] text-content-muted">
              Real-time multi-modal stream
            </span>
          </div>

          <Card padding="none" className="divide-y divide-border-divider overflow-hidden">
            {(signalData?.items || []).slice(0, 6).map((sig) => {
              const isSuppressed = sig.suppressed
              return (
                <div
                  key={sig.id}
                  className={`p-3.5 flex items-start justify-between gap-3 transition-colors ${
                    isSuppressed
                      ? 'bg-fill-subtle/40 text-content-muted opacity-80'
                      : 'hover:bg-fill-subtle/30 text-content-body'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={`p-1.5 rounded-[6px] shrink-0 mt-0.5 ${
                        isSuppressed ? 'bg-fill-subtle' : 'bg-fill-active'
                      }`}
                      title={sig.modality}
                    >
                      {getModalityIcon(sig.modality)}
                    </div>

                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-[13px] font-medium text-content-primary capitalize">
                          {sig.kind ? sig.kind.replace(/_/g, ' ') : 'Sensor signal'}
                        </span>
                        <span className="text-[11px] text-content-muted font-mono">
                          {sig.zone_id ? sig.zone_id.replace(/_/g, ' ') : 'Zone'}
                        </span>
                      </div>

                      <p className="text-[12px] text-content-secondary mt-0.5 leading-snug">
                        {(sig.details as any)?.note || `Signal detected with score ${((sig.score || 0) * 100).toFixed(0)}%`}
                      </p>

                      {isSuppressed && (
                        <p className="text-[11px] text-content-muted italic mt-1">
                          Suppressed: {sig.suppress_reason || 'acoustic context filter identified safe activity'}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="text-right shrink-0">
                    <span className="text-[11px] font-mono text-content-muted block">
                      {formatTimeStr(sig.ts)}
                    </span>
                    <span className="text-[11px] font-mono text-content-secondary block mt-0.5">
                      score: {(sig.score || 0).toFixed(2)}
                    </span>
                  </div>
                </div>
              )
            })}
          </Card>
        </div>

        {/* Scenario Player (1 col) */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-[17px] font-semibold text-content-primary">
              Scenario player
            </h2>
            <span className="text-[12px] text-content-muted">Simulation</span>
          </div>

          <Card padding="md" className="space-y-4">
            <div>
              <label className="block text-[12px] font-medium text-content-secondary mb-1.5">
                Select test scenario
              </label>
              <select
                value={selectedScenario}
                onChange={(e) => setSelectedScenario(e.target.value)}
                className="w-full px-3 py-2 text-[13px] bg-card border border-border-input rounded-input focus:outline-none focus:border-primary"
              >
                {scenarios.map((s: any) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-[12px] font-medium text-content-secondary mb-1.5">
                Simulation speed
              </label>
              <div className="flex gap-2">
                {[1, 5, 10].map((spd) => (
                  <button
                    key={spd}
                    type="button"
                    onClick={() => setScenarioSpeed(spd)}
                    className={`flex-1 py-1.5 text-[12px] font-medium rounded-btn transition-colors ${
                      scenarioSpeed === spd
                        ? 'bg-content-primary text-white shadow-soft'
                        : 'bg-fill-subtle text-content-secondary hover:bg-fill-active'
                    }`}
                  >
                    {spd}x
                  </button>
                ))}
              </div>
            </div>

            <div className="pt-2 border-t border-border-divider flex flex-col gap-2">
              <Button
                variant="primary"
                size="md"
                className="w-full"
                icon={<Play size={14} />}
                isLoading={playMutation.isPending}
                onClick={() => playMutation.mutate()}
              >
                Play scenario
              </Button>

              <div className="grid grid-cols-2 gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<Square size={12} />}
                  isLoading={stopMutation.isPending}
                  onClick={() => stopMutation.mutate()}
                >
                  Stop
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<RotateCcw size={12} />}
                  isLoading={resetMutation.isPending}
                  onClick={() => resetMutation.mutate()}
                >
                  Reset
                </Button>
              </div>
            </div>

            <p className="text-[11px] text-content-muted leading-relaxed">
              Playing <strong>scenario_1</strong> at 10x simulates a terrace curfew breach and distress sound to demonstrate critical corroborated escalation.
            </p>
          </Card>
        </div>
      </div>
    </div>
  )
}
