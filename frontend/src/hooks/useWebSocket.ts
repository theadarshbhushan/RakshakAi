import { useEffect, useRef, useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useNavigate } from 'react-router-dom'
import { api, getAccessToken, setAccessToken } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { useSoundStore } from '@/store/soundStore'
import { cleanExplanation, getIncidentPlainTitle } from '@/utils/incidentHelpers'

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

  const connect = useCallback(async () => {
    if (!isAuthenticated) return

    let token = getAccessToken()
    if (!token) {
      try {
        const refreshRes = await api.auth.refresh()
        if (refreshRes && refreshRes.access_token) {
          setAccessToken(refreshRes.access_token)
          token = refreshRes.access_token
        }
      } catch (err) {
        console.warn('WS auth refresh failed:', err)
        return
      }
    }

    if (!token) return

    // Clear existing
    if (wsRef.current) {
      try {
        wsRef.current.close()
      } catch {}
      wsRef.current = null
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
              queryClient.invalidateQueries({ queryKey: ['signals'] })

              const severity = (data?.severity || 'high').toLowerCase()
              playAlertChime(severity)
              const title =
                cleanExplanation(data?.title_human) ||
                getIncidentPlainTitle(data) ||
                cleanExplanation(data?.explanation_paragraph) ||
                'New safety incident reported'
              const zone = data?.zone_id ? data.zone_id.replace(/_/g, ' ') : 'Zone'

              toast.error(`${severity === 'critical' ? 'Critical' : 'Alert'} · ${zone}`, {
                description: title,
                action: {
                  label: 'Review now',
                  onClick: () => navigate(`/app/incidents/${data?.id || data?._id}`),
                },
                duration: 8000,
              })
              break
            }

            case 'incident_updated':
            case 'incident_reviewed':
            case 'incident_acknowledged':
              queryClient.invalidateQueries({ queryKey: ['incidents'] })
              if (data?.id || data?._id) {
                queryClient.invalidateQueries({ queryKey: ['incident', data.id || data._id] })
              }
              queryClient.invalidateQueries({ queryKey: ['analytics'] })
              break

            case 'signal_new':
              queryClient.invalidateQueries({ queryKey: ['signals'] })
              break

            case 'camera_status':
            case 'camera_tamper':
              queryClient.invalidateQueries({ queryKey: ['cameras'] })
              if (data?.status === 'tampered' || data?.is_blind_spot) {
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
          if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
          reconnectTimeoutRef.current = window.setTimeout(async () => {
            try {
              // Refresh token before reconnecting
              const res = await api.auth.refresh()
              if (res?.access_token) {
                setAccessToken(res.access_token)
              }
            } catch (err) {
              console.warn('WS token refresh error:', err)
            }
            connect()
          }, timeout)
        }
      }

      ws.onerror = () => {
        try {
          ws.close()
        } catch {}
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
