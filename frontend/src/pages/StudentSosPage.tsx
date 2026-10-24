import React, { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  ShieldCheck,
  CheckCircle2,
  HeartPulse,
  Swords,
  UserX,
  AlertTriangle,
  HelpCircle,
  PhoneCall,
  MapPin,
  ArrowRight,
} from 'lucide-react'
import { api } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { toast } from 'sonner'

const SOS_OPTIONS = [
  {
    category: 'medical',
    title: 'Someone needs medical help',
    hint: 'First aid, injury, fainting, or sudden sickness',
    icon: <HeartPulse size={20} className="text-critical" />,
  },
  {
    category: 'fight',
    title: 'There is a fight',
    hint: 'Physical altercation, loud threats, or aggression',
    icon: <Swords size={20} className="text-status-high" />,
  },
  {
    category: 'harassment',
    title: 'Someone is harassing me',
    hint: 'Unwanted following, intimidation, or persistent stalking',
    icon: <UserX size={20} className="text-critical" />,
  },
  {
    category: 'unsafe',
    title: 'I feel unsafe',
    hint: 'Suspicious presence, stranger in hallway, or feeling cornered',
    icon: <AlertTriangle size={20} className="text-status-medium" />,
  },
  {
    category: 'other',
    title: 'Something else',
    hint: 'Other immediate security or facility emergency',
    icon: <HelpCircle size={20} className="text-content-secondary" />,
  },
]

export const StudentSosPage: React.FC = () => {
  const { token } = useParams<{ token: string }>()
  const [selectedCategory, setSelectedCategory] = useState<string>('')
  const [note, setNote] = useState<string>('')
  const [submitted, setSubmitted] = useState<boolean>(false)
  const [submittedZoneName, setSubmittedZoneName] = useState<string>('')

  // Fetch zone info
  const { data: zoneInfo, isLoading, error } = useQuery({
    queryKey: ['sos_info', token],
    queryFn: () => api.sos.getInfo(token || ''),
    enabled: !!token,
  })

  const submitMutation = useMutation({
    mutationFn: (cat: string) =>
      api.sos.submit(token || '', {
        category: cat,
        note: note.trim() || undefined,
      }),
    onSuccess: (res) => {
      setSubmitted(true)
      setSubmittedZoneName(res.zone_name || zoneInfo?.zone_name || 'your location')
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to send alert. Please call campus helpline.')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedCategory) {
      toast.error('Please tap one option above')
      return
    }
    submitMutation.mutate(selectedCategory)
  }

  const handleReset = () => {
    setSubmitted(false)
    setSelectedCategory('')
    setNote('')
  }

  const zoneName = zoneInfo?.zone_name || 'Hostel Campus'

  return (
    <div className="min-h-screen bg-page text-content-body flex flex-col justify-between p-4 sm:p-6 max-w-md mx-auto font-sans antialiased">
      {/* Top Header */}
      <div>
        <div className="flex items-center justify-between pb-4 border-b border-border-divider">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-[8px] bg-primary flex items-center justify-center text-white shadow-soft">
              <ShieldCheck size={18} strokeWidth={2.4} />
            </div>
            <span className="text-[17px] font-bold text-content-primary">
              RakshakAI
            </span>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-card border border-border-card text-[12px] font-medium text-content-secondary shadow-soft">
            <MapPin size={13} className="text-primary" />
            <span>{isLoading ? 'Locating…' : zoneName}</span>
          </div>
        </div>

        {/* Content Body */}
        {!submitted ? (
          <div className="mt-6">
            <h1 className="text-[24px] font-bold text-content-primary leading-tight">
              What's going on?
            </h1>
            <p className="text-[14px] text-content-secondary mt-1.5 leading-relaxed">
              Tap one. Security on duty gets it right away. You don't have to give your name.
            </p>

            <form onSubmit={handleSubmit} className="mt-5 space-y-2.5">
              {/* 5 Full-Width Option Buttons */}
              {SOS_OPTIONS.map((opt) => {
                const isSelected = selectedCategory === opt.category
                return (
                  <button
                    key={opt.category}
                    type="button"
                    onClick={() => setSelectedCategory(opt.category)}
                    className={`w-full p-4 text-left rounded-card border transition-all flex items-start gap-3.5 ${
                      isSelected
                        ? 'bg-content-primary text-white border-content-primary shadow-md'
                        : 'bg-card text-content-body border-border-card hover:bg-fill-subtle'
                    }`}
                  >
                    <div className="mt-0.5 shrink-0">{opt.icon}</div>
                    <div>
                      <span className={`text-[15px] font-semibold block ${isSelected ? 'text-white' : 'text-content-primary'}`}>
                        {opt.title}
                      </span>
                      <span className={`text-[12px] block mt-0.5 ${isSelected ? 'text-white/80' : 'text-content-muted'}`}>
                        {opt.hint}
                      </span>
                    </div>
                  </button>
                )
              })}

              {/* Optional Note Box */}
              <div className="pt-2">
                <label className="block text-[12px] font-medium text-content-secondary mb-1">
                  Optional extra detail (e.g. room number or description)
                </label>
                <textarea
                  rows={2}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="e.g. Near the west stairs on 2nd floor"
                  className="w-full px-3 py-2 text-[14px] bg-card border border-border-input rounded-input focus:outline-none focus:border-primary"
                />
              </div>

              {/* Big Red Button */}
              <div className="pt-2">
                <button
                  type="submit"
                  disabled={!selectedCategory || submitMutation.isPending}
                  className="w-full py-3.5 px-4 rounded-btn bg-critical-danger hover:bg-critical-danger/90 disabled:opacity-50 text-white font-semibold text-[16px] shadow-soft transition-all flex items-center justify-center gap-2"
                >
                  {submitMutation.isPending ? (
                    <span className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <span>Send to security</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        ) : (
          /* Success Screen */
          <div className="mt-12 text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-status-healthy-tint text-status-healthy flex items-center justify-center mx-auto">
              <CheckCircle2 size={36} />
            </div>

            <div className="space-y-2">
              <h1 className="text-[24px] font-bold text-content-primary">
                Security has been told
              </h1>
              <p className="text-[15px] text-content-body max-w-sm mx-auto leading-relaxed">
                Someone is on the way to <strong>{submittedZoneName}</strong>. If you can, move somewhere you feel safe.
              </p>
            </div>

            <div className="p-4 bg-fill-subtle rounded-card border border-border-card text-[13px] text-content-secondary max-w-sm mx-auto">
              A guard and warden have received your emergency ping on their monitor.
            </div>

            <div className="pt-4">
              <Button variant="secondary" size="md" onClick={handleReset}>
                Report something else
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Helpline Line Footer */}
      <div className="pt-6 mt-6 border-t border-border-divider text-center">
        <div className="flex items-center justify-center gap-2 text-[13px] text-content-secondary">
          <PhoneCall size={14} className="text-primary" />
          <span>Campus Emergency Helpline: <strong>+91 1800-425-789</strong></span>
        </div>
        <p className="text-[11px] text-content-muted mt-1">
          Available 24x7. For external police emergency, call 112.
        </p>
      </div>
    </div>
  )
}
