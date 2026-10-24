import type { Incident } from '@/api/types'

/**
 * Returns a friendly greeting based on local time:
 * - 5am - 12pm: Good morning
 * - 12pm - 5pm: Good afternoon
 * - 5pm - 10pm: Good evening
 * - 10pm - 5am: Working late
 */
export function getLocalGreeting(date: Date = new Date()): string {
  const hour = date.getHours()
  if (hour >= 5 && hour < 12) {
    return 'Good morning'
  }
  if (hour >= 12 && hour < 17) {
    return 'Good afternoon'
  }
  if (hour >= 17 && hour < 22) {
    return 'Good evening'
  }
  return 'Working late'
}

/**
 * Extracts a person's first name, or defaults to the role if there is no real name.
 * Handles generic accounts like "Hostel Owner" -> "Warden" or "Chief Warden / Owner" -> "Warden".
 */
export function getGreetingName(user?: { full_name?: string | null; role?: string | null } | null): string {
  const roleTitle = user?.role
    ? user.role.charAt(0).toUpperCase() + user.role.slice(1)
    : 'Warden'
  const fallbackRole = user?.role === 'owner' ? 'Warden' : roleTitle

  if (!user || !user.full_name) {
    return fallbackRole
  }

  const rawName = user.full_name.trim()

  // Words that indicate an organizational title or role rather than a person's first name
  const genericTitles = [
    'hostel',
    'chief',
    'security',
    'sunrise',
    'green',
    'valley',
    'admin',
    'administrator',
    'owner',
    'warden',
    'guard',
    'auditor',
    'staff',
    'user',
    'system',
  ]

  const firstWord = rawName.split(/[\s/]+/)[0]

  if (genericTitles.includes(firstWord.toLowerCase())) {
    return fallbackRole
  }

  return firstWord
}

/**
 * Map of zone IDs to human-readable names.
 */
export const ZONE_NAMES: Record<string, string> = {
  terrace: 'Terrace Rooftop',
  block_b_entry: 'Block B Entry',
  corridor_2f: '2nd Floor Corridor',
  common_room: 'Common Room',
  mess_hall: 'Mess Hall & Dining',
  ground_floor: 'Ground Floor Lobby',
}

/**
 * Formats a zone ID into a natural-sounding English noun phrase.
 */
export function formatZoneNoun(zoneId?: string): string {
  if (!zoneId) return 'the campus'
  const z = zoneId.toLowerCase()
  if (z === 'terrace') return 'the terrace'
  if (z === 'block_b_entry') return 'Block B entry'
  if (z === 'corridor_2f') return 'the 2nd floor corridor'
  if (z === 'common_room') return 'the common room'
  return zoneId.replace(/_/g, ' ')
}

/**
 * Formats a zone ID into a clean display title (e.g. "terrace" -> "Terrace Rooftop").
 */
export function formatZoneDisplayName(zoneId?: string | null): string {
  if (!zoneId) return 'Terrace Rooftop'
  const cleanId = zoneId.toLowerCase().trim()
  if (ZONE_NAMES[cleanId]) {
    return ZONE_NAMES[cleanId]
  }
  return zoneId
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

/**
 * Map of signal kinds to human-readable names.
 */
export const SIGNAL_KIND_NAMES: Record<string, string> = {
  fight: 'Possible fight',
  distress_audio: 'Distress audio',
  zone_intrusion: 'Zone intrusion',
  loitering: 'Unusual loitering',
  tailgating: 'Tailgating event',
  student_sos: 'Student SOS',
  restricted_access: 'Restricted access entry',
  camera_tamper: 'Camera tamper / blind spot',
  curfew_violation: 'Curfew violation',
}

/**
 * Formats a signal kind into a clean human name (e.g. "fight" -> "Possible fight").
 */
export function formatSignalKindName(kind?: string | null): string {
  if (!kind) return 'Sensor signal'
  const clean = kind.toLowerCase().trim()
  if (SIGNAL_KIND_NAMES[clean]) {
    return SIGNAL_KIND_NAMES[clean]
  }
  return clean
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

/**
 * Cleans up stray broken punctuation like ".," or ". ," or double spaces.
 */
export function cleanExplanation(text?: string | null): string {
  if (!text) return ''
  return text
    .replace(/\.\s*,\s*/g, ', ')
    .replace(/,\s*\./g, '.')
    .replace(/\.{2,}/g, '.')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

/**
 * Constructs a short plain-language title from an incident's zone and signal kinds/modalities.
 * Example: "Someone entered the terrace after curfew, and a scream was heard"
 */
export function getIncidentPlainTitle(incident?: Incident | null): string {
  if (!incident) return 'Safety incident reported'

  // If a clean human title is already explicitly provided
  if ((incident as any).title_human) {
    return cleanExplanation((incident as any).title_human)
  }

  const exp = (incident.explanation || '').toLowerCase()
  const zoneName = formatZoneNoun(incident.zone_id)
  const mods = incident.modalities || []

  const hasAudio =
    mods.includes('audio') ||
    exp.includes('scream') ||
    exp.includes('distress') ||
    exp.includes('audio') ||
    exp.includes('screaming')

  const hasVideo =
    mods.includes('video') ||
    exp.includes('person') ||
    exp.includes('entering') ||
    exp.includes('fight') ||
    exp.includes('loitering')

  const hasAccess =
    mods.includes('access') ||
    exp.includes('swipe') ||
    exp.includes('door') ||
    exp.includes('curfew')

  const hasSos = mods.includes('sos') || exp.includes('sos')

  // Check specific corroborations and kinds:
  if (hasSos) {
    return `Emergency student SOS reported in ${zoneName}`
  }

  if (
    (exp.includes('scream') || exp.includes('distress')) &&
    (hasAccess || exp.includes('curfew') || exp.includes('entering') || exp.includes('terrace'))
  ) {
    return `Someone entered ${zoneName} after curfew, and a scream was heard`
  }

  if (exp.includes('fight') || exp.includes('altercation')) {
    return `Physical altercation detected in ${zoneName}`
  }

  if (exp.includes('tailgating')) {
    return `Unauthorized tailgating detected at ${zoneName}`
  }

  if (exp.includes('loitering')) {
    return `Unusual loitering detected in ${zoneName} during curfew`
  }

  if (exp.includes('screaming') || exp.includes('scream')) {
    return `A distress scream was detected in ${zoneName}`
  }

  if (exp.includes('tamper')) {
    return `Camera tampering detected in ${zoneName}`
  }

  if (exp.includes('restricted')) {
    return `Unauthorized entry into restricted area in ${zoneName}`
  }

  if (hasAudio && hasVideo && hasAccess) {
    return `Intrusion and distress audio corroborated in ${zoneName}`
  }

  if (hasAudio && hasVideo) {
    return `Visual movement and distress sounds corroborated in ${zoneName}`
  }

  if (hasAccess && hasVideo) {
    return `Door access and movement detected in ${zoneName}`
  }

  if (hasVideo) {
    return `Restricted movement detected in ${zoneName}`
  }

  if (hasAudio) {
    return `Distress audio detected in ${zoneName}`
  }

  return `Safety incident reported in ${zoneName}`
}
