import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Radio, Cpu } from 'lucide-react'
import { api, BrainStateInfo, TaskInfo } from '../services/api'
import { useEventStream } from '../hooks/useSocket'

const statusColors: Record<string, string> = {
  PENDING: 'text-gray-500',
  RUNNING: 'text-blue-500 animate-pulse',
  SUCCEEDED: 'text-green-500',
  FAILED: 'text-red-500',
  RETRYING: 'text-yellow-500',
  CANCELLED: 'text-gray-400',
  WAITING_APPROVAL: 'text-orange-500',
}

const BrainPage: React.FC = () => {
  const { events, connected } = useEventStream()
  const [taskFilter, setTaskFilter] = useState<number | null>(null)

  const { data: state } = useQuery<BrainStateInfo>({
    queryKey: ['brain-state'],
    queryFn: async () => (await api.get('/brain/state')).data,
    refetchInterval: 15000,
  })

  const { data: tasks } = useQuery<TaskInfo[]>({
    queryKey: ['tasks'],
    queryFn: async () => (await api.get('/tasks/')).data,
    refetchInterval: 15000,
  })

  const filteredEvents = taskFilter !== null ? events.filter((e) => e.task_id === taskFilter) : events

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold gradient-text">Cerebro</h1>
          <p className="text-gray-600 dark:text-gray-400">Eventos reales de ejecución en tiempo real (SSE)</p>
        </div>
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ${connected ? 'bg-green-100 text-green-700 dark:bg-green-900/40' : 'bg-red-100 text-red-700 dark:bg-red-900/40'}`}>
          <Radio className={`w-4 h-4 ${connected ? 'animate-pulse' : ''}`} />
          {connected ? 'Conectado' : 'Desconectado'}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
        {state && Object.entries(state.status_counts).map(([status, count]) => (
          <div key={status} className="p-3 rounded-lg border dark:border-gray-700 text-center">
            <div className={`text-2xl font-bold ${statusColors[status] || ''}`}>{count}</div>
            <div className="text-xs text-gray-500">{status}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-3">
          <h2 className="font-semibold flex items-center gap-2"><Cpu className="w-4 h-4" /> Tareas</h2>
          {tasks?.length === 0 && <p className="text-sm text-gray-500">Sin tareas todavía. Crea una desde Conversaciones → Multi-IA.</p>}
          {tasks?.map((t) => (
            <div key={t.id} className={`p-3 rounded-lg border dark:border-gray-700 cursor-pointer ${taskFilter === t.id ? 'border-nexus-500 bg-nexus-50 dark:bg-nexus-900/20' : ''}`} onClick={() => setTaskFilter(taskFilter === t.id ? null : t.id)}>
              <div className="flex justify-between items-start">
                <div>
                  <div className="text-sm font-medium">#{t.id} · {t.objective.slice(0, 80)}</div>
                  <div className="text-xs text-gray-500 mt-1">{t.providers.join(', ')}</div>
                </div>
                <span className={`text-xs font-medium ${statusColors[t.status] || ''}`}>{t.status}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Eventos en vivo</h2>
            {taskFilter !== null && (
              <button onClick={() => setTaskFilter(null)} className="text-xs text-nexus-600 underline">Quitar filtro #{taskFilter}</button>
            )}
          </div>
          <div className="max-h-[55vh] overflow-y-auto space-y-1 font-mono text-xs">
            {filteredEvents.length === 0 && <p className="text-gray-500 font-sans">Esperando eventos…</p>}
            {filteredEvents.slice().reverse().map((e) => (
              <div key={e.id} className="p-2 rounded bg-gray-50 dark:bg-gray-800/60 border dark:border-gray-700/50">
                <span className="text-gray-400">{new Date(e.timestamp * 1000).toLocaleTimeString()}</span>{' '}
                <span className="text-nexus-600 dark:text-nexus-400 font-semibold">{e.type}</span>
                {e.task_id !== null && <span className="text-gray-500"> task#{e.task_id}</span>}
                {e.status && <span className={`ml-1 ${statusColors[e.status] || 'text-gray-500'}`}>[{e.status}]</span>}
                {Object.keys(e.data).length > 0 && <div className="text-gray-500 mt-0.5">{JSON.stringify(e.data).slice(0, 200)}</div>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export default BrainPage
