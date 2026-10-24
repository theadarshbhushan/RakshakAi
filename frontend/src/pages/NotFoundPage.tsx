import React from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { ShieldAlert } from 'lucide-react'

export const NotFoundPage: React.FC = () => {
  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center text-center p-6">
      <div className="w-14 h-14 rounded-full bg-primary-tint flex items-center justify-center text-primary mb-4">
        <ShieldAlert size={28} />
      </div>
      <h1 className="text-[24px] font-bold text-content-primary">Page not found</h1>
      <p className="text-[14px] text-content-secondary mt-1 max-w-sm mb-6">
        The safety dashboard view or incident you requested does not exist or may have been archived.
      </p>
      <Link to="/">
        <Button variant="primary" size="md">
          Return to Live Monitor
        </Button>
      </Link>
    </div>
  )
}
