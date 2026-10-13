import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { 
  Cpu, MessageSquare, Brain, Folder, Terminal, 
  Zap, Shield, Database, Clock, Activity
} from 'lucide-react'
import { api } from '../services/api'
import StatCard from '../components/StatCard'
import ProviderStatus from '../components/ProviderStatus'

const Dashboard: React.FC = () => {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: async () => (await fetch('/health')).json(),
    refetchInterval: 30000,
  })

  const { data: providers } = useQuery({
    queryKey: ['providers'],
    queryFn: async () => (await api.get('/providers/')).data,
    refetchInterval: 60000,
  })

  const { data: brainState } = useQuery({
    queryKey: ['brain-state'],
    queryFn: async () => (await api.get('/brain/state')).data,
    refetchInterval: 15000,
  })

  const { data: conversations } = useQuery({
    queryKey: ['conversations'],
    queryFn: async () => (await api.get('/conversations/')).data,
  })

  const available = providers?.filter((p: { available: boolean }) => p.available).length ?? 0
  const freeAvailable = providers?.filter((p: { available: boolean; free: boolean }) => p.available && p.free).length ?? 0
  const total = providers?.length ?? 0
  const statusCounts = brainState?.status_counts ?? {}
  const running = statusCounts.RUNNING ?? 0
  const succeeded = statusCounts.SUCCEEDED ?? 0
  const failed = statusCounts.FAILED ?? 0
  const totalTasks = brainState?.tasks?.length ?? 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold gradient-text mb-2">Dashboard</h1>
        <p className="text-gray-600 dark:text-gray-400">
          Datos reales del sistema NEXUS AI · v{health?.version || '…'}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Proveedores IA"
          value={`${available}/${total}`}
          change={`${freeAvailable} gratuitos disponibles`}
          icon={<Cpu className="w-5 h-5" />}
          color="blue"
          trend="stable"
        />
        <StatCard
          title="Conversaciones"
          value={String(conversations?.length ?? 0)}
          change="persistidas en base de datos"
          icon={<MessageSquare className="w-5 h-5" />}
          color="green"
          trend="stable"
        />
        <StatCard
          title="Tareas"
          value={String(totalTasks)}
          change={`${running} ejecutándose · ${succeeded} ok · ${failed} fallos`}
          icon={<Brain className="w-5 h-5" />}
          color="purple"
          trend="stable"
        />
        <StatCard
          title="Eventos cerebro"
          value={String(brainState?.recent_events ?? 0)}
          change="eventos reales registrados"
          icon={<Activity className="w-5 h-5" />}
          color="orange"
          trend="stable"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 glass-panel rounded-xl p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-1">Estado de Proveedores</h2>
              <p className="text-sm text-gray-600 dark:text-gray-400">Disponibilidad verificada contra el backend</p>
            </div>
            {health?.free_mode && (
              <div className="flex items-center gap-2">
                <Shield className="w-5 h-5 text-green-500" />
                <span className="text-sm font-medium text-green-600 dark:text-green-400">FREE MODE activo</span>
              </div>
            )}
          </div>
          <ProviderStatus />
        </div>

        <div className="glass-panel rounded-xl p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">Información del Sistema</h2>
          <div className="space-y-4 text-sm">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-gray-600 dark:text-gray-400"><Database className="w-4 h-4" /> Base de datos</span>
              <span className="font-medium">SQLite local</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-gray-600 dark:text-gray-400"><Terminal className="w-4 h-4" /> Agente local</span>
              <span className="font-medium text-green-600 dark:text-green-400">Operativo</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-gray-600 dark:text-gray-400"><Zap className="w-4 h-4" /> Modo Multi-IA</span>
              <span className="font-medium text-blue-600 dark:text-blue-400">Habilitado</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-gray-600 dark:text-gray-400"><Clock className="w-4 h-4" /> Estado backend</span>
              <span className="font-medium">{health?.status === 'healthy' ? <span className="text-green-600">Saludable</span> : <span className="text-red-500">{health?.status || '—'}</span>}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-gray-600 dark:text-gray-400"><Folder className="w-4 h-4" /> Memoria</span>
              <span className="font-medium">{brainState?.memory_enabled ? 'Activada' : 'Desactivada'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
