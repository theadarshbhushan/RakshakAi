import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Printer, ArrowLeft, Download, ShieldCheck, QrCode, AlertCircle, RefreshCw } from 'lucide-react'
import { api } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { toast } from 'sonner'
import type { Zone } from '@/api/types'

interface QrCardProps {
  zone: Zone
}

const ZoneQrPosterCard: React.FC<QrCardProps> = ({ zone }) => {
  const [qrUrl, setQrUrl] = useState<string | null>(null)
  const [blob, setBlob] = useState<Blob | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    let createdUrl: string | null = null

    setIsLoading(true)
    setError(null)

    api.sos.getZoneQrBlob(zone.zone_id)
      .then((dataBlob) => {
        if (!active) return
        createdUrl = URL.createObjectURL(dataBlob)
        setBlob(dataBlob)
        setQrUrl(createdUrl)
        setIsLoading(false)
      })
      .catch((err) => {
        if (!active) return
        setError(err.message || 'Failed to generate QR')
        setIsLoading(false)
      })

    return () => {
      active = false
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl)
      }
    }
  }, [zone.zone_id])

  const handleDownload = () => {
    if (!blob) {
      toast.error('QR code image is still generating')
      return
    }
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `sos-qr-${zone.zone_id}.png`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    toast.success(`Downloaded QR for ${zone.name}`)
  }

  return (
    <div className="bg-white rounded-[12px] border-2 border-border-card p-6 flex flex-col justify-between items-center text-center shadow-card break-inside-avoid print:border-black print:shadow-none print:m-0 print:p-5">
      {/* Top Header */}
      <div className="w-full pb-3 border-b border-border-divider/70 mb-4 print:border-black">
        <div className="flex items-center justify-between text-[11px] text-content-muted font-mono uppercase tracking-wider mb-1.5 print:text-black">
          <span className="flex items-center gap-1 font-semibold text-primary print:text-black">
            <ShieldCheck size={14} />
            RakshakAI
          </span>
          <span className="px-1.5 py-0.5 rounded bg-fill-subtle font-semibold text-content-primary print:border print:border-black print:bg-white">
            {zone.type || 'ZONE'}
          </span>
        </div>
        <h3 className="text-[17px] font-bold text-content-primary print:text-black leading-snug">
          {zone.name}
        </h3>
        <p className="text-[11px] font-mono text-content-muted print:text-black mt-0.5">
          Zone ID: {zone.zone_id}
        </p>
      </div>

      {/* QR Code Graphic */}
      <div className="my-2 p-3 bg-white rounded-[8px] flex items-center justify-center min-h-[190px]">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center gap-2 py-8 text-content-muted">
            <div className="w-7 h-7 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            <span className="text-[12px]">Generating poster QR…</span>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center gap-2 py-8 text-status-high">
            <AlertCircle size={24} />
            <span className="text-[12px]">{error}</span>
          </div>
        ) : qrUrl ? (
          <img
            src={qrUrl}
            alt={`SOS QR code for ${zone.name}`}
            className="w-44 h-44 object-contain shadow-soft print:shadow-none"
          />
        ) : null}
      </div>

      {/* Required Text Under QR */}
      <div className="w-full mt-3 pt-3 border-t border-border-divider/70 space-y-1 print:border-black">
        <p className="text-[14px] font-bold text-content-primary print:text-black leading-snug">
          Feeling unsafe? Scan for help. Anonymous.
        </p>
        <p className="text-[11px] text-content-secondary print:text-black leading-tight">
          Point any smartphone camera to report urgent distress. No app or student sign-in required.
        </p>
      </div>

      {/* Action Footer (Hidden in Print) */}
      <div className="w-full mt-4 pt-3 border-t border-border-divider/50 flex items-center justify-center print:hidden">
        <button
          type="button"
          onClick={handleDownload}
          disabled={isLoading || !blob}
          className="inline-flex items-center gap-1.5 text-[12px] font-medium text-primary hover:text-primary-dark transition-colors disabled:opacity-50"
        >
          <Download size={13} />
          Download PNG
        </button>
      </div>
    </div>
  )
}

export const SosQrPage: React.FC = () => {
  const { hasRole } = useAuthStore()
  const isOwnerOrAdmin = hasRole('owner', 'admin')

  const { data: zones = [], isLoading, error, refetch } = useQuery({
    queryKey: ['zones_list'],
    queryFn: () => api.zones.list(),
  })

  if (!isOwnerOrAdmin) {
    return (
      <div className="py-16 text-center max-w-md mx-auto">
        <h2 className="text-[18px] font-bold text-critical">Unauthorized Access</h2>
        <p className="text-[13px] text-content-secondary mt-1 mb-4">
          Only hostel owners and system administrators can view and print student SOS QR sheets.
        </p>
        <Link to="/app/settings">
          <Button variant="secondary" size="sm">
            Back to settings
          </Button>
        </Link>
      </div>
    )
  }

  const handlePrint = () => {
    window.print()
  }

  return (
    <div className="space-y-6">
      {/* Top Navigation & Controls (Hidden in Print) */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 print:hidden">
        <div>
          <Link
            to="/app/settings"
            className="inline-flex items-center gap-1.5 text-[13px] text-content-secondary hover:text-content-primary font-medium mb-2 transition-colors"
          >
            <ArrowLeft size={14} />
            Back to settings
          </Link>
          <h1 className="text-[26px] font-bold text-content-primary">
            Student SOS QR Posters
          </h1>
          <p className="text-[14px] text-content-secondary mt-0.5">
            Printable physical posters for corridor walls, turnstiles, and common rooms. Students can scan to summon immediate anonymous aid.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant="secondary"
            size="md"
            icon={<RefreshCw size={14} />}
            onClick={() => refetch()}
          >
            Refresh
          </Button>
          <Button
            variant="primary"
            size="md"
            icon={<Printer size={15} />}
            onClick={handlePrint}
          >
            Print posters
          </Button>
        </div>
      </div>

      {/* Printable Sheet Content */}
      {isLoading ? (
        <div className="py-20 flex flex-col items-center justify-center gap-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-[13px] text-content-muted">Loading hostel zones…</p>
        </div>
      ) : error ? (
        <Card padding="md" className="text-center py-10 space-y-3">
          <AlertCircle size={28} className="mx-auto text-status-high" />
          <h3 className="text-[16px] font-semibold text-content-primary">Failed to load zones</h3>
          <p className="text-[13px] text-content-muted max-w-sm mx-auto">
            {(error as any)?.message || 'Could not fetch hostel zone configurations.'}
          </p>
          <Button variant="secondary" size="sm" onClick={() => refetch()}>
            Try again
          </Button>
        </Card>
      ) : zones.length === 0 ? (
        <Card padding="md" className="text-center py-12 space-y-2">
          <QrCode size={32} className="mx-auto text-content-muted" />
          <h3 className="text-[16px] font-semibold text-content-primary">No zones found</h3>
          <p className="text-[13px] text-content-muted">
            Configure hostel zones in Rules & Zones before printing SOS codes.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 print:grid-cols-2 print:gap-4">
          {zones.map((zone) => (
            <ZoneQrPosterCard key={zone.zone_id} zone={zone} />
          ))}
        </div>
      )}
    </div>
  )
}

export default SosQrPage
