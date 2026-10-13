import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Play, Shield, Loader2, History } from 'lucide-react'
import { api } from '../services/api'

interface CommandResult {
  command: string
  cwd: string
  exit_code: number | null
  stdout: string
  stderr: string
  status: string
  duration_ms: number
  timed_out: boolean
}

interface HistoryItem {
  id: number
  command: string
  cwd: string
  exit_code: number | null
  status: string
  duration_ms: number | null
  started_at: string | null
  stdout: string | null
  stderr: string | null
}

interface RejectedItem {
  id: number
  command: string
  cwd: string
  exit_code: null
  status: 'REJECTED'
  duration_ms: number
  stdout: string
  stderr: string
  started_at?: string
}

type DisplayItem = HistoryItem | RejectedItem

const AgentPage: React.FC = () => {
  const [command, setCommand] = useState('')
  const [cwd, setCwd] = useState<string>('')
  const [rejected, setRejected] = useState<RejectedItem[]>([])
  const [cmdRecall, setCmdRecall] = useState<string[]>([])
  const [recallIdx, setRecallIdx] = useState(-1)
  const nextId = React.useRef(1)
  const queryClient = useQueryClient()

  const { data: policy } = useQuery({
    queryKey: ['terminal-policy'],
    queryFn: async () => (await api.get('/terminal/allowed')).data,
  })

  // Persisted history (survives reloads) — backend logs every execution
  const { data: serverHistory, isLoading: historyLoading } = useQuery<HistoryItem[]>({
    queryKey: ['terminal-history'],
    queryFn: async () => (await api.get('/terminal/history', { params: { limit: 50 } })).data,
    refetchOnWindowFocus: false,
  })

  const runCmd = useMutation({
    mutationFn: async (cmd: string) =>
      (await api.post('/terminal/execute', { command: cmd, cwd: cwd || undefined })).data as CommandResult,
    onSuccess: (result) => {
      setCommand('')
      setCmdRecall((prev) => [result.command, ...prev].slice(0, 50))
      setRecallIdx(-1)
      queryClient.invalidateQueries({ queryKey: ['terminal-history'] })
    },
    onError: (err: unknown) => {
      let detail = 'Error desconocido'
      if (err && typeof err === 'object' && 'response' in err) {
        const resp = (err as { response?: { data?: { detail?: string } } }).response
        detail = resp?.data?.detail || 'Error'
      }
      setRejected((prev) => [...prev, {
        id: nextId.current++,
        command, cwd: cwd || '—', exit_code: null, stdout: '', stderr: detail,
        status: 'REJECTED' as const, duration_ms: 0,
      }])
      setCmdRecall((prev) => [command, ...prev].slice(0, 50))
      setRecallIdx(-1)
    },
  })

  const items: DisplayItem[] = [...rejected, ...(serverHistory || [])]
  const quickCommands = ['python --version', 'git status', 'node --version', 'npm --version', 'dir']

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && command.trim() && !runCmd.isPending) {
      runCmd.mutate(command)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      const next = Math.min(recallIdx + 1, cmdRecall.length - 1)
      if (next >= 0 && cmdRecall[next]) { setRecallIdx(next); setCommand(cmdRecall[next]) }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      const next = recallIdx - 1
      if (next >= 0) { setRecallIdx(next); setCommand(cmdRecall[next]) }
      else { setRecallIdx(-1); setCommand('') }
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold gradient-text">Agente Local</h1>
        <p className="text-gray-600 dark:text-gray-400">Terminal validada: solo comandos permitidos dentro de carpetas autorizadas</p>
      </div>

      {policy && (
        <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/60 border dark:border-gray-700 text-xs">
          <div className="flex items-center gap-2 mb-1 font-medium"><Shield className="w-4 h-4 text-green-500" /> Política activa</div>
          <div className="text-gray-600 dark:text-gray-400">
            Timeout máx: {policy.max_timeout_seconds}s · Salida máx: {policy.max_output_kb} KB ·
            Raíces: {policy.authorized_roots?.join(', ')}
          </div>
          <div className="mt-1 text-gray-500">Permitidos: {policy.allowed?.slice(0, 15).join(', ')}…</div>
        </div>
      )}

      <div className="flex gap-2 flex-wrap items-center">
        {policy?.authorized_roots?.length > 0 && (
          <select
            value={cwd}
            onChange={(e) => setCwd(e.target.value)}
            className="px-3 py-1.5 text-xs rounded-lg border bg-transparent border-gray-300 dark:border-gray-600 font-mono max-w-[280px]"
            title="Directorio de trabajo"
          >
            <option value="">(raíz por defecto)</option>
            {policy.authorized_roots.map((r: string) => <option key={r} value={r}>{r}</option>)}
          </select>
        )}
        {quickCommands.map((qc) => (
          <button key={qc} onClick={() => setCommand(qc)} className="px-3 py-1 text-xs rounded-full border dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 font-mono">{qc}</button>
        ))}
      </div>

      <div className="flex gap-2">
        <input value={command} onChange={(e) => setCommand(e.target.value)} onKeyDown={onKeyDown} placeholder="Ej: python --version · ↑/↓ historial" className="flex-1 px-4 py-3 rounded-lg border bg-transparent border-gray-300 dark:border-gray-600 font-mono text-sm" />
        <button onClick={() => command.trim() && runCmd.mutate(command)} disabled={runCmd.isPending || !command.trim()} className="btn-primary flex items-center gap-2">
          {runCmd.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />} Ejecutar
        </button>
      </div>

      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
          <History className="w-4 h-4" /> Historial persistente
          <span className="text-xs text-gray-400">({items.length} ejecuciones{historyLoading ? ', cargando…' : ''})</span>
        </div>
        {items.map((h) => (
          <div key={`${h.status === 'REJECTED' ? 'r' : 'h'}-${h.id}`} className="rounded-lg border dark:border-gray-700 overflow-hidden">
            <div className={`px-4 py-2 flex items-center justify-between text-sm ${h.status === 'SUCCEEDED' ? 'bg-green-50 dark:bg-green-900/20' : h.status === 'REJECTED' ? 'bg-yellow-50 dark:bg-yellow-900/20' : 'bg-red-50 dark:bg-red-900/20'}`}>
              <span className="font-mono">$ {h.command}</span>
              <span className="text-xs">{h.status} {h.exit_code !== null && `· exit ${h.exit_code}`} {h.duration_ms != null && h.duration_ms > 0 && `· ${h.duration_ms} ms`}</span>
            </div>
            {h.stdout && <pre className="px-4 py-2 text-xs font-mono bg-gray-50 dark:bg-gray-900 overflow-x-auto max-h-48">{h.stdout}</pre>}
            {h.stderr && <pre className="px-4 py-2 text-xs font-mono text-red-600 dark:text-red-400 bg-red-50/50 dark:bg-red-900/10 overflow-x-auto max-h-32">{h.stderr}</pre>}
          </div>
        ))}
        {items.length === 0 && !historyLoading && <p className="text-sm text-gray-500 text-center py-8">Sin ejecuciones todavía. Prueba un comando de la lista rápida.</p>}
      </div>
    </div>
  )
}

export default AgentPage
