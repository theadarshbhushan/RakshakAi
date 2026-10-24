import React from 'react'

export interface StatItem {
  label: string
  value: React.ReactNode
  meta?: React.ReactNode
}

export interface StatStripProps {
  stats: StatItem[]
  className?: string
}

export const StatStrip: React.FC<StatStripProps> = ({ stats, className = '' }) => {
  return (
    <div
      className={`bg-card rounded-card border border-border-card shadow-soft grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 divide-y lg:divide-y-0 lg:divide-x divide-border-divider overflow-hidden ${className}`}
    >
      {stats.map((stat, idx) => (
        <div key={idx} className="p-4 sm:p-5 flex flex-col justify-between">
          <p className="text-[13px] font-medium text-content-secondary">{stat.label}</p>
          <div className="mt-2 flex items-baseline gap-2">
            <div className="text-[20px] sm:text-[22px] font-semibold text-content-primary">
              {stat.value}
            </div>
          </div>
          {stat.meta && (
            <div className="mt-1 text-[13px] text-content-muted">
              {stat.meta}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
