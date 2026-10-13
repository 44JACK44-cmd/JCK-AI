import React, { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { CheckCircle, AlertCircle, WifiOff } from 'lucide-react'

interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy'
  service: string
  version: string
  environment: string
  free_mode: boolean
  timestamp: number
}

const HealthCheck: React.FC = () => {
  const [showAlert, setShowAlert] = useState(false)
  const [lastHealthy, setLastHealthy] = useState<number>(Date.now())

  const { data, isLoading, error, refetch } = useQuery<HealthStatus>({
    queryKey: ['health'],
    queryFn: async () => {
      const response = await fetch('/health')
      if (!response.ok) {
        throw new Error(`Health check failed: ${response.status}`)
      }
      return response.json()
    },
    refetchInterval: 30000, // Check every 30 seconds
    retry: 2,
  })

  useEffect(() => {
    if (error) {
      setShowAlert(true)
      toast('Conexión con el backend perdida', {
        id: 'backend-error',
        icon: '⚠️',
        duration: 5000,
      })
    } else if (data) {
      setLastHealthy(Date.now())
      
      if (data.status !== 'healthy') {
        setShowAlert(true)
        toast(`Estado del sistema: ${data.status}`, {
          id: 'system-warning',
          icon: '⚠️',
          duration: 3000,
        })
      } else if (showAlert) {
        setShowAlert(false)
        toast.success('Sistema restaurado', {
          id: 'system-restored',
          duration: 3000,
        })
      }
    }
  }, [data, error, showAlert])

  // Calculate uptime
  const uptime = React.useMemo(() => {
    if (!lastHealthy) return '--:--:--'
    
    const diff = Date.now() - lastHealthy
    const hours = Math.floor(diff / (1000 * 60 * 60))
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
    const seconds = Math.floor((diff % (1000 * 60)) / 1000)
    
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
  }, [lastHealthy])

  if (isLoading) {
    return null
  }

  return (
    <>
      {/* Health status indicator (floating) */}
      <div className="fixed bottom-4 right-4 z-50">
        <div className="flex items-center gap-2 bg-white dark:bg-gray-800 rounded-lg shadow-lg px-4 py-2 border border-gray-200 dark:border-gray-700">
          {error ? (
            <>
              <WifiOff className="w-4 h-4 text-red-500" />
              <span className="text-sm text-red-600 dark:text-red-400 font-medium">
                Offline
              </span>
            </>
          ) : data?.status === 'healthy' ? (
            <>
              <CheckCircle className="w-4 h-4 text-green-500" />
              <div className="flex flex-col">
                <span className="text-sm text-green-600 dark:text-green-400 font-medium">
                  Sistema OK
                </span>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  Uptime: {uptime}
                </span>
              </div>
            </>
          ) : (
            <>
              <AlertCircle className="w-4 h-4 text-yellow-500" />
              <div className="flex flex-col">
                <span className="text-sm text-yellow-600 dark:text-yellow-400 font-medium">
                  {data?.status === 'degraded' ? 'Degradado' : 'Error'}
                </span>
                <button
                  onClick={() => refetch()}
                  className="text-xs text-nexus-600 dark:text-nexus-400 hover:underline"
                >
                  Reintentar
                </button>
              </div>
            </>
          )}
          
          {/* FREE MODE indicator */}
          {data?.free_mode && (
            <div className="ml-2 px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 text-xs font-medium rounded-full">
              FREE MODE
            </div>
          )}
        </div>
      </div>

      {/* Connection alert banner */}
      {showAlert && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-red-500 text-white px-4 py-2">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5" />
              <span className="font-medium">
                {error 
                  ? 'No se puede conectar con el backend de NEXUS AI'
                  : `Estado del sistema: ${data?.status}`
                }
              </span>
            </div>
            <button
              onClick={() => setShowAlert(false)}
              className="text-white/80 hover:text-white"
            >
              ×
            </button>
          </div>
        </div>
      )}
    </>
  )
}

export default HealthCheck