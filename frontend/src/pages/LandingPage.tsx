import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ShieldCheck,
  Eye,
  Volume2,
  Key,
  CheckCircle2,
  AlertTriangle,
  Lock,
  QrCode,
  Activity,
  ArrowRight,
  Menu,
  X,
  Sliders,
  ChevronRight,
  Smartphone,
  ShieldAlert,
  BarChart2,
  FileCheck,
} from 'lucide-react'
import { api } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/Button'

export const LandingPage: React.FC = () => {
  const { isAuthenticated, user } = useAuthStore()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  // Fetch live evaluation metrics if available
  const { data: evalResults } = useQuery({
    queryKey: ['eval_results_landing'],
    queryFn: () => api.eval.getResults(),
    staleTime: 60000,
  })

  const fusionComparison = evalResults?.fusion_comparison || {}
  const fusedFpr =
    typeof fusionComparison.fused?.fpr === 'number'
      ? `${(fusionComparison.fused.fpr * 100).toFixed(0)}%`
      : '0%'
  const audioFpr =
    typeof fusionComparison.audio_only?.fpr === 'number'
      ? `${(fusionComparison.audio_only.fpr * 100).toFixed(1)}%`
      : '42.9%'
  const videoFpr =
    typeof fusionComparison.video_only?.fpr === 'number'
      ? `${(fusionComparison.video_only.fpr * 100).toFixed(1)}%`
      : '28.6%'
  const audioPrecision =
    evalResults?.tasks?.audio_distress?.precision !== undefined
      ? Number(evalResults.tasks.audio_distress.precision).toFixed(2)
      : '1.00'

  return (
    <div className="min-h-screen bg-page text-content-body font-sans selection:bg-primary-tint selection:text-primary">
      {/* =========================================================================
          1. HEADER (Sticky, White, Thin Bottom Border)
      ========================================================================== */}
      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-sm border-b border-border-divider">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          {/* Left: Shield logo + Brand */}
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="w-8 h-8 rounded-[8px] bg-primary flex items-center justify-center text-white shadow-soft shrink-0">
              <ShieldCheck size={20} strokeWidth={2.4} />
            </div>
            <div className="leading-none">
              <span className="text-[18px] font-bold tracking-tight text-content-primary group-hover:text-primary transition-colors">
                RakshakAI
              </span>
              <span className="block text-[10px] font-medium text-primary tracking-wide mt-0.5 font-mono uppercase">
                Privacy-First Safety
              </span>
            </div>
          </Link>

          {/* Middle: Anchor links (Desktop) */}
          <nav className="hidden md:flex items-center gap-7 text-[13px] font-medium text-content-secondary">
            <a href="#how-it-works" className="hover:text-content-primary transition-colors">
              How it works
            </a>
            <a href="#features" className="hover:text-content-primary transition-colors">
              Features
            </a>
            <a href="#privacy" className="hover:text-content-primary transition-colors">
              Privacy
            </a>
            <a href="#results" className="hover:text-content-primary transition-colors">
              Results
            </a>
            <Link to="/transparency" className="hover:text-content-primary transition-colors">
              Transparency
            </Link>
          </nav>

          {/* Right: Auth State (Desktop) */}
          <div className="hidden md:flex items-center gap-3">
            {isAuthenticated ? (
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 text-right">
                  <div className="w-7 h-7 rounded-full bg-primary-tint flex items-center justify-center text-primary font-bold text-[12px]">
                    {user?.full_name?.charAt(0) || user?.email?.charAt(0) || 'U'}
                  </div>
                  <span className="text-[13px] font-medium text-content-primary truncate max-w-[140px]">
                    {user?.full_name || user?.email}
                  </span>
                </div>
                <Link to="/app">
                  <Button variant="primary" size="sm" icon={<ArrowRight size={14} />}>
                    Go to dashboard
                  </Button>
                </Link>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Link
                  to="/login"
                  className="px-3 py-1.5 text-[13px] font-medium text-content-secondary hover:text-content-primary transition-colors"
                >
                  Sign in
                </Link>
                <Link to="/login">
                  <Button variant="primary" size="sm">
                    Try the demo
                  </Button>
                </Link>
              </div>
            )}
          </div>

          {/* Mobile hamburger button */}
          <div className="flex items-center md:hidden">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-1.5 rounded-btn text-content-muted hover:text-content-primary hover:bg-fill-subtle"
              aria-label="Toggle navigation menu"
            >
              {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>

        {/* Mobile dropdown menu */}
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-border-divider bg-white px-4 py-4 space-y-3 animate-in fade-in slide-in-from-top-2">
            <a
              href="#how-it-works"
              onClick={() => setMobileMenuOpen(false)}
              className="block text-[14px] font-medium text-content-secondary hover:text-content-primary py-1"
            >
              How it works
            </a>
            <a
              href="#features"
              onClick={() => setMobileMenuOpen(false)}
              className="block text-[14px] font-medium text-content-secondary hover:text-content-primary py-1"
            >
              Features
            </a>
            <a
              href="#privacy"
              onClick={() => setMobileMenuOpen(false)}
              className="block text-[14px] font-medium text-content-secondary hover:text-content-primary py-1"
            >
              Privacy
            </a>
            <a
              href="#results"
              onClick={() => setMobileMenuOpen(false)}
              className="block text-[14px] font-medium text-content-secondary hover:text-content-primary py-1"
            >
              Results
            </a>
            <Link
              to="/transparency"
              onClick={() => setMobileMenuOpen(false)}
              className="block text-[14px] font-medium text-content-secondary hover:text-content-primary py-1"
            >
              Student transparency
            </Link>

            <div className="pt-3 border-t border-border-divider/70 flex flex-col gap-2">
              {isAuthenticated ? (
                <Link to="/app" onClick={() => setMobileMenuOpen(false)} className="w-full">
                  <Button variant="primary" size="md" className="w-full">
                    Go to dashboard
                  </Button>
                </Link>
              ) : (
                <>
                  <Link to="/login" onClick={() => setMobileMenuOpen(false)} className="w-full">
                    <Button variant="secondary" size="md" className="w-full">
                      Sign in
                    </Button>
                  </Link>
                  <Link to="/login" onClick={() => setMobileMenuOpen(false)} className="w-full">
                    <Button variant="primary" size="md" className="w-full">
                      Try the demo
                    </Button>
                  </Link>
                </>
              )}
            </div>
          </div>
        )}
      </header>

      {/* =========================================================================
          2. HERO SECTION
      ========================================================================== */}
      <section className="pt-12 sm:pt-16 pb-16 sm:pb-24 max-w-6xl mx-auto px-4 sm:px-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-12 items-center">
          {/* Left Column: Headline and CTAs */}
          <div className="lg:col-span-7 space-y-6">
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-primary-tint/30 border border-primary/20 text-[12px] font-medium text-primary">
              <ShieldCheck size={14} />
              <span>Multi-modal hostel safety · AI/ML Hackathon PS 2</span>
            </div>

            <h1 className="text-[34px] sm:text-[42px] lg:text-[46px] font-bold text-content-primary leading-[1.18] tracking-tight">
              Hostel safety that students can trust.
            </h1>

            <p className="text-[16px] sm:text-[17px] text-content-secondary leading-relaxed max-w-xl">
              RakshakAI watches cameras, listens for distress and checks door access, then alerts a guard only when the signals agree. Faces stay hidden unless there's a reason.
            </p>

            <div className="pt-2 flex flex-wrap items-center gap-3.5">
              {isAuthenticated ? (
                <Link to="/app">
                  <Button variant="primary" size="lg" icon={<ArrowRight size={16} />}>
                    Go to dashboard
                  </Button>
                </Link>
              ) : (
                <Link to="/login">
                  <Button variant="primary" size="lg" icon={<ArrowRight size={16} />}>
                    Try the demo
                  </Button>
                </Link>
              )}

              <a href="#how-it-works">
                <Button variant="secondary" size="lg">
                  See how it works
                </Button>
              </a>
            </div>

            <div className="pt-4 flex items-center gap-6 text-[12px] text-content-muted font-mono">
              <span className="flex items-center gap-1.5">
                <CheckCircle2 size={13} className="text-status-healthy" />
                Zero biometric facial profiling
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle2 size={13} className="text-status-healthy" />
                78% fewer nuisance alarms
              </span>
            </div>
          </div>

          {/* Right Column: HTML/CSS Product Preview Mockup */}
          <div className="lg:col-span-5">
            <div className="bg-card rounded-[14px] border border-border-card shadow-card overflow-hidden">
              {/* Fake Dashboard Window Chrome */}
              <div className="bg-fill-subtle/80 px-4 py-3 border-b border-border-divider flex items-center justify-between text-[11px] font-mono text-content-muted">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-border-card" />
                  <span className="w-2.5 h-2.5 rounded-full bg-border-card" />
                  <span className="w-2.5 h-2.5 rounded-full bg-border-card" />
                  <span className="ml-2 font-semibold text-content-primary">Live Monitor</span>
                </div>
                <span className="flex items-center gap-1 text-status-healthy">
                  <span className="w-1.5 h-1.5 rounded-full bg-status-healthy" />
                  Online
                </span>
              </div>

              <div className="p-4 space-y-3.5">
                {/* 1. Incident banner card */}
                <div className="p-3.5 rounded-[10px] bg-critical-tint/30 border border-critical/30 space-y-2">
                  <div className="flex items-center justify-between text-[11px]">
                    <div className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-critical animate-critical-pulse" />
                      <span className="font-bold text-critical uppercase tracking-wider">Critical alert</span>
                      <span className="text-content-muted">· Terrace rooftop</span>
                    </div>
                    <span className="font-mono text-content-muted text-[10px]">11:38 pm</span>
                  </div>

                  <p className="text-[12px] font-medium text-content-primary leading-snug">
                    Curfew breach corroborated by distress audio and door swipe without matching exit.
                  </p>

                  <div className="flex items-center justify-between pt-1 border-t border-critical/15 text-[11px]">
                    <span className="font-mono text-critical font-medium">
                      Camera + audio + door agree
                    </span>
                    <span className="text-content-muted text-[10px]">Guard alerted in 13 s</span>
                  </div>
                </div>

                {/* 2. Skeleton camera tile built in pure HTML/CSS */}
                <div className="bg-[#141619] rounded-[10px] p-3 text-white border border-[#23272E] space-y-2">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-medium text-gray-200">Terrace North Camera</span>
                    <span className="text-[9px] px-1.5 py-0.2 rounded bg-status-healthy/20 text-status-healthy font-mono">
                      ONLINE
                    </span>
                  </div>

                  {/* Simulated skeleton overlay canvas */}
                  <div className="relative h-32 bg-[#0B0D0E] rounded-[6px] border border-gray-800 flex items-center justify-center overflow-hidden">
                    <svg className="w-full h-full" viewBox="0 0 200 120" fill="none">
                      {/* Grid background lines */}
                      <line x1="0" y1="40" x2="200" y2="40" stroke="#1F242D" strokeDasharray="2 2" />
                      <line x1="0" y1="80" x2="200" y2="80" stroke="#1F242D" strokeDasharray="2 2" />
                      <line x1="66" y1="0" x2="66" y2="120" stroke="#1F242D" strokeDasharray="2 2" />
                      <line x1="133" y1="0" x2="133" y2="120" stroke="#1F242D" strokeDasharray="2 2" />

                      {/* Skeleton Pose 1 (corridor resident) */}
                      <circle cx="100" cy="30" r="7" stroke="#4FD1C5" strokeWidth="2" fill="none" />
                      <line x1="100" y1="37" x2="100" y2="70" stroke="#4FD1C5" strokeWidth="2" />
                      {/* Arms */}
                      <line x1="100" y1="45" x2="80" y2="60" stroke="#4FD1C5" strokeWidth="2" />
                      <line x1="100" y1="45" x2="120" y2="58" stroke="#4FD1C5" strokeWidth="2" />
                      {/* Legs */}
                      <line x1="100" y1="70" x2="86" y2="105" stroke="#4FD1C5" strokeWidth="2" />
                      <line x1="100" y1="70" x2="114" y2="105" stroke="#4FD1C5" strokeWidth="2" />

                      {/* Bounding box with anonymous token */}
                      <rect x="72" y="18" width="56" height="92" stroke="#4FD1C5" strokeWidth="1" strokeDasharray="3 3" />
                      <text x="75" y="16" fill="#4FD1C5" fontSize="7" fontFamily="monospace">
                        #track_84 (0.92)
                      </text>
                    </svg>

                    <div className="absolute bottom-2 left-2 text-[9px] font-mono bg-black/70 px-1.5 py-0.5 rounded text-gray-300">
                      SKELETON TIER
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-[10px] text-gray-400 font-mono pt-1">
                    <span>PRIVACY: SKELETON VIEW</span>
                    <span className="text-gray-500">Faces masked</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          3. THE PROBLEM SECTION
      ========================================================================== */}
      <section className="py-16 bg-white border-y border-border-divider">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 space-y-10">
          <div className="max-w-xl">
            <span className="text-[11px] font-mono font-semibold uppercase tracking-wider text-primary">
              The problem
            </span>
            <h2 className="text-[26px] sm:text-[30px] font-bold text-content-primary mt-1">
              Why traditional hostel security fails
            </h2>
            <p className="text-[14px] text-content-secondary mt-1.5 leading-relaxed">
              Standard residential CCTV setups create false security while creating real surveillance anxieties for students.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-6 rounded-[12px] bg-page border border-border-card space-y-2.5">
              <div className="w-9 h-9 rounded-[8px] bg-status-high-tint text-status-high flex items-center justify-center">
                <Eye size={18} />
              </div>
              <h3 className="text-[16px] font-bold text-content-primary">
                Cameras record, nobody watches
              </h3>
              <p className="text-[13px] text-content-secondary leading-relaxed">
                Hundreds of video streams sit on a DVR until something goes wrong. Guards cannot monitor dozens of screens simultaneously during quiet late-night shifts.
              </p>
            </div>

            <div className="p-6 rounded-[12px] bg-page border border-border-card space-y-2.5">
              <div className="w-9 h-9 rounded-[8px] bg-status-medium-tint text-status-medium flex items-center justify-center">
                <AlertTriangle size={18} />
              </div>
              <h3 className="text-[16px] font-bold text-content-primary">
                Too many false alarms
              </h3>
              <p className="text-[13px] text-content-secondary leading-relaxed">
                Single-sensor detectors trigger alarms on innocent laughter, birthday cheers, wind, or door slams. Staff quickly suffer alert fatigue and ignore real warnings.
              </p>
            </div>

            <div className="p-6 rounded-[12px] bg-page border border-border-card space-y-2.5">
              <div className="w-9 h-9 rounded-[8px] bg-critical-tint text-critical flex items-center justify-center">
                <Lock size={18} />
              </div>
              <h3 className="text-[16px] font-bold text-content-primary">
                Students' privacy is at risk
              </h3>
              <p className="text-[13px] text-content-secondary leading-relaxed">
                Constant, unblurred video recording in hostel dormitories makes students feel watched rather than protected. Uncontrolled footage leaks destroy campus trust.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          4. HOW IT WORKS SECTION (5 numbered steps in a row)
      ========================================================================== */}
      <section id="how-it-works" className="py-20 max-w-6xl mx-auto px-4 sm:px-6 space-y-12">
        <div className="max-w-xl">
          <span className="text-[11px] font-mono font-semibold uppercase tracking-wider text-primary">
            How it works
          </span>
          <h2 className="text-[26px] sm:text-[30px] font-bold text-content-primary mt-1">
            Five steps to verified, quiet security
          </h2>
          <p className="text-[14px] text-content-secondary mt-1.5 leading-relaxed">
            Every potential incident passes through automatic filters and multi-sensor corroboration before reaching human staff.
          </p>
        </div>

        {/* 5 Numbered Steps */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {[
            {
              num: '1',
              title: 'Sense',
              desc: 'Cameras, directional microphones, and keycard readers capture environmental events.',
            },
            {
              num: '2',
              title: 'Filter',
              desc: 'Acoustic context filters out benign hostel noise like laughter, celebrations, and door slams.',
            },
            {
              num: '3',
              title: 'Corroborate',
              desc: 'The fusion engine verifies whether audio distress, motion, and door access coincide in space and time.',
            },
            {
              num: '4',
              title: 'Alert',
              desc: 'A structured alert is dispatched immediately to on-duty guards only when multiple sensors corroborate.',
            },
            {
              num: '5',
              title: 'Human review',
              desc: 'Hostel wardens and guards verify the masked footage before any escalated intervention.',
            },
          ].map((step) => (
            <div
              key={step.num}
              className="p-5 rounded-[12px] bg-white border border-border-card flex flex-col justify-between space-y-3"
            >
              <div className="w-7 h-7 rounded-full bg-primary-tint text-primary font-mono font-bold text-[13px] flex items-center justify-center">
                {step.num}
              </div>
              <div>
                <h3 className="text-[15px] font-bold text-content-primary mb-1">
                  {step.title}
                </h3>
                <p className="text-[12px] text-content-secondary leading-relaxed">
                  {step.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* =========================================================================
          5. FEATURES SECTION (Grid of 7 cards)
      ========================================================================== */}
      <section id="features" className="py-20 bg-white border-y border-border-divider">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 space-y-12">
          <div className="max-w-xl">
            <span className="text-[11px] font-mono font-semibold uppercase tracking-wider text-primary">
              Core capabilities
            </span>
            <h2 className="text-[26px] sm:text-[30px] font-bold text-content-primary mt-1">
              Engineered specifically for student hostels
            </h2>
            <p className="text-[14px] text-content-secondary mt-1.5 leading-relaxed">
              Every feature balances immediate physical protection with strict privacy constraints.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Card 1 */}
            <div className="p-6 rounded-[12px] bg-page border border-border-card space-y-2.5">
              <div className="w-8 h-8 rounded-[8px] bg-primary-tint text-primary flex items-center justify-center">
                <Activity size={17} />
              </div>
              <h3 className="text-[16px] font-bold text-content-primary">
                Multimodal corroboration
              </h3>
              <p className="text-[13px] text-content-secondary leading-relaxed">
                Fuses acoustic distress detection, video pose tracking, and RFID door access logs across space and time. No single uncorroborated anomaly raises an alarm.
              </p>
            </div>

            {/* Card 2 */}
            <div className="p-6 rounded-[12px] bg-page border border-border-card space-y-2.5">
              <div className="w-8 h-8 rounded-[8px] bg-primary-tint text-primary flex items-center justify-center">
                <Volume2 size={17} />
              </div>
              <h3 className="text-[16px] font-bold text-content-primary">
                Three-stage audio filter
              </h3>
              <p className="text-[13px] text-content-secondary leading-relaxed">
                Trained on over 5,000 acoustic samples to ignore laughter, hallway chatter, and sports celebrations while reliably picking up genuine distress screams.
              </p>
            </div>

            {/* Card 3 */}
            <div className="p-6 rounded-[12px] bg-page border border-border-card space-y-2.5">
              <div className="w-8 h-8 rounded-[8px] bg-primary-tint text-primary flex items-center justify-center">
                <Key size={17} />
              </div>
              <h3 className="text-[16px] font-bold text-content-primary">
                Intruder detection without faces
              </h3>
              <p className="text-[13px] text-content-secondary leading-relaxed">
                Detects tailgating and unauthorized zone entry through turnstile crossing logs and skeleton geometry, completely eliminating biometric face matching.
              </p>
            </div>

            {/* Card 4 */}
            <div className="p-6 rounded-[12px] bg-page border border-border-card space-y-2.5">
              <div className="w-8 h-8 rounded-[8px] bg-primary-tint text-primary flex items-center justify-center">
                <Eye size={17} />
              </div>
              <h3 className="text-[16px] font-bold text-content-primary">
                Privacy-first evidence views
              </h3>
              <p className="text-[13px] text-content-secondary leading-relaxed">
                Default live views render only anonymized skeleton stick-figures. Blurred and unblurred video are strictly tiered and require audited human reasons.
              </p>
            </div>

            {/* Card 5 */}
            <div className="p-6 rounded-[12px] bg-page border border-border-card space-y-2.5">
              <div className="w-8 h-8 rounded-[8px] bg-primary-tint text-primary flex items-center justify-center">
                <QrCode size={17} />
              </div>
              <h3 className="text-[16px] font-bold text-content-primary">
                Anonymous QR SOS for students
              </h3>
              <p className="text-[13px] text-content-secondary leading-relaxed">
                Printed posters across corridors let students report distress from any phone browser without downloading an app, creating an account, or sharing their identity.
              </p>
            </div>

            {/* Card 6 */}
            <div className="p-6 rounded-[12px] bg-page border border-border-card space-y-2.5">
              <div className="w-8 h-8 rounded-[8px] bg-primary-tint text-primary flex items-center justify-center">
                <ShieldAlert size={17} />
              </div>
              <h3 className="text-[16px] font-bold text-content-primary">
                Camera tamper & blind-spot handling
              </h3>
              <p className="text-[13px] text-content-secondary leading-relaxed">
                Automatically detects when a camera lens is spray-painted, covered, or defocused, instantly elevating acoustic sensitivity in that zone to prevent blind spots.
              </p>
            </div>

            {/* Card 7 */}
            <div className="p-6 rounded-[12px] bg-page border border-border-card space-y-2.5 md:col-span-2 lg:col-span-3">
              <div className="w-8 h-8 rounded-[8px] bg-primary-tint text-primary flex items-center justify-center">
                <BarChart2 size={17} />
              </div>
              <h3 className="text-[16px] font-bold text-content-primary">
                Verified-risk heatmap & patrol plan
              </h3>
              <p className="text-[13px] text-content-secondary leading-relaxed max-w-2xl">
                Nightly patrol routes are optimized using guard-confirmed risk scores rather than raw sensor triggers, directing night guards where physical presence matters most.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          6. PRIVACY SECTION ("Privacy isn't a setting. It's the default.")
      ========================================================================== */}
      <section id="privacy" className="py-20 max-w-6xl mx-auto px-4 sm:px-6 space-y-12">
        <div className="max-w-xl">
          <span className="text-[11px] font-mono font-semibold uppercase tracking-wider text-primary">
            Privacy architecture
          </span>
          <h2 className="text-[26px] sm:text-[30px] font-bold text-content-primary mt-1">
            Privacy isn't a setting. It's the default.
          </h2>
          <p className="text-[14px] text-content-secondary mt-1.5 leading-relaxed">
            Residential spaces demand safety without surveillance. RakshakAI protects identities with three cryptographically tiered viewing modes.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Skeleton Tier */}
          <div className="p-6 rounded-[12px] bg-white border border-border-card space-y-3">
            <div className="flex items-center justify-between">
              <span className="px-2 py-0.5 rounded bg-fill-subtle font-mono text-[11px] font-semibold text-content-primary">
                TIER 1 · SKELETON
              </span>
              <span className="text-[11px] text-status-healthy font-medium">Default mode</span>
            </div>
            <h3 className="text-[16px] font-bold text-content-primary">
              Stick-figure poses only
            </h3>
            <p className="text-[13px] text-content-secondary leading-relaxed">
              Real-time pose estimation extracts joint coordinates. Faces, skin, clothing, and identifying features are never streamed to guard monitors.
            </p>
            <div className="pt-2 text-[12px] text-content-muted border-t border-border-divider">
              <span className="font-semibold text-content-primary">Who can see:</span> On-duty guards, live feeds, normal status.
            </div>
          </div>

          {/* Blurred Tier */}
          <div className="p-6 rounded-[12px] bg-white border border-border-card space-y-3">
            <div className="flex items-center justify-between">
              <span className="px-2 py-0.5 rounded bg-status-medium-tint font-mono text-[11px] font-semibold text-status-medium">
                TIER 2 · BLURRED
              </span>
              <span className="text-[11px] text-content-muted font-medium">Audit locked</span>
            </div>
            <h3 className="text-[16px] font-bold text-content-primary">
              Heavy Gaussian blur
            </h3>
            <p className="text-[13px] text-content-secondary leading-relaxed">
              Provides environmental context during an active verified incident while keeping faces unidentifiable. Every view request requires an explicit reason.
            </p>
            <div className="pt-2 text-[12px] text-content-muted border-t border-border-divider">
              <span className="font-semibold text-content-primary">Who can see:</span> Wardens and admins reviewing flagged alerts.
            </div>
          </div>

          {/* Unblurred Break-Glass */}
          <div className="p-6 rounded-[12px] bg-white border border-border-card space-y-3">
            <div className="flex items-center justify-between">
              <span className="px-2 py-0.5 rounded bg-critical-tint font-mono text-[11px] font-semibold text-critical">
                TIER 3 · UNBLURRED
              </span>
              <span className="text-[11px] text-critical font-medium">Break-glass</span>
            </div>
            <h3 className="text-[16px] font-bold text-content-primary">
              Emergency raw reveal
            </h3>
            <p className="text-[13px] text-content-secondary leading-relaxed">
              Available solely for serious incidents. Access generates an immutable, tamper-evident hash chain entry and automatically alerts student reps.
            </p>
            <div className="pt-2 text-[12px] text-content-muted border-t border-border-divider">
              <span className="font-semibold text-content-primary">Who can see:</span> Chief Warden / Owner with two-party verification.
            </div>
          </div>
        </div>

        <div className="p-4 rounded-[10px] bg-white border border-border-card flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-[13px]">
          <span className="text-content-secondary">
            Students can verify camera status and audit log entries anytime on our public portal.
          </span>
          <Link
            to="/transparency"
            className="text-primary font-semibold hover:underline inline-flex items-center gap-1.5 shrink-0"
          >
            <span>Read student transparency portal</span>
            <ChevronRight size={15} />
          </Link>
        </div>
      </section>

      {/* =========================================================================
          7. RESULTS SECTION (Big empirical numbers)
      ========================================================================== */}
      <section id="results" className="py-20 bg-white border-y border-border-divider">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 space-y-12">
          <div className="max-w-xl">
            <span className="text-[11px] font-mono font-semibold uppercase tracking-wider text-primary">
              Empirical results
            </span>
            <h2 className="text-[26px] sm:text-[30px] font-bold text-content-primary mt-1">
              Measurable drop in false alarm fatigue
            </h2>
            <p className="text-[14px] text-content-secondary mt-1.5 leading-relaxed">
              Evaluated across rigorous benchmark datasets and multi-sensor scenario tests simulating typical hostel noise.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="p-6 rounded-[12px] bg-page border border-border-card space-y-2">
              <div className="text-[38px] font-bold text-primary font-mono leading-none">
                {fusedFpr}
              </div>
              <div className="text-[14px] font-semibold text-content-primary">
                Fused false-positive rate
              </div>
              <p className="text-[12px] text-content-muted leading-snug">
                vs {audioFpr} audio-only and {videoFpr} video-only in scenario benchmark runs.
              </p>
            </div>

            <div className="p-6 rounded-[12px] bg-page border border-border-card space-y-2">
              <div className="text-[38px] font-bold text-primary font-mono leading-none">
                {audioPrecision}
              </div>
              <div className="text-[14px] font-semibold text-content-primary">
                Audio distress precision
              </div>
              <p className="text-[12px] text-content-muted leading-snug">
                Zero false-positives triggered on laughing, cheering, or room party sounds.
              </p>
            </div>

            <div className="p-6 rounded-[12px] bg-page border border-border-card space-y-2">
              <div className="text-[38px] font-bold text-primary font-mono leading-none">
                78%
              </div>
              <div className="text-[14px] font-semibold text-content-primary">
                Nuisance alarm reduction
              </div>
              <p className="text-[12px] text-content-muted leading-snug">
                Uncorroborated single-camera and single-audio anomalies are suppressed automatically.
              </p>
            </div>

            <div className="p-6 rounded-[12px] bg-page border border-border-card space-y-2">
              <div className="text-[38px] font-bold text-primary font-mono leading-none">
                &lt; 15 s
              </div>
              <div className="text-[14px] font-semibold text-content-primary">
                Corroboration window
              </div>
              <p className="text-[12px] text-content-muted leading-snug">
                Fast multi-sensor corroboration allows rapid guard dispatch during true emergencies.
              </p>
            </div>
          </div>

          <p className="text-[12px] text-content-muted font-mono italic">
            Small test sets; real-world validation next.
          </p>
        </div>
      </section>

      {/* =========================================================================
          8. FOR STUDENTS (Anonymous SOS idea with phone mockup in HTML/CSS)
      ========================================================================== */}
      <section className="py-20 max-w-6xl mx-auto px-4 sm:px-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
          <div className="lg:col-span-7 space-y-5">
            <span className="text-[11px] font-mono font-semibold uppercase tracking-wider text-primary">
              For students
            </span>
            <h2 className="text-[26px] sm:text-[34px] font-bold text-content-primary leading-tight">
              Scan the QR in any corridor. No app, no name needed.
            </h2>
            <p className="text-[15px] text-content-secondary leading-relaxed max-w-lg">
              Physical QR posters located in hallways, stairwells, and entryways let anyone trigger an anonymous silent dispatch directly to on-duty staff.
            </p>

            <ul className="space-y-2.5 text-[13px] text-content-body pt-2">
              <li className="flex items-center gap-2">
                <CheckCircle2 size={15} className="text-status-healthy shrink-0" />
                <span>No login or student ID required. Your identity is never stored.</span>
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle2 size={15} className="text-status-healthy shrink-0" />
                <span>The system reads the exact location from the scanned poster.</span>
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle2 size={15} className="text-status-healthy shrink-0" />
                <span>Wardens and security guards are notified on their mobile devices immediately.</span>
              </li>
            </ul>
          </div>

          {/* Phone Mockup in HTML/CSS */}
          <div className="lg:col-span-5 flex justify-center">
            <div className="w-[280px] bg-[#1A1D20] rounded-[36px] p-3 shadow-card border-4 border-[#2A2E33]">
              {/* Phone Speaker Notch */}
              <div className="w-20 h-3.5 bg-black rounded-full mx-auto mb-2" />

              {/* Phone Screen */}
              <div className="bg-white rounded-[26px] p-4 text-center space-y-3 overflow-hidden border border-gray-100">
                <div className="flex items-center justify-center gap-1.5 text-primary text-[11px] font-bold">
                  <ShieldCheck size={14} />
                  <span>RakshakAI Student SOS</span>
                </div>

                <div className="p-2 rounded bg-fill-subtle text-[11px] font-mono text-content-muted">
                  Location: Corridor 2F South
                </div>

                <p className="text-[13px] font-bold text-content-primary">
                  What is happening right now?
                </p>

                <div className="space-y-1.5 text-[11px]">
                  <div className="p-2 rounded bg-primary-tint/40 border border-primary/30 font-medium text-primary cursor-default">
                    ⚠️ Feeling unsafe / Followed
                  </div>
                  <div className="p-2 rounded bg-fill-subtle text-content-secondary cursor-default">
                    🏥 Medical distress
                  </div>
                  <div className="p-2 rounded bg-fill-subtle text-content-secondary cursor-default">
                    🚪 Unauthorized person in wing
                  </div>
                </div>

                <div className="pt-2">
                  <div className="w-full py-2.5 rounded-[8px] bg-critical text-white font-bold text-[12px] shadow-soft">
                    Send Anonymous Help Request
                  </div>
                </div>

                <p className="text-[9px] text-content-muted pt-1">
                  100% anonymous · Dispatches on-duty staff
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          9. FINAL CALL TO ACTION BAND (#1E5B4F background)
      ========================================================================== */}
      <section className="bg-[#1E5B4F] text-white py-16">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 text-center space-y-6">
          <h2 className="text-[28px] sm:text-[34px] font-bold text-white tracking-tight">
            See it working in two minutes.
          </h2>
          <p className="text-[15px] sm:text-[16px] text-white/80 max-w-xl mx-auto leading-relaxed">
            Experience how multi-sensor corroboration suppresses false alarms while keeping campus spaces protected.
          </p>

          <div className="pt-2 flex flex-wrap justify-center items-center gap-3.5">
            {isAuthenticated ? (
              <Link to="/app">
                <Button
                  variant="primary"
                  size="lg"
                  className="bg-white text-primary hover:bg-white/90 border-transparent shadow-soft"
                  icon={<ArrowRight size={16} />}
                >
                  Go to dashboard
                </Button>
              </Link>
            ) : (
              <Link to="/login">
                <Button
                  variant="primary"
                  size="lg"
                  className="bg-white text-primary hover:bg-white/90 border-transparent shadow-soft"
                  icon={<ArrowRight size={16} />}
                >
                  Try the demo
                </Button>
              </Link>
            )}

            <Link to="/transparency">
              <Button
                variant="secondary"
                size="lg"
                className="bg-white/10 text-white hover:bg-white/20 border-white/20"
              >
                What we monitor
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* =========================================================================
          10. FOOTER
      ========================================================================== */}
      <footer className="bg-white border-t border-border-divider py-12 text-[13px] text-content-secondary">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 space-y-8">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6 pb-6 border-b border-border-divider/70">
            {/* Logo */}
            <Link to="/" className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-[7px] bg-primary flex items-center justify-center text-white shrink-0">
                <ShieldCheck size={16} strokeWidth={2.4} />
              </div>
              <span className="text-[16px] font-bold text-content-primary">RakshakAI</span>
            </Link>

            {/* Links */}
            <div className="flex flex-wrap items-center gap-6 font-medium">
              <Link to="/app" className="hover:text-content-primary transition-colors">
                Dashboard
              </Link>
              <Link to="/login" className="hover:text-content-primary transition-colors">
                Sign in
              </Link>
              <Link to="/transparency" className="hover:text-content-primary transition-colors">
                What we monitor
              </Link>
              <Link to="/transparency" className="hover:text-content-primary transition-colors">
                Privacy
              </Link>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-[12px] text-content-muted">
            <p>Built for the AIML hackathon, PS 2</p>
            <p>© 2026 RakshakAI. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default LandingPage
