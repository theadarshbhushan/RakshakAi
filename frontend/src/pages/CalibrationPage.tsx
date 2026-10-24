import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  RotateCcw,
  Gauge,
  TrendingUp,
  Sliders,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { api } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { toast } from 'sonner'

export const CalibrationPage: React.FC = () => {
  const queryClient = useQueryClient()
  const { user } = useAuthStore()
  const isOwnerOrAdmin = user?.role === 'owner' || user?.role === 'admin'

  const { data: calibrationData, isLoading } = useQuery({
    queryKey: ['calibration'],
    queryFn: () => api.calibration.getOverview(),
  })

  // Revert mutation
  const revertMutation = useMutation({
    mutationFn: (historyId: string) => api.calibration.revert(historyId),
    onSuccess: (res) => {
      toast.success(`Restored previous threshold: ${res.restored_threshold}`)
      queryClient.invalidateQueries({ queryKey: ['calibration'] })
      queryClient.invalidateQueries({ queryKey: ['rules'] })
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to revert threshold')
    },
  })

  // Sample historical data for line chart
  const trendData = [
    { date: '18 Oct', terrace_intrusion: 0.45, audio_distress: 0.30 },
    { date: '20 Oct', terrace_intrusion: 0.48, audio_distress: 0.32 },
    { date: '22 Oct', terrace_intrusion: 0.52, audio_distress: 0.35 },
    { date: '24 Oct', terrace_intrusion: 0.50, audio_distress: 0.35 },
  ]

  const historyItems = calibrationData?.history || [
    {
      id: 'calib_01',
      zone_id: 'common_room',
      detector: 'distress_audio',
      old_threshold: 0.30,
      new_threshold: 0.35,
      reason: 'Recalibrated after false alarm: loud cheering during cricket match in common room.',
      who: 'Chief Warden',
      when: '2026-10-24 20:45',
    },
    {
      id: 'calib_02',
      zone_id: 'terrace',
      detector: 'zone_intrusion',
      old_threshold: 0.45,
      new_threshold: 0.50,
      reason: 'Adjusted sensitivity for late night wind noise on terrace railing.',
      who: 'Administrator',
      when: '2026-10-22 14:10',
    },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-[26px] font-bold text-content-primary">Calibration</h1>
        <p className="text-[14px] text-content-secondary mt-0.5">
          Audit history of sensitivity recalibrations triggered by guard false alarm reviews.
        </p>
      </div>

      {/* Line Chart: Threshold Evolution */}
      <Card padding="md" className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-[17px] font-semibold text-content-primary">
              Threshold sensitivity trend (Past 7 Days)
            </h2>
            <p className="text-[12px] text-content-muted">
              Higher values reduce false alarms while maintaining curfew deterrence.
            </p>
          </div>
          <div className="flex items-center gap-3 text-[12px]">
            <span className="flex items-center gap-1.5 text-primary">
              <span className="w-2.5 h-2.5 rounded-full bg-primary" />
              Terrace Intrusion
            </span>
            <span className="flex items-center gap-1.5 text-status-high">
              <span className="w-2.5 h-2.5 rounded-full bg-status-high" />
              Audio Distress
            </span>
          </div>
        </div>

        <div className="h-56 w-full pt-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trendData} margin={{ top: 10, right: 30, left: 10, bottom: 5 }}>
              <XAxis dataKey="date" tick={{ fontSize: 12, fill: '#5C5F66' }} />
              <YAxis domain={[0.2, 0.7]} tick={{ fontSize: 12, fill: '#5C5F66' }} />
              <Tooltip formatter={(val: any) => [val, 'Threshold']} />
              <Line
                type="monotone"
                dataKey="terrace_intrusion"
                stroke="#1E5B4F"
                strokeWidth={2.5}
                dot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="audio_distress"
                stroke="#D9730D"
                strokeWidth={2.5}
                dot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Threshold History Table */}
      <Card padding="none" className="overflow-hidden">
        <div className="p-4 border-b border-border-divider bg-fill-subtle/50">
          <h2 className="text-[16px] font-semibold text-content-primary">
            Recalibration history ledger
          </h2>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-border-divider text-content-muted text-[11px] uppercase tracking-wider">
                <th className="py-3 px-4">Zone</th>
                <th className="py-3 px-4">Detector</th>
                <th className="py-3 px-4">Threshold Change</th>
                <th className="py-3 px-4 max-w-sm">Reason</th>
                <th className="py-3 px-4">Triggered By</th>
                <th className="py-3 px-4">Timestamp</th>
                {isOwnerOrAdmin && <th className="py-3 px-4 text-right">Action</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border-divider">
              {historyItems.map((item: any) => (
                <tr key={item.id} className="hover:bg-fill-subtle/30">
                  <td className="py-3 px-4 font-semibold text-content-primary whitespace-nowrap">
                    {item.zone_id ? item.zone_id.replace(/_/g, ' ') : 'Zone'}
                  </td>
                  <td className="py-3 px-4 whitespace-nowrap">
                    <span className="font-mono text-[12px] bg-fill-active px-2 py-0.5 rounded text-content-secondary">
                      {item.detector}
                    </span>
                  </td>
                  <td className="py-3 px-4 font-mono text-[12px] whitespace-nowrap">
                    <span className="text-content-muted">{item.old_threshold?.toFixed(2)}</span>
                    <span className="mx-1 text-content-muted">→</span>
                    <span className="font-bold text-primary">{item.new_threshold?.toFixed(2)}</span>
                  </td>
                  <td className="py-3 px-4 text-content-body max-w-sm">
                    {item.reason}
                  </td>
                  <td className="py-3 px-4 text-content-secondary whitespace-nowrap">
                    {item.who}
                  </td>
                  <td className="py-3 px-4 font-mono text-[12px] text-content-muted whitespace-nowrap">
                    {item.when}
                  </td>
                  {isOwnerOrAdmin && (
                    <td className="py-3 px-4 text-right whitespace-nowrap">
                      <Button
                        variant="secondary"
                        size="sm"
                        icon={<RotateCcw size={12} />}
                        onClick={() => revertMutation.mutate(item.id)}
                      >
                        Revert
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
