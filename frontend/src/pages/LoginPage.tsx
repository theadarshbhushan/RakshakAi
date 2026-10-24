import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { ShieldCheck, ArrowRight, Shield, Eye, Users } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

const DEMO_PRESETS = [
  { label: 'Owner', email: 'owner@sunrise.demo', pass: 'Owner@12345' },
  { label: 'Admin', email: 'admin@sunrise.demo', pass: 'Admin@12345' },
  { label: 'Warden', email: 'warden@sunrise.demo', pass: 'Warden@12345' },
  { label: 'Guard', email: 'guard@sunrise.demo', pass: 'Guard@12345' },
  { label: 'Auditor', email: 'auditor@sunrise.demo', pass: 'Auditor@12345' },
  { label: 'Another hostel', email: 'owner@greenvalley.demo', pass: 'Owner@12345' },
]

export const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('owner@sunrise.demo')
  const [password, setPassword] = useState('Owner@12345')
  const [selectedPill, setSelectedPill] = useState('Owner')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [loginError, setLoginError] = useState<string | null>(null)

  const { login } = useAuthStore()
  const navigate = useNavigate()

  const handleSelectPreset = (preset: typeof DEMO_PRESETS[0]) => {
    setSelectedPill(preset.label)
    setEmail(preset.email)
    setPassword(preset.pass)
    setLoginError(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoginError(null)
    setIsSubmitting(true)
    try {
      await login(email, password)
      navigate('/')
    } catch (err: any) {
      setLoginError(err.message || 'Invalid email or password.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-page flex flex-col md:flex-row font-sans">
      {/* Left Half: Login Form */}
      <div className="w-full md:w-1/2 flex flex-col justify-between p-8 sm:p-12 md:p-16 lg:p-20 bg-card">
        {/* Top Logo */}
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-[8px] bg-primary flex items-center justify-center text-white shadow-soft">
              <ShieldCheck size={22} strokeWidth={2.4} />
            </div>
            <span className="text-[20px] font-bold tracking-tight text-content-primary">
              RakshakAI
            </span>
          </div>

          <div className="mt-12 max-w-md">
            <h1 className="text-[26px] font-bold text-content-primary">Sign in</h1>
            <p className="text-[14px] text-content-secondary mt-1.5">
              For hostel wardens, security staff and admins.
            </p>

            {loginError && (
              <div className="mt-4 p-3 rounded-card bg-critical-tint border border-critical-border text-critical text-[13px]">
                {loginError}
              </div>
            )}

            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <Input
                label="Email address"
                type="email"
                required
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                  setSelectedPill('')
                }}
                placeholder="name@sunrise.demo"
              />

              <div>
                <Input
                  label="Password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value)
                    setSelectedPill('')
                  }}
                  placeholder="••••••••"
                />
                <div className="flex justify-end mt-1.5">
                  <a
                    href="#forgot"
                    onClick={(e) => {
                      e.preventDefault()
                      alert('For demo purposes, select any role pill below to auto-fill credentials.')
                    }}
                    className="text-[13px] text-content-muted hover:text-primary transition-colors"
                  >
                    Forgot password?
                  </a>
                </div>
              </div>

              <Button
                type="submit"
                variant="primary"
                size="lg"
                className="w-full mt-2"
                isLoading={isSubmitting}
              >
                Sign in
              </Button>
            </form>

            {/* Demo Pills */}
            <div className="mt-8 pt-6 border-t border-border-divider">
              <p className="text-[13px] font-medium text-content-secondary mb-3">
                Trying the demo? Sign in as:
              </p>
              <div className="flex flex-wrap gap-2">
                {DEMO_PRESETS.map((p) => {
                  const isSelected = selectedPill === p.label
                  return (
                    <button
                      key={p.label}
                      type="button"
                      onClick={() => handleSelectPreset(p)}
                      className={`px-3 py-1.5 text-[12px] font-medium rounded-full transition-all ${
                        isSelected
                          ? 'bg-content-primary text-white shadow-soft'
                          : 'bg-fill-subtle text-content-secondary hover:text-content-primary hover:bg-fill-active border border-border-card/60'
                      }`}
                    >
                      {p.label}
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Footer links */}
        <div className="mt-12 pt-6 flex items-center gap-6 text-[13px] text-content-muted">
          <Link
            to="/transparency"
            className="hover:text-primary transition-colors underline-offset-4 hover:underline"
          >
            What we monitor (for students)
          </Link>
          <Link
            to="/transparency"
            className="hover:text-primary transition-colors underline-offset-4 hover:underline"
          >
            Privacy
          </Link>
        </div>
      </div>

      {/* Right Half: Solid #1E5B4F Brand Panel */}
      <div className="w-full md:w-1/2 bg-primary text-white flex flex-col justify-center p-8 sm:p-12 md:p-16 lg:p-20 relative overflow-hidden">
        <div className="max-w-lg z-10">
          <span className="text-[12px] tracking-wider uppercase font-semibold text-primary-tint opacity-90 block mb-4">
            Safe Hostels · Responsible AI
          </span>
          <h2 className="text-[28px] sm:text-[34px] font-bold leading-tight text-white mb-8">
            Fewer false alarms. Faster help. Students' privacy left intact.
          </h2>

          <div className="space-y-6 text-[15px] leading-relaxed text-primary-tint/90">
            <div className="flex items-start gap-4">
              <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center shrink-0 mt-0.5 text-white">
                <Shield size={18} />
              </div>
              <p>
                Alerts escalate only when sensors agree. Video, audio, and door swipe logs corroborate before anyone is disturbed.
              </p>
            </div>

            <div className="flex items-start gap-4">
              <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center shrink-0 mt-0.5 text-white">
                <Eye size={18} />
              </div>
              <p>
                Guards see outlines not faces unless there's a logged reason. Raw footage stays encrypted with audit chains.
              </p>
            </div>

            <div className="flex items-start gap-4">
              <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center shrink-0 mt-0.5 text-white">
                <Users size={18} />
              </div>
              <p>
                A person makes every final call. No automated disciplinary action is ever taken against students without human review.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
