import React from 'react'

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
  padding?: 'none' | 'sm' | 'md' | 'lg'
}

export const Card: React.FC<CardProps> = ({
  children,
  padding = 'md',
  className = '',
  ...props
}) => {
  const paddingStyles = {
    none: '',
    sm: 'p-3.5',
    md: 'p-5',
    lg: 'p-6',
  }[padding]

  return (
    <div
      className={`bg-card rounded-card border border-border-card shadow-soft ${paddingStyles} ${className}`}
      {...props}
    >
      {children}
    </div>
  )
}
