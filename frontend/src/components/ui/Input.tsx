import React from 'react'

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, className = '', id, ...props }, ref) => {
    const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined)

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={inputId} className="block text-[13px] font-medium text-content-body mb-1.5">
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={`w-full px-3.5 py-2 text-[14px] bg-card text-content-primary placeholder:text-content-muted border border-border-input rounded-input focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors disabled:bg-fill-subtle disabled:text-content-muted ${
            error ? 'border-critical focus:border-critical focus:ring-critical/10' : ''
          } ${className}`}
          {...props}
        />
        {hint && !error && <p className="text-[12px] text-content-muted mt-1">{hint}</p>}
        {error && <p className="text-[12px] text-critical mt-1">{error}</p>}
      </div>
    )
  }
)

Input.displayName = 'Input'
