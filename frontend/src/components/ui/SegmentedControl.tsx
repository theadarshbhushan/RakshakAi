import React from 'react'

export interface SegmentOption<T extends string> {
  value: T
  label: string
  icon?: React.ReactNode
  disabled?: boolean
  tooltip?: string
}

export interface SegmentedControlProps<T extends string> {
  options: SegmentOption<T>[]
  value: T
  onChange: (value: T) => void
  size?: 'sm' | 'md'
  className?: string
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  size = 'md',
  className = '',
}: SegmentedControlProps<T>) {
  const sizeClasses = {
    sm: 'p-0.5 text-[12px]',
    md: 'p-1 text-[13px]',
  }[size]

  const btnPadding = {
    sm: 'px-2.5 py-1',
    md: 'px-3.5 py-1.5',
  }[size]

  return (
    <div
      className={`inline-flex items-center bg-fill-active rounded-[8px] ${sizeClasses} ${className}`}
      role="tablist"
    >
      {options.map((opt) => {
        const isSelected = opt.value === value
        return (
          <button
            key={opt.value}
            role="tab"
            aria-selected={isSelected}
            disabled={opt.disabled}
            title={opt.tooltip}
            onClick={() => !opt.disabled && onChange(opt.value)}
            className={`inline-flex items-center justify-center gap-1.5 rounded-[6px] font-medium transition-all ${btnPadding} ${
              isSelected
                ? 'bg-card text-content-primary shadow-soft'
                : 'text-content-secondary hover:text-content-primary disabled:opacity-40 disabled:hover:text-content-secondary'
            }`}
          >
            {opt.icon && <span className="shrink-0">{opt.icon}</span>}
            <span>{opt.label}</span>
          </button>
        )
      })}
    </div>
  )
}
