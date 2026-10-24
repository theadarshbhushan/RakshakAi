import React from 'react'

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'subtle'
  size?: 'sm' | 'md' | 'lg'
  isLoading?: boolean
  icon?: React.ReactNode
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      children,
      variant = 'primary',
      size = 'md',
      isLoading = false,
      icon,
      disabled,
      className = '',
      ...props
    },
    ref
  ) => {
    const baseStyles =
      'inline-flex items-center justify-center font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-50 disabled:cursor-not-allowed select-none'

    const sizeStyles = {
      sm: 'text-[13px] px-3 py-1.5 rounded-btn gap-1.5',
      md: 'text-[14px] px-4 py-2 rounded-btn gap-2',
      lg: 'text-[15px] px-5 py-2.5 rounded-btn gap-2.5',
    }[size]

    const variantStyles = {
      primary: 'bg-primary text-white hover:bg-primary-hover active:bg-primary-hover/90 shadow-soft',
      secondary:
        'bg-card text-content-primary border border-border-input hover:bg-fill-subtle active:bg-fill-active shadow-soft',
      danger:
        'bg-critical-danger text-white hover:bg-critical-danger/90 active:bg-critical-danger/95 shadow-soft',
      ghost: 'bg-transparent text-content-secondary hover:text-content-primary hover:bg-fill-subtle',
      subtle: 'bg-primary-tint text-primary hover:bg-primary-tint-strong',
    }[variant]

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={`${baseStyles} ${sizeStyles} ${variantStyles} ${className}`}
        {...props}
      >
        {isLoading ? (
          <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
        ) : (
          icon && <span className="shrink-0">{icon}</span>
        )}
        {children}
      </button>
    )
  }
)

Button.displayName = 'Button'
