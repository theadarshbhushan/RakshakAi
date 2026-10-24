import React, { useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  UploadCloud,
  Film,
  Music,
  Play,
  Trash2,
  CheckCircle,
  Clock,
  Radio,
  Video,
  AlertTriangle,
  ArrowRight,
  Maximize2,
} from 'lucide-react'
import { api, getAccessToken } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { EmptyState } from '@/components/ui/EmptyState'
import { toast } from 'sonner'
import type { AnalysisJob, Camera } from '@/api/types'

export const AnalyzeFootagePage: React.FC = () => {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Upload Form State
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [targetType, setTargetType] = useState<'video' | 'audio'>('video')
  const [selectedCamera, setSelectedCamera] = useState('cam_terrace')
  const [selectedZone, setSelectedZone] = useState('terrace')
  const [simulatedTime, setSimulatedTime] = useState('23:40')
  const [isUploading, setIsUploading] = useState(false)

  // Player State
  const [activeJob, setActiveJob] = useState<AnalysisJob | null>(null)
  const [videoMode, setVideoMode] = useState<'skeleton' | 'blurred'>('skeleton')

  // Live Webcam Analysis State
  const [liveCameraId, setLiveCameraId] = useState('cam_terrace')
  const [isLiveActive, setIsLiveActive] = useState(false)
  const [isLiveStarting, setIsLiveStarting] = useState(false)

  // Fetch cameras
  const { data: cameras = [] } = useQuery({
    queryKey: ['cameras'],
    queryFn: () => api.cameras.list(),
  })

  // Fetch jobs
  const { data: jobsData, isLoading: jobsLoading } = useQuery({
    queryKey: ['analyze_jobs'],
    queryFn: () => api.analyze.listJobs(),
    refetchInterval: 5000,
  })

  const jobs: AnalysisJob[] = Array.isArray(jobsData) ? jobsData : (jobsData as any)?.items || []

  // Auto-select first job if none selected
  React.useEffect(() => {
    if (!activeJob && jobs.length > 0) {
      setActiveJob(jobs[0])
    }
  }, [jobs, activeJob])

  // Drag & drop handlers
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0]
      setSelectedFile(file)
      if (file.type.startsWith('audio/')) {
        setTargetType('audio')
      } else {
        setTargetType('video')
      }
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0]
      setSelectedFile(file)
      if (file.type.startsWith('audio/')) {
        setTargetType('audio')
      } else {
        setTargetType('video')
      }
    }
  }

  // Upload mutation
  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedFile) {
      toast.error('Please choose a video or audio file')
      return
    }

    setIsUploading(true)
    const formData = new FormData()
    formData.append('file', selectedFile)
    if (targetType === 'video') {
      formData.append('camera_id', selectedCamera)
    } else {
      formData.append('zone_id', selectedZone)
    }
    if (simulatedTime) {
      formData.append('simulated_time', simulatedTime)
    }

    try {
      const job = await api.analyze.upload(formData)
      toast.success('Upload complete! Multi-sensor analysis started.')
      setSelectedFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      setActiveJob(job)
      queryClient.invalidateQueries({ queryKey: ['analyze_jobs'] })
    } catch (err: any) {
      toast.error(err.message || 'Upload failed')
    } finally {
      setIsUploading(false)
    }
  }

  // Delete Job mutation
  const deleteMutation = useMutation({
    mutationFn: (jobId: string) => api.analyze.deleteJob(jobId),
    onSuccess: (_, jobId) => {
      toast.info('Analysis job removed')
      if (activeJob?.job_id === jobId) {
        setActiveJob(null)
      }
      queryClient.invalidateQueries({ queryKey: ['analyze_jobs'] })
    },
  })

  // Start Live Webcam Analysis
  const handleToggleLive = async () => {
    if (isLiveActive) {
      try {
        await api.analyze.stopLive(liveCameraId)
        setIsLiveActive(false)
        toast.info('Live webcam analysis stopped')
      } catch (err: any) {
        toast.error(err.message || 'Failed to stop live feed')
      }
    } else {
      setIsLiveStarting(true)
      try {
        await api.analyze.startLive({ camera_id: liveCameraId })
        setIsLiveActive(true)
        toast.success(`Live webcam analysis active on ${liveCameraId}`)
      } catch (err: any) {
        toast.error(err.message || 'Failed to start live analysis')
      } finally {
        setIsLiveStarting(false)
      }
    }
  }

  const token = getAccessToken()

  return (
    <div className="space-y-6">
      {/* Page Title */}
      <div>
        <h1 className="text-[26px] font-bold text-content-primary">Analyze Footage</h1>
        <p className="text-[14px] text-content-secondary mt-0.5">
          Upload recorded CCTV footage or audio recordings for pose skeleton detection and audio classification.
        </p>
      </div>

      {/* 2-Column Top Section: Upload Box & Go-Live Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Upload Form (2 cols) */}
        <Card padding="md" className="lg:col-span-2 space-y-4">
          <h2 className="text-[17px] font-semibold text-content-primary">
            Upload footage for processing
          </h2>

          <form onSubmit={handleUpload} className="space-y-4">
            {/* Drag & Drop Zone */}
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`p-6 border-2 border-dashed rounded-card text-center cursor-pointer transition-colors ${
                selectedFile
                  ? 'border-primary bg-primary-tint/20'
                  : 'border-border-input hover:border-content-muted bg-fill-subtle/40'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="video/*,audio/*,.mp4,.avi,.mov,.wav,.mp3"
                onChange={handleFileChange}
                className="hidden"
              />
              <UploadCloud
                size={36}
                className={`mx-auto mb-2 ${selectedFile ? 'text-primary' : 'text-content-muted'}`}
              />
              {selectedFile ? (
                <div>
                  <p className="text-[14px] font-medium text-content-primary">
                    {selectedFile.name}
                  </p>
                  <p className="text-[12px] text-content-muted mt-0.5 font-mono">
                    {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB · Click to choose another
                  </p>
                </div>
              ) : (
                <div>
                  <p className="text-[14px] font-medium text-content-body">
                    Drag and drop CCTV video (.mp4) or acoustic audio (.wav) here
                  </p>
                  <p className="text-[12px] text-content-muted mt-1">
                    Or click to browse from your computer
                  </p>
                </div>
              )}
            </div>

            {/* Target Selectors */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-[12px] font-medium text-content-secondary mb-1">
                  Modality
                </label>
                <select
                  value={targetType}
                  onChange={(e) => setTargetType(e.target.value as any)}
                  className="w-full px-3 py-1.5 text-[13px] bg-card border border-border-input rounded-input"
                >
                  <option value="video">Video (Pose & Intrusion)</option>
                  <option value="audio">Audio (Acoustic scream)</option>
                </select>
              </div>

              {targetType === 'video' ? (
                <div>
                  <label className="block text-[12px] font-medium text-content-secondary mb-1">
                    Target Camera
                  </label>
                  <select
                    value={selectedCamera}
                    onChange={(e) => setSelectedCamera(e.target.value)}
                    className="w-full px-3 py-1.5 text-[13px] bg-card border border-border-input rounded-input"
                  >
                    {cameras.map((c) => (
                      <option key={c.camera_id} value={c.camera_id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>
              ) : (
                <div>
                  <label className="block text-[12px] font-medium text-content-secondary mb-1">
                    Target Zone
                  </label>
                  <select
                    value={selectedZone}
                    onChange={(e) => setSelectedZone(e.target.value)}
                    className="w-full px-3 py-1.5 text-[13px] bg-card border border-border-input rounded-input"
                  >
                    <option value="terrace">Terrace Rooftop</option>
                    <option value="common_room">Common Room</option>
                    <option value="block_b_entry">Block B Entry</option>
                    <option value="corridor_2f">Corridor 2F</option>
                  </select>
                </div>
              )}

              <div>
                <label className="block text-[12px] font-medium text-content-secondary mb-1">
                  Simulated Time (Curfew test)
                </label>
                <input
                  type="text"
                  value={simulatedTime}
                  onChange={(e) => setSimulatedTime(e.target.value)}
                  placeholder="e.g. 23:40"
                  className="w-full px-3 py-1.5 text-[13px] bg-card border border-border-input rounded-input font-mono"
                />
              </div>
            </div>

            <div className="flex justify-end pt-1">
              <Button
                type="submit"
                variant="primary"
                size="md"
                isLoading={isUploading}
                disabled={!selectedFile}
              >
                Start analysis
              </Button>
            </div>
          </form>
        </Card>

        {/* Go Live Panel (1 col) */}
        <Card padding="md" className="space-y-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Radio
                size={18}
                className={isLiveActive ? 'text-critical animate-pulse' : 'text-content-muted'}
              />
              <h2 className="text-[17px] font-semibold text-content-primary">
                Live webcam analysis
              </h2>
            </div>
            <p className="text-[12px] text-content-muted mt-1 leading-relaxed">
              Stream directly from your workstation camera into the edge pose detector to test real-time skeletons.
            </p>

            <div className="mt-4">
              <label className="block text-[12px] font-medium text-content-secondary mb-1.5">
                Target camera feed
              </label>
              <select
                value={liveCameraId}
                onChange={(e) => setLiveCameraId(e.target.value)}
                className="w-full px-3 py-2 text-[13px] bg-card border border-border-input rounded-input"
              >
                {cameras.map((c) => (
                  <option key={c.camera_id} value={c.camera_id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="pt-4 border-t border-border-divider">
            <Button
              variant={isLiveActive ? 'danger' : 'primary'}
              size="md"
              className="w-full"
              isLoading={isLiveStarting}
              onClick={handleToggleLive}
            >
              {isLiveActive ? 'Stop webcam analysis' : 'Start webcam analysis'}
            </Button>
            <p className="text-[11px] text-content-muted mt-2 text-center">
              Skeleton output displays on Live Monitor
            </p>
          </div>
        </Card>
      </div>

      {/* 2-Column Lower Section: Jobs Queue & Inline Video Player */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Jobs Queue Table (1 col) */}
        <Card padding="none" className="overflow-hidden flex flex-col">
          <div className="p-4 border-b border-border-divider bg-fill-subtle/50">
            <h2 className="text-[16px] font-semibold text-content-primary">
              Analysis queue & history
            </h2>
          </div>

          <div className="divide-y divide-border-divider overflow-y-auto max-h-[500px]">
            {jobs.length === 0 ? (
              <div className="p-8 text-center text-content-muted text-[13px]">
                No jobs processed yet. Upload a clip above.
              </div>
            ) : (
              jobs.map((job) => {
                const isSelected = activeJob?.job_id === job.job_id
                return (
                  <div
                    key={job.job_id}
                    onClick={() => setActiveJob(job)}
                    className={`p-3.5 cursor-pointer transition-colors ${
                      isSelected
                        ? 'bg-fill-active'
                        : 'hover:bg-fill-subtle/50'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        {job.type === 'audio' ? (
                          <Music size={14} className="text-content-muted" />
                        ) : (
                          <Film size={14} className="text-primary" />
                        )}
                        <span className="text-[13px] font-semibold text-content-primary truncate max-w-[150px]">
                          {job.original_filename || job.job_id.slice(0, 8)}
                        </span>
                      </div>

                      <span
                        className={`text-[11px] font-medium px-1.5 py-0.5 rounded ${
                          job.status === 'done'
                            ? 'bg-status-healthy-tint text-status-healthy'
                            : job.status === 'processing'
                            ? 'bg-status-medium-tint text-status-medium animate-pulse'
                            : 'bg-critical-tint text-critical'
                        }`}
                      >
                        {job.status}
                      </span>
                    </div>

                    {/* Progress bar if processing */}
                    {job.status === 'processing' && (
                      <div className="w-full h-1.5 bg-fill-subtle rounded-full overflow-hidden mt-2">
                        <div
                          className="h-full bg-primary transition-all duration-300"
                          style={{ width: `${job.progress || 20}%` }}
                        />
                      </div>
                    )}

                    <div className="mt-2 flex items-center justify-between text-[11px] text-content-muted font-mono">
                      <span>{job.signals_count || 0} signals detected</span>
                      <span>{job.zone_id || job.camera_id}</span>
                    </div>

                    {job.incident_ids && job.incident_ids.length > 0 && (
                      <div className="mt-2 pt-1 border-t border-border-divider/60 flex items-center justify-between">
                        <Link
                          to={`/incidents/${job.incident_ids[0]}`}
                          onClick={(e) => e.stopPropagation()}
                          className="text-[12px] font-medium text-primary hover:underline flex items-center gap-1"
                        >
                          <span>View incident</span>
                          <ArrowRight size={12} />
                        </Link>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            deleteMutation.mutate(job.job_id)
                          }}
                          className="text-content-muted hover:text-critical p-1"
                          title="Delete job"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </div>
        </Card>

        {/* Inline Annotated Video Player (2 cols) */}
        <Card padding="md" className="lg:col-span-2 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h2 className="text-[17px] font-semibold text-content-primary">
                Annotated inspection
              </h2>
              <p className="text-[12px] text-content-muted">
                {activeJob
                  ? `${activeJob.original_filename || activeJob.job_id} · ${activeJob.signals_count || 0} signals`
                  : 'Select a job to play result'}
              </p>
            </div>

            {/* View Toggle */}
            <div className="inline-flex items-center bg-fill-active p-1 rounded-[8px]">
              <button
                type="button"
                onClick={() => setVideoMode('skeleton')}
                className={`px-3 py-1 text-[12px] font-medium rounded-[6px] ${
                  videoMode === 'skeleton'
                    ? 'bg-card text-content-primary shadow-soft'
                    : 'text-content-secondary hover:text-content-primary'
                }`}
              >
                Skeleton view
              </button>
              <button
                type="button"
                onClick={() => setVideoMode('blurred')}
                className={`px-3 py-1 text-[12px] font-medium rounded-[6px] ${
                  videoMode === 'blurred'
                    ? 'bg-card text-content-primary shadow-soft'
                    : 'text-content-secondary hover:text-content-primary'
                }`}
              >
                Face-blurred view
              </button>
            </div>
          </div>

          {/* Video Player Display */}
          <div className="relative aspect-video bg-video-bg rounded-card overflow-hidden flex items-center justify-center border border-border-card">
            {activeJob && activeJob.status === 'done' ? (
              <video
                key={`${activeJob.job_id}-${videoMode}`}
                controls
                autoPlay
                loop
                muted
                className="w-full h-full object-contain"
                src={`/api/v1/analyze/jobs/${activeJob.job_id}/annotated?mode=${videoMode}${
                  token ? `&token=${encodeURIComponent(token)}` : ''
                }`}
              />
            ) : activeJob && activeJob.status === 'processing' ? (
              <div className="text-center text-[#EDEBE6]">
                <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                <p className="text-[13px]">Processing video frames with YOLOv8 pose detector…</p>
                <p className="text-[11px] text-[#B9B7B1] mt-1">
                  Progress: {activeJob.progress || 0}%
                </p>
              </div>
            ) : (
              <div className="text-center text-[#B9B7B1]">
                <Film size={36} className="mx-auto mb-2 opacity-50" />
                <p className="text-[13px]">No completed job selected</p>
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
