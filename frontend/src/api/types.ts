import type { components } from './schema'

export type User = components['schemas']['UserResponse']
export type UserSummary = components['schemas']['UserSummaryResponse']
export type MeResponse = components['schemas']['MeResponse']
export type TokenResponse = components['schemas']['TokenResponse']
export type Incident = components['schemas']['IncidentResponse']
export type Signal = components['schemas']['SignalResponse']
export type Camera = components['schemas']['CameraResponse']
export type Zone = components['schemas']['ZoneResponse']
export type Site = components['schemas']['SiteResponse']
export type Organization = components['schemas']['OrgResponse']
export type AnalysisJob = components['schemas']['AnalysisJobResponse']
export type AnalyticsSummary = components['schemas']['AnalyticsSummaryResponse']
export type HeatmapResponse = components['schemas']['HeatmapResponse']
export type PatrolPlanResponse = components['schemas']['PatrolPlanResponse']
export type PatrolPlanItem = components['schemas']['PatrolPlanItem']
export type CalibrationOverview = components['schemas']['CalibrationOverviewResponse']
export type ThresholdHistory = components['schemas']['ThresholdHistoryResponse']
export type AuditLog = components['schemas']['AuditLogResponse']
export type AuditVerifyResponse = components['schemas']['AuditVerifyResponse']
export type PrivacyInventory = components['schemas']['PrivacyInventoryResponse']
export type SOSZoneInfo = components['schemas']['SOSZoneInfoResponse']
export type SOSSubmitResponse = components['schemas']['SOSSubmitResponse']
export type BreakglassResponse = components['schemas']['BreakglassResponse']

export type Role = 'owner' | 'admin' | 'warden' | 'guard' | 'auditor'

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'

export interface ScenarioItem {
  id: string
  name: string
  description: string
  duration_s?: number
  zone?: string
  expected_severity?: string
}

export interface EvidenceAccessInfo {
  incident_id: string
  default_view: 'skeleton' | 'face_blurred' | 'unblurred'
  available_views: Array<'skeleton' | 'blurred' | 'unblurred'>
  skeleton_available: boolean
  blurred_available: boolean
  unblurred_available: boolean
  blurred_locked: boolean
  unblurred_locked: boolean
  blurred_grant_expires_at?: string | null
  unblurred_grant_expires_at?: string | null
  emergency_context_available?: boolean
  emergency_reveal_eligible?: boolean
  pending_identity_reveal_id?: string | null
  can_request_unblurred?: boolean
  intruder_identified_reason?: string | null
}
