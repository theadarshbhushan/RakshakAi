import type {
  User,
  MeResponse,
  TokenResponse,
  Incident,
  Signal,
  Camera,
  Zone,
  Site,
  Organization,
  AnalysisJob,
  AnalyticsSummary,
  HeatmapResponse,
  PatrolPlanResponse,
  CalibrationOverview,
  AuditLog,
  AuditVerifyResponse,
  PrivacyInventory,
  SOSZoneInfo,
  SOSSubmitResponse,
  BreakglassResponse,
  EvidenceAccessInfo,
} from './types'

let inMemoryToken: string | null = null

export const getAccessToken = () => inMemoryToken
export const setAccessToken = (token: string | null) => {
  inMemoryToken = token
}

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined | null>
}

let isRefreshing = false
let refreshSubscribers: ((token: string | null) => void)[] = []

const subscribeTokenRefresh = (cb: (token: string | null) => void) => {
  refreshSubscribers.push(cb)
}

const onRefreshed = (token: string | null) => {
  refreshSubscribers.forEach((cb) => cb(token))
  refreshSubscribers = []
}

export async function apiFetch<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, headers = {}, ...rest } = options

  let url = endpoint
  if (params) {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null) {
        searchParams.append(key, String(val))
      }
    })
    const queryString = searchParams.toString()
    if (queryString) {
      url += (url.includes('?') ? '&' : '?') + queryString
    }
  }

  const reqHeaders: Record<string, string> = {
    Accept: 'application/json',
    ...(headers as Record<string, string>),
  }

  if (inMemoryToken && !reqHeaders['Authorization']) {
    reqHeaders['Authorization'] = `Bearer ${inMemoryToken}`
  }

  const isFormData = rest.body instanceof FormData
  if (!isFormData && !reqHeaders['Content-Type'] && rest.body) {
    reqHeaders['Content-Type'] = 'application/json'
  }

  let response = await fetch(url, {
    ...rest,
    headers: reqHeaders,
    credentials: 'include',
  })

  // Handle 401 Auto-refresh
  if (response.status === 401 && !endpoint.includes('/auth/login') && !endpoint.includes('/auth/refresh')) {
    if (!isRefreshing) {
      isRefreshing = true
      try {
        const refreshRes = await fetch('/api/v1/auth/refresh', {
          method: 'POST',
          credentials: 'include',
          headers: { Accept: 'application/json' },
        })

        if (refreshRes.ok) {
          const data: TokenResponse = await refreshRes.json()
          setAccessToken(data.access_token)
          isRefreshing = false
          onRefreshed(data.access_token)
        } else {
          setAccessToken(null)
          isRefreshing = false
          onRefreshed(null)
          throw new Error('Session expired. Please log in again.')
        }
      } catch (err) {
        setAccessToken(null)
        isRefreshing = false
        onRefreshed(null)
        throw err
      }
    } else {
      // Wait for existing refresh to resolve
      await new Promise<string | null>((resolve) => {
        subscribeTokenRefresh(resolve)
      })
    }

    // Retry original request with new token
    if (inMemoryToken) {
      reqHeaders['Authorization'] = `Bearer ${inMemoryToken}`
      response = await fetch(url, {
        ...rest,
        headers: reqHeaders,
        credentials: 'include',
      })
    }
  }

  if (!response.ok) {
    let errorDetail = 'An error occurred'
    try {
      const errJson = await response.json()
      errorDetail = errJson.error?.message || errJson.detail || JSON.stringify(errJson)
    } catch {
      errorDetail = `${response.status} ${response.statusText}`
    }
    throw new Error(errorDetail)
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T
  }

  return response.json()
}

export async function apiFetchBlob(endpoint: string, options: RequestOptions = {}): Promise<Blob> {
  const { params, headers = {}, ...rest } = options

  let url = endpoint
  if (params) {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null) {
        searchParams.append(key, String(val))
      }
    })
    const queryString = searchParams.toString()
    if (queryString) {
      url += (url.includes('?') ? '&' : '?') + queryString
    }
  }

  const reqHeaders: Record<string, string> = {
    Accept: 'image/*, */*',
    ...(headers as Record<string, string>),
  }

  if (inMemoryToken && !reqHeaders['Authorization']) {
    reqHeaders['Authorization'] = `Bearer ${inMemoryToken}`
  }

  let response = await fetch(url, {
    ...rest,
    headers: reqHeaders,
    credentials: 'include',
  })

  // Handle 401 Auto-refresh
  if (response.status === 401) {
    try {
      const refreshRes = await fetch('/api/v1/auth/refresh', {
        method: 'POST',
        credentials: 'include',
        headers: { Accept: 'application/json' },
      })
      if (refreshRes.ok) {
        const data: TokenResponse = await refreshRes.json()
        setAccessToken(data.access_token)
        reqHeaders['Authorization'] = `Bearer ${data.access_token}`
        response = await fetch(url, {
          ...rest,
          headers: reqHeaders,
          credentials: 'include',
        })
      }
    } catch {}
  }

  if (!response.ok) {
    let errorDetail = 'Failed to fetch resource'
    try {
      const errJson = await response.json()
      errorDetail = errJson.error?.message || errJson.detail || JSON.stringify(errJson)
    } catch {
      errorDetail = `${response.status} ${response.statusText}`
    }
    throw new Error(errorDetail)
  }

  return response.blob()
}

export const api = {
  // Auth
  auth: {
    login: (data: { email: string; password: string }) =>
      apiFetch<TokenResponse>('/api/v1/auth/login', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    refresh: () =>
      apiFetch<TokenResponse>('/api/v1/auth/refresh', {
        method: 'POST',
      }),
    logout: () =>
      apiFetch<{ message: string }>('/api/v1/auth/logout', {
        method: 'POST',
      }),
    logoutAll: () =>
      apiFetch<{ message: string }>('/api/v1/auth/logout-all', {
        method: 'POST',
      }),
    me: () => apiFetch<MeResponse>('/api/v1/auth/me'),
    changePassword: (data: { old_password: string; new_password: string }) =>
      apiFetch<{ message: string }>('/api/v1/auth/change-password', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    registerOrg: (data: any) =>
      apiFetch<Organization>('/api/v1/auth/register-organization', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
  },

  // Incidents
  incidents: {
    list: (params?: {
      severity?: string
      status?: string
      zone?: string
      date_from?: string
      date_to?: string
      skip?: number
      limit?: number
    }) =>
      apiFetch<{ items: Incident[]; total: number; skip: number; limit: number }>(
        '/api/v1/incidents',
        { params }
      ),
    get: (id: string) => apiFetch<Incident>(`/api/v1/incidents/${id}`),
    acknowledge: (id: string, data?: { notes?: string }) =>
      apiFetch<Incident>(`/api/v1/incidents/${id}/ack`, {
        method: 'POST',
        body: JSON.stringify(data || {}),
      }),
    review: (
      id: string,
      data: {
        outcome: 'confirmed' | 'false_positive' | 'investigating'
        notes: string
      }
    ) =>
      apiFetch<Incident>(`/api/v1/incidents/${id}/review`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
  },

  // Signals
  signals: {
    list: (params?: {
      incident_id?: string
      camera_id?: string
      zone?: string
      modality?: string
      kind?: string
      skip?: number
      limit?: number
    }) =>
      apiFetch<{ items: Signal[]; total: number; skip: number; limit: number }>(
        '/api/v1/signals',
        { params }
      ),
    getEvidence: (signalId: string) =>
      apiFetch<any>(`/api/v1/evidence/${signalId}`),
  },

  // Cameras
  cameras: {
    list: () => apiFetch<Camera[]>('/api/v1/cameras'),
    create: (data: any) =>
      apiFetch<Camera>('/api/v1/cameras', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    updateHealth: (cameraId: string, data: { status: string; reason?: string }) =>
      apiFetch<Camera>(`/api/v1/cameras/${cameraId}/health`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    getStreamUrl: (cameraId: string, mode: 'skeleton' | 'blurred' | 'emergency' = 'skeleton') => {
      const token = getAccessToken()
      return `/api/v1/stream/${cameraId}?mode=${mode}${token ? `&token=${encodeURIComponent(token)}` : ''}`
    },
  },

  // Scenarios
  scenarios: {
    list: () => apiFetch<any[]>('/api/v1/scenarios'),
    play: (scenarioId: string, speed: number = 1) =>
      apiFetch<{ message: string; scenario_id: string; speed: number }>(
        `/api/v1/scenarios/${scenarioId}/play`,
        {
          method: 'POST',
          params: { speed },
        }
      ),
    stop: () =>
      apiFetch<{ message: string }>('/api/v1/scenarios/stop', {
        method: 'POST',
      }),
    reset: (includeHistory: boolean = false) =>
      apiFetch<{ message: string; deleted_incidents: number; deleted_signals: number }>(
        `/api/v1/scenarios/reset`,
        {
          method: 'POST',
          params: { include_history: includeHistory },
        }
      ),
  },

  // Analyze
  analyze: {
    upload: (formData: FormData) =>
      apiFetch<AnalysisJob>('/api/v1/analyze/upload', {
        method: 'POST',
        body: formData,
      }),
    listJobs: (params?: { skip?: number; limit?: number }) =>
      apiFetch<{ items: AnalysisJob[]; total: number }>('/api/v1/analyze/jobs', { params }),
    getJob: (jobId: string) => apiFetch<AnalysisJob>(`/api/v1/analyze/jobs/${jobId}`),
    deleteJob: (jobId: string) =>
      apiFetch<{ message: string }>(`/api/v1/analyze/jobs/${jobId}`, {
        method: 'DELETE',
      }),
    getAnnotatedUrl: (jobId: string, mode: 'skeleton' | 'blurred' = 'skeleton', token?: string) => {
      const accessToken = getAccessToken()
      const searchParams = new URLSearchParams()
      searchParams.append('mode', mode)
      if (token) searchParams.append('token', token)
      if (accessToken) searchParams.append('auth_token', accessToken)
      return `/api/v1/analyze/jobs/${jobId}/annotated?${searchParams.toString()}`
    },
    startLive: (data: { camera_id: string; rtmp_url?: string }) =>
      apiFetch<{ message: string; camera_id: string }>('/api/v1/analyze/live', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    stopLive: (cameraId: string) =>
      apiFetch<{ message: string }>(`/api/v1/analyze/live/${cameraId}/stop`, {
        method: 'POST',
      }),
  },

  // Evidence & Privacy Access
  evidence: {
    getAccess: (incidentId: string) =>
      apiFetch<EvidenceAccessInfo>(`/api/v1/evidence/incident/${incidentId}/access`),
    getEvidence: (incidentId: string) =>
      apiFetch<any>(`/api/v1/evidence/incident/${incidentId}`),
    getVideoUrl: (
      incidentId: string,
      options: { tier?: 'skeleton' | 'blurred' | 'raw'; variant?: 'targeted' | 'full'; token?: string } = {}
    ) => {
      const { tier = 'skeleton', variant = 'targeted', token } = options
      const accessToken = getAccessToken()
      const searchParams = new URLSearchParams()
      if (tier) searchParams.append('tier', tier)
      if (variant) searchParams.append('variant', variant)
      if (token) searchParams.append('token', token)
      if (accessToken) searchParams.append('auth_token', accessToken)
      return `/api/v1/evidence/incident/${incidentId}?${searchParams.toString()}`
    },
    exportPolice: (incidentId: string) =>
      apiFetch<{ download_url?: string; chain_of_custody_hash: string; message: string }>(
        `/api/v1/evidence/incident/${incidentId}/export`,
        { method: 'POST' }
      ),
  },

  privacy: {
    breakglass: (data: { incident_id?: string; job_id?: string; reason: string }) =>
      apiFetch<BreakglassResponse>('/api/v1/privacy/breakglass', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    requestIdentityReveal: (data: { incident_id: string; reason: string }) =>
      apiFetch<{ id: string; incident_id: string; status: string; message: string }>(
        '/api/v1/privacy/identity-reveal',
        {
          method: 'POST',
          body: JSON.stringify(data),
        }
      ),
    listIdentityReveals: (status?: string) =>
      apiFetch<any[]>('/api/v1/privacy/identity-reveal', {
        params: { status },
      }),
    approveIdentityReveal: (requestId: string, note?: string) =>
      apiFetch<any>(`/api/v1/privacy/identity-reveal/${requestId}/approve`, {
        method: 'POST',
        body: JSON.stringify({ note }),
      }),
    denyIdentityReveal: (requestId: string, note?: string) =>
      apiFetch<any>(`/api/v1/privacy/identity-reveal/${requestId}/deny`, {
        method: 'POST',
        body: JSON.stringify({ note }),
      }),
    emergencyReveal: (data: { incident_id: string; reason: string }) =>
      apiFetch<{
        id: string
        incident_id: string
        expires_at: string
        flagged_track_ids: string[]
        review_status: string
        message: string
      }>('/api/v1/privacy/emergency-reveal', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    listEmergencyReveals: (review?: string) =>
      apiFetch<any[]>('/api/v1/privacy/emergency-reveal', {
        params: { review },
      }),
    reviewEmergencyReveal: (revealId: string, data: { status: 'justified' | 'not_justified'; note: string }) =>
      apiFetch<any>(`/api/v1/privacy/emergency-reveal/${revealId}/review`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    getSettings: () => apiFetch<any>('/api/v1/privacy/settings'),
    updateSettings: (data: { default_evidence_view?: 'skeleton' | 'blurred'; retention_days?: number; retention_days_confirmed?: number }) =>
      apiFetch<any>('/api/v1/privacy/settings', {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
    getInventory: () => apiFetch<PrivacyInventory>('/api/v1/privacy/inventory'),
    purge: (data: { target_date?: string; confirmation: string }) =>
      apiFetch<{ message: string; deleted_records: number }>('/api/v1/privacy/purge', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    getTransparency: () => apiFetch<any>('/api/v1/privacy/transparency'),
  },

  // Analytics & Patrol
  analytics: {
    getHeatmap: (days: number = 30) =>
      apiFetch<HeatmapResponse>('/api/v1/analytics/heatmap', {
        params: { days },
      }),
    getPatrolPlan: () => apiFetch<PatrolPlanResponse>('/api/v1/analytics/patrol-plan'),
    getSummary: () => apiFetch<AnalyticsSummary>('/api/v1/analytics/summary'),
  },

  // Calibration
  calibration: {
    getOverview: () => apiFetch<CalibrationOverview>('/api/v1/calibration'),
    revert: (historyId: string) =>
      apiFetch<{ message: string; restored_threshold: number }>(
        `/api/v1/calibration/${historyId}/revert`,
        { method: 'POST' }
      ),
  },

  // Evaluation
  eval: {
    getResults: () => apiFetch<any>('/api/v1/eval/results'),
    run: () => apiFetch<{ task_id: string; status: string; message: string }>('/api/v1/eval/run', {
      method: 'POST',
    }),
  },

  // Audit
  audit: {
    list: (params?: {
      action?: string
      user_id?: string
      skip?: number
      limit?: number
    }) =>
      apiFetch<{ items: AuditLog[]; total: number; skip: number; limit: number }>(
        '/api/v1/audit',
        { params }
      ),
    verify: () => apiFetch<AuditVerifyResponse>('/api/v1/audit/verify'),
  },

  // Rules & Zones & Sites
  rules: {
    get: () => apiFetch<any>('/api/v1/rules'),
    update: (data: any) =>
      apiFetch<any>('/api/v1/rules', {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
  },
  zones: {
    list: () => apiFetch<Zone[]>('/api/v1/zones'),
    get: (id: string) => apiFetch<Zone>(`/api/v1/zones/${id}`),
    create: (data: any) =>
      apiFetch<Zone>('/api/v1/zones', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    update: (id: string, data: any) =>
      apiFetch<Zone>(`/api/v1/zones/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
  },
  sites: {
    list: () => apiFetch<Site[]>('/api/v1/sites'),
    create: (data: any) =>
      apiFetch<Site>('/api/v1/sites', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
  },
  org: {
    get: () => apiFetch<Organization>('/api/v1/org'),
    updatePlan: (data: { plan: string }) =>
      apiFetch<Organization>('/api/v1/org/plan', {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
  },
  users: {
    list: () => apiFetch<User[]>('/api/v1/users'),
    update: (id: string, data: any) =>
      apiFetch<User>(`/api/v1/users/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    delete: (id: string) =>
      apiFetch<{ message: string }>(`/api/v1/users/${id}`, {
        method: 'DELETE',
      }),
  },

  // Student SOS (public & admin)
  sos: {
    getInfo: (token: string) => apiFetch<SOSZoneInfo>(`/api/v1/sos/${token}/info`),
    submit: (
      token: string,
      data: {
        category: string
        note?: string
      }
    ) =>
      apiFetch<SOSSubmitResponse>(`/api/v1/sos/${token}`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    getQr: (zoneId: string) => apiFetch<any>(`/api/v1/sos/qr/${zoneId}`),
    getZoneQrBlob: (zoneId: string) => apiFetchBlob(`/api/v1/sos/qr/${encodeURIComponent(zoneId)}`),
    getQrSheet: () => apiFetch<any>('/api/v1/sos/qr-sheet'),
    rotate: (zoneId: string) =>
      apiFetch<{ zone_id: string; new_token: string }>(`/api/v1/sos/rotate/${zoneId}`, {
        method: 'POST',
      }),
  },
}
