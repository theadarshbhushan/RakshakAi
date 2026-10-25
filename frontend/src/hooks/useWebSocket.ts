import { useEffect, useRef, useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useNavigate } from 'react-router-dom'
import { api, getAccessToken, setAccessToken } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { useSoundStore } from '@/store/soundStore'
import { cleanExplanation, getIncidentPlainTitle } from '@/utils/incidentHelpers'

export type ConnectionStatus = 'connected' | 'connecting' | 'reconnecting' | 'disconnected'

export function useWebSocket() {
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const pingIntervalRef = useRef<number | null>(null)
  const isConnectingRef = useRef(false)

  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { isAuthenticated } = useAuthStore()
  const { playAlertChime } = useSoundStore()

  const scheduleReconnect = useCallback((delayMs: number = 3000) => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }

    if (!isAuthenticated) {
      setStatus('disconnected')
      return
    }

    setStatus('reconnecting')
    reconnectTimeoutRef.current = window.setTimeout(async () => {
      if (!isAuthenticated) {
        setStatus('disconnected')
        return
      }

      console.log('[WebSocket] Reconnecting: obtaining fresh token...')
      try {
        const refreshRes = await api.auth.refresh()
        if (refreshRes && refreshRes.access_token) {
          setAccessToken(refreshRes.access_token)
          console.log('[WebSocket] Successfully acquired fresh token')
        }
      } catch (err) {
        console.warn('[WebSocket] Token refresh failed before reconnect:', err)
      }

      connect()
    }, delayMs)
  }, [isAuthenticated])

  const connect = useCallback(async () => {
    if (!isAuthenticated) {
      setStatus('disconnected')
      return
    }

    if (isConnectingRef.current) return
    isConnectingRef.current = true

    let token = getAccessToken()
    if (!token) {
      setStatus('reconnecting')
      try {
        const refreshRes = await api.auth.refresh()
        if (refreshRes && refreshRes.access_token) {
          setAccessToken(refreshRes.access_token)
          token = refreshRes.access_token
        }
      } catch (err) {
        console.warn('[WebSocket] Initial auth refresh failed:', err)
      }
    }

    if (!token) {
      isConnectingRef.current = false
      scheduleReconnect(3000)
      return
    }

    // Clean up any existing connection
    if (wsRef.current) {
      try {
        wsRef.current.onopen = null
        wsRef.current.onmessage = null
        wsRef.current.onerror = null
        wsRef.current.onclose = null
        wsRef.current.close()
      } catch {}
      wsRef.current = null
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws?token=${encodeURIComponent(token)}`

    try {
      console.log('[WebSocket] Connecting to', wsUrl.replace(/token=([^&]+)/, 'token=***'))
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        isConnectingRef.current = false
        console.log('[WebSocket] Connected successfully to /api/v1/ws')
        setStatus('connected')

        // Start ping interval to keep connection alive
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
            case 'camera_health_changed':
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
            case 'identity_reveal.requested':
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

      ws.onclose = (event) => {
        isConnectingRef.current = false
        console.warn(`[WebSocket] Closed: code=${event.code}, reason="${event.reason}"`)
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current)

        if (isAuthenticated) {
          scheduleReconnect(3000)
        } else {
          setStatus('disconnected')
        }
      }

      ws.onerror = (error) => {
        isConnectingRef.current = false
        console.error('[WebSocket] Error event caught:', error)
        try {
          ws.close()
        } catch {}
      }
    } catch (err) {
      isConnectingRef.current = false
      console.error('[WebSocket] Failed to instantiate WebSocket:', err)
      scheduleReconnect(3000)
    }
  }, [isAuthenticated, playAlertChime, queryClient, navigate, scheduleReconnect])

  useEffect(() => {
    if (isAuthenticated) {
      connect()
    } else {
      if (wsRef.current) {
        try {
          wsRef.current.close()
        } catch {}
        wsRef.current = null
      }
      setStatus('disconnected')
    }

    return () => {
      if (wsRef.current) {
        try {
          wsRef.current.close()
        } catch {}
        wsRef.current = null
      }
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current)
    }
  }, [isAuthenticated, connect])

  return { status, reconnect: connect }
}
