import React, { useState, useEffect } from 'react'

export interface CountdownProps {
  targetDate?: string | Date
  secondsLeft?: number
  prefix?: string
  suffix?: string
  className?: string
  onExpire?: () => void
}

export const Countdown: React.FC<CountdownProps> = ({
  targetDate,
  secondsLeft: initialSeconds,
  prefix = '',
  suffix = '',
  className = '',
  onExpire,
}) => {
  const [remaining, setRemaining] = useState<number>(() => {
    if (initialSeconds !== undefined) return initialSeconds
    if (targetDate) {
      const diff = Math.floor((new Date(targetDate).getTime() - Date.now()) / 1000)
      return Math.max(0, diff)
    }
    return 0
  })

  useEffect(() => {
    if (remaining <= 0) {
      if (onExpire) onExpire()
      return
    }

    const timer = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(timer)
          if (onExpire) onExpire()
          return 0
        }
        return prev - 1
      })
    }, 1000)

    return () => clearInterval(timer)
  }, [remaining, onExpire])

  const formatTime = (secs: number) => {
    if (secs <= 60) return `${secs} s`
    const mins = Math.floor(secs / 60)
    const rem = secs % 60
    return `${mins}m ${rem < 10 ? '0' : ''}${rem}s`
  }

  return (
    <span className={`font-mono text-critical ${className}`}>{prefix}{formatTime(remaining)}{suffix}</span>
  )
}
