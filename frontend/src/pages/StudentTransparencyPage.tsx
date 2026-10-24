import React from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ShieldCheck,
  EyeOff,
  Clock,
  Lock,
  CheckCircle2,
  XCircle,
  HelpCircle,
  FileText,
  ArrowLeft,
  ChevronRight,
} from 'lucide-react'
import { api } from '@/api/client'
import { Card } from '@/components/ui/Card'
import { StatStrip } from '@/components/ui/StatStrip'

export const StudentTransparencyPage: React.FC = () => {
  // Try fetching monthly transparency stats
  const { data: transparencyData } = useQuery({
    queryKey: ['privacy_transparency'],
    queryFn: async () => {
      try {
        return await api.privacy.getTransparency()
      } catch {
        return {
          period: 'October 2026',
          breakglass_count: 3,
          emergency_reveal_count: 1,
          identity_reveal_count: 0,
          export_count: 1,
        }
      }
    },
  })

  return (
    <div className="min-h-screen bg-page text-content-body font-sans antialiased">
      {/* Top Header */}
      <header className="bg-card border-b border-border-divider py-4 px-6 sticky top-0 z-20">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-[8px] bg-primary flex items-center justify-center text-white shadow-soft">
              <ShieldCheck size={18} strokeWidth={2.4} />
            </div>
            <div>
              <span className="text-[17px] font-bold text-content-primary">RakshakAI</span>
              <span className="text-[12px] text-content-muted ml-2 hidden sm:inline">
                Student Transparency Portal
              </span>
            </div>
          </div>

          <Link
            to="/login"
            className="text-[13px] font-medium text-primary hover:text-primary-hover flex items-center gap-1"
          >
            <ArrowLeft size={14} />
            <span>Staff sign in</span>
          </Link>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto p-6 md:p-12 space-y-10">
        {/* Hero Section */}
        <div className="space-y-3">
          <span className="text-[12px] font-semibold text-primary uppercase tracking-wider block">
            Public Transparency Report
          </span>
          <h1 className="text-[28px] sm:text-[34px] font-bold text-content-primary leading-tight">
            How your privacy is protected at Block B Hostel
          </h1>
          <p className="text-[15px] text-content-secondary leading-relaxed max-w-2xl">
            We believe safety technology should protect students without invasive surveillance. Here is a plain-language explanation of what is monitored, what is never done, and how footage is locked.
          </p>
        </div>

        {/* Monthly Transparency Metrics */}
        <div>
          <h2 className="text-[18px] font-semibold text-content-primary mb-3">
            Monthly accountability report (October 2026)
          </h2>
          <StatStrip
            stats={[
              {
                label: 'Break-glass accesses',
                value: transparencyData?.breakglass_count ?? 3,
                meta: <span>Face-blurred real footage views</span>,
              },
              {
                label: 'Identity reveals granted',
                value: transparencyData?.identity_reveal_count ?? 0,
                meta: <span>Dual admin approved unblurs</span>,
              },
              {
                label: 'Emergency intruder reveals',
                value: transparencyData?.emergency_reveal_count ?? 1,
                meta: <span>Intruder bounding box unblurs</span>,
              },
              {
                label: 'Police exports',
                value: transparencyData?.export_count ?? 1,
                meta: <span>Chain-of-custody locked clips</span>,
              },
            ]}
          />
        </div>

        {/* What is NOT Done (Guarantees) */}
        <Card padding="lg" className="border-critical-border bg-critical-tint/20 space-y-4">
          <h2 className="text-[18px] font-semibold text-critical flex items-center gap-2">
            <XCircle size={20} />
            What RakshakAI NEVER does
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-[13px] text-content-body">
            <div className="space-y-1">
              <strong className="text-content-primary block font-semibold">
                No Facial Recognition
              </strong>
              <p className="text-content-secondary leading-relaxed">
                We do not index faces, compare students against photo databases, or track individuals across campus.
              </p>
            </div>

            <div className="space-y-1">
              <strong className="text-content-primary block font-semibold">
                No Automated Disciplinary Actions
              </strong>
              <p className="text-content-secondary leading-relaxed">
                The AI cannot issue fines, gate bans, or disciplinary warnings. Only human wardens make final determinations.
              </p>
            </div>

            <div className="space-y-1">
              <strong className="text-content-primary block font-semibold">
                No Private Room Monitoring
              </strong>
              <p className="text-content-secondary leading-relaxed">
                Sensors are strictly placed only in perimeter walls, turnstile gates, rooftop terraces, and common corridors.
              </p>
            </div>

            <div className="space-y-1">
              <strong className="text-content-primary block font-semibold">
                No Indefinite Footage Retention
              </strong>
              <p className="text-content-secondary leading-relaxed">
                All video and audio recordings are permanently destroyed after 30 days unless involved in an active safety investigation.
              </p>
            </div>
          </div>
        </Card>

        {/* What IS Monitored */}
        <Card padding="lg" className="space-y-4">
          <h2 className="text-[18px] font-semibold text-content-primary flex items-center gap-2">
            <CheckCircle2 size={20} className="text-status-healthy" />
            What is monitored and why
          </h2>
          <div className="space-y-3 text-[14px] text-content-body leading-relaxed">
            <p>
              <strong>1. Rooftop Terraces After Curfew:</strong> Pose keypoints detect human movement on the terrace after 11:00 pm to prevent unauthorized access or fall risks.
            </p>
            <p>
              <strong>2. Audio Distress & Screams:</strong> Acoustic decibel and frequency analysis alerts guards to screams or physical fights while filtering out benign celebration sounds like laughter.
            </p>
            <p>
              <strong>3. Tailgating at Gates:</strong> Turnstile sensors verify that entry turnstiles have an authorized swipe for every person entering the building.
            </p>
            <p>
              <strong>4. Student SOS Buttons:</strong> Anonymous digital QR assistance alerts security to medical needs, harassment, or safety concerns.
            </p>
          </div>
        </Card>

        {/* How Footage is Accessed */}
        <Card padding="lg" className="space-y-4">
          <h2 className="text-[18px] font-semibold text-content-primary">
            How footage is protected from misuse
          </h2>
          <div className="space-y-3 text-[13px] text-content-secondary leading-relaxed">
            <div className="p-3 rounded-card bg-fill-subtle border border-border-card">
              <strong className="text-content-primary block font-semibold mb-0.5">
                Default Skeleton View
              </strong>
              Security staff see only skeleton wireframes over black tiles. Real faces remain hidden by default.
            </div>

            <div className="p-3 rounded-card bg-fill-subtle border border-border-card">
              <strong className="text-content-primary block font-semibold mb-0.5">
                Break-Glass Logging
              </strong>
              If a guard must view real footage to investigate a fight, they must input a formal written reason. This reason is permanently recorded on an immutable cryptographic ledger.
            </div>

            <div className="p-3 rounded-card bg-fill-subtle border border-border-card">
              <strong className="text-content-primary block font-semibold mb-0.5">
                Two-Person Identity Reveal
              </strong>
              Unblurring faces requires the independent approval of a second administrator. Nobody can authorize their own reveal.
            </div>
          </div>
        </Card>

        {/* Footer info */}
        <div className="pt-6 border-t border-border-divider text-center text-[13px] text-content-muted">
          <p>
            Questions or privacy concerns? Contact the Hostel Safety & Compliance Committee at{' '}
            <a href="mailto:safety@sunrise.demo" className="text-primary underline">
              safety@sunrise.demo
            </a>
          </p>
        </div>
      </main>
    </div>
  )
}
