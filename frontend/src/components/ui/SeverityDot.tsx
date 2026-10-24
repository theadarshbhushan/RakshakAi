import React from 'react'

export interface SeverityDotProps {
  severity: 'critical' | 'high' | 'medium' | 'low' | 'healthy' | 'info' | string
  showText?: boolean
  pulse?: boolean
  className?: string
}

export const SeverityDot: React.FC<SeverityDotProps> = ({
  severity,
  showText = true,
  pulse = false,
  className = '',
}) => {
  const norm = severity.toLowerCase()

  const config = {
    critical: {
      color: 'bg-critical',
      textColor: 'text-critical',
      label: 'Critical',
    },
    high: {
      color: 'bg-status-high',
      textColor: 'text-status-high',
      label: 'High',
    },
    medium: {
      color: 'bg-status-medium',
      textColor: 'text-status-medium',
      label: 'Medium',
    },
    low: {
      color: 'bg-status-low',
      textColor: 'text-status-low',
      label: 'Low',
    },
    healthy: {
      color: 'bg-status-healthy',
      textColor: 'text-status-healthy',
      label: 'Healthy',
    },
    info: {
      color: 'bg-status-low',
      textColor: 'text-status-low',
      label: 'Info',
    },
  }[norm] || {
    color: 'bg-content-muted',
    textColor: 'text-content-muted',
    label: severity,
  }

  return (
    <span className={`inline-flex items-center gap-1.5 text-[13px] font-medium ${config.textColor} ${className}`}>
      <span
        className={`w-2 h-2 rounded-full shrink-0 ${config.color} ${
          pulse || norm === 'critical' ? 'animate-critical-pulse' : ''
        }`}
      />
      {showText && <span>{config.label}</span>}
    </span>
  )
}
