import React from 'react'
import { AlertCircle } from 'lucide-react'
import { Button } from './Button'

export interface ErrorStateProps {
  title?: string
  message: string
  onRetry?: () => void
  className?: string
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Something went wrong',
  message,
  onRetry,
  className = '',
}) => {
  return (
    <div
      className={`p-8 text-center flex flex-col items-center justify-center rounded-card border border-critical-border bg-critical-tint ${className}`}
    >
      <div className="text-critical mb-2">
        <AlertCircle size={28} />
      </div>
      <h3 className="text-[16px] font-semibold text-critical">{title}</h3>
      <p className="text-[13px] text-content-body max-w-md mt-1 mb-4">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}
