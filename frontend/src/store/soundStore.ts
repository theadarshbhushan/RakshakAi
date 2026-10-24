import { create } from 'zustand'

interface SoundState {
  soundEnabled: boolean
  toggleSound: () => void
  setSoundEnabled: (enabled: boolean) => void
  playAlertChime: (severity: 'critical' | 'high' | 'medium') => void
}

export const useSoundStore = create<SoundState>((set, get) => ({
  soundEnabled: localStorage.getItem('rakshak_sound_enabled') !== 'false',

  toggleSound: () => {
    const next = !get().soundEnabled
    localStorage.setItem('rakshak_sound_enabled', String(next))
    set({ soundEnabled: next })
  },

  setSoundEnabled: (enabled) => {
    localStorage.setItem('rakshak_sound_enabled', String(enabled))
    set({ soundEnabled: enabled })
  },

  playAlertChime: (severity) => {
    if (!get().soundEnabled) return

    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext
      if (!AudioCtx) return
      const ctx = new AudioCtx()

      const now = ctx.currentTime
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()

      osc.connect(gain)
      gain.connect(ctx.destination)

      if (severity === 'critical') {
        // Calm two-tone alert: 520Hz then 659Hz
        osc.type = 'sine'
        osc.frequency.setValueAtTime(523.25, now) // C5
        osc.frequency.setValueAtTime(659.25, now + 0.12) // E5
        gain.gain.setValueAtTime(0.08, now)
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45)
        osc.start(now)
        osc.stop(now + 0.45)
      } else {
        // High/medium single quiet chime: 587Hz (D5)
        osc.type = 'sine'
        osc.frequency.setValueAtTime(587.33, now)
        gain.gain.setValueAtTime(0.06, now)
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35)
        osc.start(now)
        osc.stop(now + 0.35)
      }
    } catch {
      // AudioContext may be restricted by autoplay policy before user gesture
    }
  },
}))
