import React from 'react'

export interface EmptyStateProps {
  title: string
  description?: string
  icon?: React.ReactNode
  action?: React.ReactNode
  className?: string
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  icon,
  action,
  className = '',
}) => {
  return (
    <div
      className={`p-10 text-center flex flex-col items-center justify-center rounded-card border border-dashed border-border-card bg-fill-subtle/50 ${className}`}
    >
      {icon && <div className="text-content-muted mb-3.5">{icon}</div>}
      <h3 className="text-[16px] font-semibold text-content-primary">{title}</h3>
      {description && (
        <p className="text-[13px] text-content-secondary max-w-sm mt-1 mb-4 leading-relaxed">
          {description}
        </p>
      )}
      {action && <div className="mt-1">{action}</div>}
    </div>
  )
}
