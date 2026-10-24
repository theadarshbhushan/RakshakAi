import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Video,
  Mic,
  CreditCard,
  Megaphone,
  Filter,
  ArrowRight,
  ShieldAlert,
  ChevronLeft,
  ChevronRight,
  Search,
} from 'lucide-react'
import { api } from '@/api/client'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { SeverityDot } from '@/components/ui/SeverityDot'
import { Countdown } from '@/components/ui/Countdown'
import { EmptyState } from '@/components/ui/EmptyState'
import type { Incident } from '@/api/types'

export const IncidentQueuePage: React.FC = () => {
  const navigate = useNavigate()
  const [severityFilter, setSeverityFilter] = useState<string>('')
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [zoneFilter, setZoneFilter] = useState<string>('')
  const [page, setPage] = useState<number>(0)
  const pageSize = 15

  const { data, isLoading } = useQuery({
    queryKey: ['incidents', 'queue', severityFilter, statusFilter, zoneFilter, page],
    queryFn: () =>
      api.incidents.list({
        severity: severityFilter || undefined,
        status: statusFilter || undefined,
        zone: zoneFilter || undefined,
        skip: page * pageSize,
        limit: pageSize,
      }),
    refetchInterval: 10000,
  })

  const incidents = data?.items || []
  const total = data?.total || 0
  const totalPages = Math.ceil(total / pageSize)

  const getModalityIcons = (modalities: string[] = []) => {
    return (
      <div className="flex items-center gap-1">
        {modalities.includes('video') && (
          <span title="Video camera detection" className="p-1 rounded bg-fill-subtle text-content-secondary">
            <Video size={13} />
          </span>
        )}
        {modalities.includes('audio') && (
          <span title="Audio acoustic detection" className="p-1 rounded bg-fill-subtle text-content-secondary">
            <Mic size={13} />
          </span>
        )}
        {modalities.includes('access') && (
          <span title="Turnstile swipe card log" className="p-1 rounded bg-fill-subtle text-content-secondary">
            <CreditCard size={13} />
          </span>
        )}
        {modalities.includes('sos') && (
          <span title="Student SOS report" className="p-1 rounded bg-critical-tint text-critical">
            <Megaphone size={13} />
          </span>
        )}
      </div>
    )
  }

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

  const formatStatus = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'new':
      case 'open':
        return <span className="text-[12px] text-critical font-medium">Needs decision</span>
      case 'acknowledged':
        return <span className="text-[12px] text-content-primary font-medium">Ramesh on it</span>
      case 'investigating':
        return <span className="text-[12px] text-status-medium font-medium">Investigating</span>
      case 'confirmed':
        return <span className="text-[12px] text-status-healthy font-medium">Confirmed real</span>
      case 'false_alarm':
      case 'false_positive':
        return <span className="text-[12px] text-content-muted font-medium">False alarm</span>
      default:
        return <span className="text-[12px] text-content-secondary">{status}</span>
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-bold text-content-primary">Incidents</h1>
          <p className="text-[14px] text-content-secondary mt-0.5">
            Human-reviewed safety alerts fused across multi-sensor signals.
          </p>
        </div>
      </div>

      {/* Filters Bar */}
      <Card padding="sm" className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-[13px] text-content-muted pl-1">
          <Filter size={15} />
          <span>Filters:</span>
        </div>

        {/* Severity */}
        <select
          value={severityFilter}
          onChange={(e) => {
            setSeverityFilter(e.target.value)
            setPage(0)
          }}
          className="text-[13px] px-2.5 py-1.5 bg-card border border-border-input rounded-input focus:outline-none focus:border-primary text-content-body"
        >
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>

        {/* Status */}
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value)
            setPage(0)
          }}
          className="text-[13px] px-2.5 py-1.5 bg-card border border-border-input rounded-input focus:outline-none focus:border-primary text-content-body"
        >
          <option value="">All statuses</option>
          <option value="new">Needs decision (open)</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="investigating">Investigating</option>
          <option value="confirmed">Confirmed real</option>
          <option value="false_alarm">False alarm</option>
        </select>

        {/* Zone */}
        <select
          value={zoneFilter}
          onChange={(e) => {
            setZoneFilter(e.target.value)
            setPage(0)
          }}
          className="text-[13px] px-2.5 py-1.5 bg-card border border-border-input rounded-input focus:outline-none focus:border-primary text-content-body"
        >
          <option value="">All zones</option>
          <option value="terrace">Terrace</option>
          <option value="common_room">Common Room</option>
          <option value="block_b_entry">Block B Entry</option>
          <option value="corridor_2f">Corridor 2F</option>
          <option value="server_room">Server Room</option>
          <option value="back_wall">Back Wall</option>
        </select>

        {(severityFilter || statusFilter || zoneFilter) && (
          <button
            onClick={() => {
              setSeverityFilter('')
              setStatusFilter('')
              setZoneFilter('')
              setPage(0)
            }}
            className="text-[12px] text-content-muted hover:text-content-primary underline ml-auto mr-1"
          >
            Clear filters
          </button>
        )}
      </Card>

      {/* Table Box (Horizontal scrollable box for phone width responsiveness) */}
      <Card padding="none" className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-border-divider bg-fill-subtle/50 text-[12px] font-semibold text-content-secondary uppercase tracking-wider">
                <th className="py-3 px-4">Severity</th>
                <th className="py-3 px-4">Zone</th>
                <th className="py-3 px-4">Sensors</th>
                <th className="py-3 px-4">Corroboration</th>
                <th className="py-3 px-4 min-w-[260px]">What happened</th>
                <th className="py-3 px-4">Time</th>
                <th className="py-3 px-4">Status / SLA</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-divider text-[13px]">
              {incidents.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12">
                    <EmptyState
                      title="No incidents match your filter"
                      description="Try adjusting your filters or play a test scenario from the Live Monitor."
                    />
                  </td>
                </tr>
              ) : (
                incidents.map((inc) => {
                  const isUrgent =
                    (inc.severity === 'critical' || inc.severity === 'high') &&
                    (!inc.status || inc.status === 'new' || inc.status === 'open')
                  const scorePct = Math.round((inc.composite_score || 0.7) * 100)

                  return (
                    <tr
                      key={inc.id}
                      className="hover:bg-fill-subtle/40 transition-colors group cursor-pointer"
                      onClick={() => navigate(`/app/incidents/${inc.id}`)}
                    >
                      {/* Severity */}
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        <div className="flex items-center gap-1.5">
                          <SeverityDot severity={inc.severity} pulse={isUrgent} />
                          {inc.escalated && (
                            <span className="text-[10px] bg-critical-tint text-critical font-medium px-1.5 py-0.5 rounded ml-1">
                              escalated
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Zone */}
                      <td className="py-3.5 px-4 font-medium text-content-primary whitespace-nowrap">
                        {inc.zone_id ? inc.zone_id.replace(/_/g, ' ') : 'Zone'}
                      </td>

                      {/* Sensor Modality Icons */}
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        {getModalityIcons(inc.modalities || ['video', 'audio'])}
                      </td>

                      {/* Composite score bar */}
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 bg-fill-active rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                inc.severity === 'critical'
                                  ? 'bg-critical'
                                  : inc.severity === 'high'
                                  ? 'bg-status-high'
                                  : 'bg-primary'
                              }`}
                              style={{ width: `${scorePct}%` }}
                            />
                          </div>
                          <span className="font-mono text-[11px] text-content-muted">
                            {scorePct}%
                          </span>
                        </div>
                      </td>

                      {/* Plain Language Explanation */}
                      <td className="py-3.5 px-4 text-content-body max-w-sm">
                        <p className="line-clamp-2 leading-relaxed">
                          {(inc as any).title_human || inc.explanation || 'Corroborated safety incident'}
                        </p>
                      </td>

                      {/* Time */}
                      <td className="py-3.5 px-4 whitespace-nowrap font-mono text-[12px] text-content-secondary">
                        {formatTimeStr(inc.created_ts)}
                      </td>

                      {/* Status & SLA Countdown */}
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        <div>
                          {formatStatus(inc.status)}
                          {isUrgent && (
                            <div className="text-[11px] font-mono mt-0.5">
                              <Countdown
                                secondsLeft={(inc as any).sla_countdown_seconds || 42}
                                prefix="alert in "
                              />
                            </div>
                          )}
                        </div>
                      </td>

                      {/* Action */}
                      <td className="py-3.5 px-4 text-right whitespace-nowrap">
                        <Link
                          to={`/incidents/${inc.id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 text-[13px] font-medium text-primary hover:text-primary-hover"
                        >
                          <span>Review</span>
                          <ArrowRight size={14} />
                        </Link>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        {totalPages > 1 && (
          <div className="p-4 border-t border-border-divider flex items-center justify-between text-[13px] text-content-secondary">
            <span>
              Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, total)} of {total} incidents
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                icon={<ChevronLeft size={14} />}
              >
                Previous
              </Button>
              <span className="font-mono text-[12px]">
                {page + 1} / {totalPages}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => p + 1)}
                icon={<ChevronRight size={14} />}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
