import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle, XCircle, AlertCircle, Clock, Shield } from 'lucide-react'
import { api } from '../services/api'

interface Provider {
  name: string
  provider_id: string
  available: boolean
  free: boolean
  status: string
  last_checked: string
}

const ProviderStatus: React.FC = () => {
  const { data: providers, isLoading } = useQuery<Provider[]>({
    queryKey: ['providers'],
    queryFn: async () => (await api.get('/providers/')).data,
    refetchInterval: 60000, // Refetch every minute
  })

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="animate-pulse">
            <div className="h-16 bg-gray-200 dark:bg-gray-700 rounded-lg"></div>
          </div>
        ))}
      </div>
    )
  }

  const getStatusIcon = (status: string, available: boolean) => {
    if (!available) {
      return <XCircle className="w-5 h-5 text-red-500" />
    }
    
    switch (status) {
      case 'FREE_AVAILABLE':
        return <Shield className="w-5 h-5 text-green-500" />
      case 'FREE_LIMIT_REACHED':
        return <Clock className="w-5 h-5 text-yellow-500" />
      case 'AUTH_REQUIRED':
        return <AlertCircle className="w-5 h-5 text-blue-500" />
      default:
        return <CheckCircle className="w-5 h-5 text-gray-500" />
    }
  }

  const getStatusText = (status: string, available: boolean) => {
    if (!available) return 'No disponible'
    
    switch (status) {
      case 'FREE_AVAILABLE':
        return 'Gratuito disponible'
      case 'FREE_LIMIT_REACHED':
        return 'Límite gratuito alcanzado'
      case 'AUTH_REQUIRED':
        return 'Autenticación requerida'
      case 'PAID_ROUTE_BLOCKED':
        return 'Ruta de pago bloqueada (FREE MODE)'
      case 'UNAVAILABLE':
        return 'No disponible'
      default:
        return 'Disponible'
    }
  }

  const getStatusColor = (status: string, available: boolean) => {
    if (!available) return 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200'
    
    switch (status) {
      case 'FREE_AVAILABLE':
        return 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200'
      case 'FREE_LIMIT_REACHED':
        return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200'
      case 'AUTH_REQUIRED':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200'
      case 'PAID_ROUTE_BLOCKED':
        return 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200'
      default:
        return 'bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200'
    }
  }

  return (
    <div className="space-y-4">
      {providers?.map((provider) => (
        <div
          key={provider.provider_id}
          className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700"
        >
          <div className="flex items-center gap-4">
            <div className="p-2 bg-white dark:bg-gray-800 rounded-lg">
              {getStatusIcon(provider.status, provider.available)}
            </div>
            
            <div>
              <h3 className="font-medium text-gray-900 dark:text-white">
                {provider.name}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                ID: {provider.provider_id}
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            <div className="text-right">
              <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium ${getStatusColor(provider.status, provider.available)}`}>
                {getStatusText(provider.status, provider.available)}
              </span>
              
              {provider.free && provider.available && (
                <div className="mt-1 flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                  <Shield className="w-3 h-3" />
                  <span>Gratuito compatible</span>
                </div>
              )}
            </div>
            
            {/* Action button */}
            <button
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                provider.available
                  ? 'bg-nexus-600 hover:bg-nexus-700 text-white'
                  : 'bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 cursor-not-allowed'
              }`}
              disabled={!provider.available}
              title={provider.available ? `Usar ${provider.name}` : 'Proveedor no disponible'}
            >
              {provider.available ? 'Usar' : 'No disp.'}
            </button>
          </div>
        </div>
      ))}
      
      {/* FREE MODE notice */}
      <div className="mt-6 p-4 bg-gradient-to-r from-green-50 to-blue-50 dark:from-green-900/20 dark:to-blue-900/20 rounded-lg border border-green-200 dark:border-green-800">
        <div className="flex items-center gap-3">
          <Shield className="w-5 h-5 text-green-600 dark:text-green-400" />
          <div>
            <h4 className="font-medium text-green-800 dark:text-green-300">
              Modo Gratuito Activo
            </h4>
            <p className="text-sm text-green-700 dark:text-green-400/80">
              Solo se permiten proveedores con acceso gratuito autorizado.
              Las rutas de pago están bloqueadas automáticamente.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ProviderStatus