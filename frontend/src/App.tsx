import React, { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { useAuthStore } from '@/store/authStore'
import { AppShell } from '@/components/layout/AppShell'

// Pages
import { LoginPage } from '@/pages/LoginPage'
import { LiveMonitorPage } from '@/pages/LiveMonitorPage'
import { IncidentQueuePage } from '@/pages/IncidentQueuePage'
import { IncidentDetailPage } from '@/pages/IncidentDetailPage'
import { AnalyzeFootagePage } from '@/pages/AnalyzeFootagePage'
import { ApprovalsPage } from '@/pages/ApprovalsPage'
import { MapPatrolPage } from '@/pages/MapPatrolPage'
import { CamerasPage } from '@/pages/CamerasPage'
import { RulesZonesPage } from '@/pages/RulesZonesPage'
import { CalibrationPage } from '@/pages/CalibrationPage'
import { EvaluationPage } from '@/pages/EvaluationPage'
import { PrivacyAuditPage } from '@/pages/PrivacyAuditPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { StudentSosPage } from '@/pages/StudentSosPage'
import { StudentTransparencyPage } from '@/pages/StudentTransparencyPage'
import { NotFoundPage } from '@/pages/NotFoundPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

// Protected Route Guard
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuthStore()

  if (isLoading) {
    return (
      <div className="min-h-screen bg-page flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

export function App() {
  const { initAuth } = useAuthStore()

  useEffect(() => {
    initAuth()
  }, [initAuth])

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Public routes */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/sos/:token" element={<StudentSosPage />} />
          <Route path="/transparency" element={<StudentTransparencyPage />} />

          {/* Protected app shell routes */}
          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route path="/" element={<LiveMonitorPage />} />
            <Route path="/analyze" element={<AnalyzeFootagePage />} />
            <Route path="/incidents" element={<IncidentQueuePage />} />
            <Route path="/incidents/:id" element={<IncidentDetailPage />} />
            <Route path="/approvals" element={<ApprovalsPage />} />
            <Route path="/map" element={<MapPatrolPage />} />
            <Route path="/cameras" element={<CamerasPage />} />
            <Route path="/rules" element={<RulesZonesPage />} />
            <Route path="/calibration" element={<CalibrationPage />} />
            <Route path="/evaluation" element={<EvaluationPage />} />
            <Route path="/privacy" element={<PrivacyAuditPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>

        <Toaster
          position="top-right"
          richColors
          toastOptions={{
            style: {
              background: '#FFFFFF',
              border: '1px solid #E5E2DB',
              color: '#1F2023',
              fontFamily: 'DM Sans, sans-serif',
              borderRadius: '12px',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.06)',
            },
          }}
        />
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
