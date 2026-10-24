import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Inbox,
  CheckCircle,
  XCircle,
  Clock,
  User,
  ShieldAlert,
  ArrowRight,
  AlertTriangle,
} from 'lucide-react'
import { api } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Modal } from '@/components/ui/Modal'
import { EmptyState } from '@/components/ui/EmptyState'
import { toast } from 'sonner'

export const ApprovalsPage: React.FC = () => {
  const queryClient = useQueryClient()
  const { user } = useAuthStore()
  const [filterTab, setFilterTab] = useState<'pending' | 'all'>('pending')

  // Decision Modal State
  const [selectedRequest, setSelectedRequest] = useState<any | null>(null)
  const [decisionType, setDecisionType] = useState<'approve' | 'deny'>('approve')
  const [decisionNotes, setDecisionNotes] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Fetch Identity Reveal requests
  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['approvals', filterTab],
    queryFn: () =>
      api.privacy.listIdentityReveals(filterTab === 'pending' ? 'pending' : undefined),
    refetchInterval: 10000,
  })

  // Approve Mutation
  const handleDecide = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedRequest) return
    setIsSubmitting(true)
    try {
      if (decisionType === 'approve') {
        await api.privacy.approveIdentityReveal(selectedRequest.id || selectedRequest.request_id, decisionNotes)
        toast.success('Identity reveal request approved. Unblurred access granted for 15 minutes.')
      } else {
        await api.privacy.denyIdentityReveal(selectedRequest.id || selectedRequest.request_id, decisionNotes)
        toast.info('Identity reveal request denied.')
      }
      setSelectedRequest(null)
      setDecisionNotes('')
      queryClient.invalidateQueries({ queryKey: ['approvals'] })
    } catch (err: any) {
      toast.error(err.message || 'Failed to record decision')
    } finally {
      setIsSubmitting(false)
    }
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-bold text-content-primary">Approvals Inbox</h1>
          <p className="text-[14px] text-content-secondary mt-0.5">
            Two-person identity reveal requests requiring administrative authorization.
          </p>
        </div>

        {/* Tab switch */}
        <div className="inline-flex items-center bg-fill-active p-1 rounded-[8px]">
          <button
            type="button"
            onClick={() => setFilterTab('pending')}
            className={`px-3 py-1.5 text-[12px] font-medium rounded-[6px] transition-all ${
              filterTab === 'pending'
                ? 'bg-card text-content-primary shadow-soft'
                : 'text-content-secondary hover:text-content-primary'
            }`}
          >
            Pending decisions
          </button>
          <button
            type="button"
            onClick={() => setFilterTab('all')}
            className={`px-3 py-1.5 text-[12px] font-medium rounded-[6px] transition-all ${
              filterTab === 'all'
                ? 'bg-card text-content-primary shadow-soft'
                : 'text-content-secondary hover:text-content-primary'
            }`}
          >
            All requests
          </button>
        </div>
      </div>

      {/* Info notice */}
      <div className="p-3.5 bg-primary-tint/50 border border-primary/20 rounded-card text-[13px] text-content-body flex items-start gap-2.5">
        <ShieldAlert size={16} className="text-primary shrink-0 mt-0.5" />
        <p>
          Students' privacy policy mandates <strong>two-person rule</strong>: an administrator or warden who requests unblurred face evidence cannot approve their own request. Another independent administrator or owner must review the justification.
        </p>
      </div>

      {/* Requests List */}
      <Card padding="none" className="overflow-hidden">
        {requests.length === 0 ? (
          <div className="p-12">
            <EmptyState
              title="No pending requests in your inbox"
              description="When a guard or warden requests an identity reveal for an eligible safety incident, it will appear here for your independent review."
              icon={<Inbox size={32} />}
            />
          </div>
        ) : (
          <div className="divide-y divide-border-divider">
            {requests.map((req: any) => {
              const isRequester = req.requested_by === user?.email || req.user_id === user?.id
              const isPending = req.status === 'pending'

              return (
                <div key={req.id || req.request_id} className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-fill-subtle/30 transition-colors">
                  <div className="space-y-1.5 max-w-2xl">
                    <div className="flex items-center gap-2">
                      <span className="text-[13px] font-semibold text-content-primary">
                        {req.requested_by_name || req.requested_by || 'Hostel Staff'}
                      </span>
                      <span className="text-[11px] text-content-muted">
                        requested identity reveal
                      </span>
                      <span className="text-border-divider">·</span>
                      <span className="text-[12px] font-mono text-content-muted">
                        {formatTimeStr(req.created_at)}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 text-[13px] text-content-secondary">
                      <span className="font-medium text-content-primary">
                        Zone: {req.zone_id ? req.zone_id.replace(/_/g, ' ') : 'Terrace Rooftop'}
                      </span>
                      {req.incident_id && (
                        <Link
                          to={`/incidents/${req.incident_id}`}
                          className="text-primary hover:underline font-mono text-[12px] flex items-center gap-0.5"
                        >
                          <span>(Incident #{req.incident_id.slice(-6)})</span>
                        </Link>
                      )}
                    </div>

                    <div className="p-2.5 rounded bg-fill-subtle border border-border-card text-[13px] text-content-body italic">
                      "{req.reason}"
                    </div>

                    {isRequester && isPending && (
                      <p className="text-[11px] text-status-medium font-medium">
                        You submitted this request. It requires another administrator's approval.
                      </p>
                    )}
                  </div>

                  <div className="shrink-0 flex items-center gap-2">
                    {isPending ? (
                      <>
                        <Button
                          variant="secondary"
                          size="sm"
                          icon={<XCircle size={14} className="text-critical" />}
                          disabled={isRequester}
                          onClick={() => {
                            setSelectedRequest(req)
                            setDecisionType('deny')
                          }}
                        >
                          Deny
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          icon={<CheckCircle size={14} />}
                          disabled={isRequester}
                          onClick={() => {
                            setSelectedRequest(req)
                            setDecisionType('approve')
                          }}
                        >
                          Approve
                        </Button>
                      </>
                    ) : (
                      <span
                        className={`text-[12px] font-medium px-2.5 py-1 rounded ${
                          req.status === 'approved'
                            ? 'bg-status-healthy-tint text-status-healthy'
                            : 'bg-critical-tint text-critical'
                        }`}
                      >
                        {req.status}
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Card>

      {/* Decision Modal */}
      <Modal
        isOpen={!!selectedRequest}
        onClose={() => setSelectedRequest(null)}
        title={decisionType === 'approve' ? 'Approve Identity Reveal' : 'Deny Identity Reveal'}
        description={`Incident in ${selectedRequest?.zone_id || 'zone'} requested by ${selectedRequest?.requested_by}`}
      >
        <form onSubmit={handleDecide} className="space-y-4">
          <div>
            <label className="block text-[13px] font-medium text-content-body mb-1">
              Decision notes (optional)
            </label>
            <textarea
              rows={3}
              value={decisionNotes}
              onChange={(e) => setDecisionNotes(e.target.value)}
              placeholder="e.g. Verified with perimeter warden. Face reveal approved for police export."
              className="w-full px-3 py-2 text-[13px] bg-card border border-border-input rounded-input"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setSelectedRequest(null)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant={decisionType === 'approve' ? 'primary' : 'danger'}
              isLoading={isSubmitting}
            >
              Confirm {decisionType}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
