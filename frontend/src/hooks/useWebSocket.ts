import { useEffect, useRef, useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useNavigate } from 'react-router-dom'
import { getAccessToken } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { useSoundStore } from '@/store/soundStore'

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected'

export function useWebSocket() {
  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const pingIntervalRef = useRef<number | null>(null)
  const retryCountRef = useRef(0)

  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { isAuthenticated } = useAuthStore()
  const { playAlertChime } = useSoundStore()

  const connect = useCallback(() => {
    if (!isAuthenticated) return

    const token = getAccessToken()
    if (!token) return

    // Clear existing
    if (wsRef.current) {
      wsRef.current.close()
    }

    setStatus('connecting')
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws?token=${encodeURIComponent(token)}`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setStatus('connected')
        retryCountRef.current = 0

        // Start ping interval
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current)
        pingIntervalRef.current = window.setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping')
          }
        }, 25000)
      }

      ws.onmessage = (event) => {
        if (event.data === 'pong') return

        try {
          const payload = JSON.parse(event.data)
          const { type, data } = payload

          switch (type) {
            case 'incident_new':
            case 'incident_escalated': {
              queryClient.invalidateQueries({ queryKey: ['incidents'] })
              queryClient.invalidateQueries({ queryKey: ['analytics'] })

              const severity = data.severity?.toLowerCase() || 'medium'
              if (severity === 'critical' || severity === 'high') {
                playAlertChime(severity)
                const title = data.title_human || data.explanation_paragraph || 'New safety incident reported'
                const zone = data.zone_id ? data.zone_id.replace(/_/g, ' ') : 'Zone'
                
                toast.error(`${severity === 'critical' ? 'Critical' : 'High priority'} · ${zone}`, {
                  description: title,
                  action: {
                    label: 'Review now',
                    onClick: () => navigate(`/incidents/${data.id || data._id}`),
                  },
                  duration: 8000,
                })
              }
              break
            }

            case 'incident_updated':
            case 'incident_reviewed':
            case 'incident_acknowledged':
              queryClient.invalidateQueries({ queryKey: ['incidents'] })
              queryClient.invalidateQueries({ queryKey: ['incident', data.id || data._id] })
              queryClient.invalidateQueries({ queryKey: ['analytics'] })
              break

            case 'signal_new':
              queryClient.invalidateQueries({ queryKey: ['signals'] })
              break

            case 'camera_status':
            case 'camera_tamper':
              queryClient.invalidateQueries({ queryKey: ['cameras'] })
              if (data.status === 'tampered' || data.is_blind_spot) {
                playAlertChime('high')
                toast.warning(`Camera blind spot · ${data.name || data.camera_id}`, {
                  description: 'Camera video is degraded or covered. Audio sensitivity automatically raised.',
                })
              }
              break

            case 'analysis_progress':
            case 'analysis_complete':
              queryClient.invalidateQueries({ queryKey: ['analyze_jobs'] })
              break

            case 'privacy_request':
              queryClient.invalidateQueries({ queryKey: ['approvals'] })
              break

            default:
              // Broad refresh for general events
              queryClient.invalidateQueries({ queryKey: ['incidents'] })
              break
          }
        } catch {
          // Non-JSON frame (e.g. keep-alive text)
        }
      }

      ws.onclose = () => {
        setStatus('disconnected')
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current)

        // Exponential backoff reconnect
        if (isAuthenticated) {
          const timeout = Math.min(1000 * Math.pow(1.5, retryCountRef.current), 10000)
          retryCountRef.current += 1
          reconnectTimeoutRef.current = window.setTimeout(() => {
            connect()
          }, timeout)
        }
      }

      ws.onerror = () => {
        ws.close()
      }
    } catch {
      setStatus('disconnected')
    }
  }, [isAuthenticated, playAlertChime, queryClient, navigate])

  useEffect(() => {
    if (isAuthenticated) {
      connect()
    } else {
      if (wsRef.current) wsRef.current.close()
      setStatus('disconnected')
    }

    return () => {
      if (wsRef.current) wsRef.current.close()
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current)
    }
  }, [isAuthenticated, connect])

  return { status, reconnect: connect }
}
