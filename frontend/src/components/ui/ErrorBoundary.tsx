import React, { Component, ErrorInfo, ReactNode } from 'react'
import { AlertTriangle, RefreshCw, Home } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'

interface Props {
  children: ReactNode
  fallbackTitle?: string
  fallbackDescription?: string
}

interface State {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
    this.setState({ error, errorInfo })
  }

  public handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null })
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="py-12 px-4 max-w-xl mx-auto">
          <Card padding="lg" className="space-y-4 border-status-high/30 shadow-card">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-status-high-tint flex items-center justify-center shrink-0">
                <AlertTriangle size={20} className="text-status-high" />
              </div>
              <div className="space-y-1">
                <h2 className="text-[18px] font-bold text-content-primary">
                  {this.props.fallbackTitle || 'Unable to display this view'}
                </h2>
                <p className="text-[13px] text-content-secondary leading-relaxed">
                  {this.props.fallbackDescription ||
                    'An unexpected rendering issue occurred while loading this section. Your session and audit records remain safe.'}
                </p>
              </div>
            </div>

            {this.state.error && (
              <div className="p-3 bg-fill-subtle rounded-card border border-border-card text-[12px] font-mono text-content-muted break-all max-h-36 overflow-y-auto">
                {this.state.error.message || String(this.state.error)}
              </div>
            )}

            <div className="pt-2 flex items-center gap-3">
              <Button
                variant="primary"
                size="md"
                icon={<RefreshCw size={14} />}
                onClick={this.handleRetry}
              >
                Try again
              </Button>
              <Button
                variant="secondary"
                size="md"
                icon={<Home size={14} />}
                onClick={() => {
                  window.location.href = '/app'
                }}
              >
                Back to monitor
              </Button>
            </div>
          </Card>
        </div>
      )
    }

    return this.props.children
  }
}
