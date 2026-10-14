import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Play, Shield, Loader2, History, Bot, Square } from 'lucide-react'
import { api, AgentEvent, API_BASE } from '../services/api'

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

  // ── Autonomous mode (Phase 5) ──
  const [objective, setObjective] = useState('')
  const [maxSteps, setMaxSteps] = useState(8)
  const [agentRunning, setAgentRunning] = useState(false)
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([])
  const agentAbortRef = React.useRef<AbortController | null>(null)

  const runAgent = async () => {
    if (!objective.trim() || agentRunning) return
    setAgentRunning(true)
    setAgentEvents([])
    const ctrl = new AbortController()
    agentAbortRef.current = ctrl
    try {
      const resp = await fetch(`${API_BASE}/agent/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ objective, max_steps: maxSteps, cwd: cwd || undefined }),
        signal: ctrl.signal,
      })
      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          try {
            const evt = JSON.parse(line.slice(5).trim()) as AgentEvent
            setAgentEvents((prev) => [...prev, evt])
          } catch { /* ignore partial */ }
        }
      }
    } catch (e: unknown) {
      if ((e as Error).name !== 'AbortError') {
        setAgentEvents((prev) => [...prev, { event: 'error', detail: String(e) }])
      }
    } finally {
      setAgentRunning(false)
      agentAbortRef.current = null
    }
  }

  const stopAgent = () => {
    agentAbortRef.current?.abort()
    setAgentRunning(false)
  }

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
        <p className="text-gray-600 dark:text-gray-400">Terminal validada + agente autónomo (plan→act→observe) con herramientas reales</p>
      </div>

      {/* ── Autonomous mode (Phase 5) ── */}
      <div className="rounded-xl border dark:border-gray-700 p-4 space-y-3 bg-white dark:bg-gray-900/40">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 font-semibold">
            <Bot className="w-5 h-5 text-nexus-600" /> Modo autónomo
            <span className="text-xs font-normal text-gray-500">filesystem · terminal · web</span>
          </div>
          {agentRunning && (
            <button onClick={stopAgent} className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300">
              <Square className="w-3 h-3" /> Detener
            </button>
          )}
        </div>
        <textarea
          value={objective}
          onChange={(e) => setObjective(e.target.value)}
          placeholder="Objetivo autónomo… ej: crea un archivo nota.txt con el resumen de FastAPI buscando en la web"
          rows={2}
          className="w-full px-3 py-2 rounded-lg border bg-transparent border-gray-300 dark:border-gray-600 text-sm"
          disabled={agentRunning}
        />
        <div className="flex items-center gap-3">
          <label className="text-xs text-gray-500 flex items-center gap-2">
            Pasos máx:
            <select value={maxSteps} onChange={(e) => setMaxSteps(Number(e.target.value))} disabled={agentRunning}
              className="px-2 py-1 rounded border bg-transparent border-gray-300 dark:border-gray-600 text-xs">
              {[4, 6, 8, 12, 16].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <button
            onClick={runAgent}
            disabled={agentRunning || !objective.trim()}
            className="btn-primary flex items-center gap-2 text-sm"
          >
            {agentRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            Ejecutar agente
          </button>
        </div>

        {agentEvents.length > 0 && (
          <div className="rounded-lg border dark:border-gray-700 max-h-80 overflow-y-auto divide-y divide-gray-100 dark:divide-gray-800">
            {agentEvents.map((evt, i) => (
              <div key={i} className="px-3 py-2 text-xs">
                {evt.event === 'start' && (
                  <span className="text-green-600 dark:text-green-400">▶ Iniciado · task #{evt.task_id} · proveedor {evt.provider} · cwd {evt.cwd}</span>
                )}
                {evt.event === 'step' && evt.thought && (
                  <div>
                    <span className="font-semibold text-nexus-600 dark:text-nexus-400">Paso {evt.step}</span>
                    <span className="ml-2 text-gray-500 italic">{evt.thought}</span>
                    {evt.action && <span className="ml-2 font-mono text-[11px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800">{evt.action}</span>}
                  </div>
                )}
                {evt.event === 'tool' && evt.action && evt.action !== '_reprompt' && (
                  <div className="font-mono text-[11px] text-blue-600 dark:text-blue-400">🔧 {evt.action} {JSON.stringify(evt.params || {}).slice(0, 160)}</div>
                )}
                {evt.event === 'observation' && (
                  <pre className="mt-1 whitespace-pre-wrap text-[11px] font-mono bg-gray-50 dark:bg-gray-900 rounded p-2 max-h-32 overflow-y-auto">{evt.output}</pre>
                )}
                {evt.event === 'final' && (
                  <div className="mt-1 p-2 rounded bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300 whitespace-pre-wrap">
                    ✅ {evt.answer}
                  </div>
                )}
                {evt.event === 'error' && (
                  <div className="text-red-600 dark:text-red-400">✗ {evt.detail}</div>
                )}
                {evt.event === 'done' && (
                  <div className="text-gray-500 mt-1">Fin · {evt.status} · {evt.steps ?? '?'} pasos · {evt.tools_used?.join(', ') || 'sin herramientas'} · {evt.duration_ms} ms</div>
                )}
              </div>
            ))}
          </div>
        )}
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
