import { useState, useEffect } from 'react'

export function useClock() {
  const [time, setTime] = useState<string>('')

  useEffect(() => {
    const formatTime = () => {
      const now = new Date()
      let hours = now.getHours()
      const minutes = now.getMinutes()
      const ampm = hours >= 12 ? 'pm' : 'am'
      hours = hours % 12
      hours = hours ? hours : 12
      const minsStr = minutes < 10 ? '0' + minutes : String(minutes)
      return `${hours}:${minsStr} ${ampm}`
    }

    setTime(formatTime())
    const interval = setInterval(() => {
      setTime(formatTime())
    }, 1000)

    return () => clearInterval(interval)
  }, [])

  return time
}
