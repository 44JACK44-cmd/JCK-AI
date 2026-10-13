import React, { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Send, Plus, Sparkles, Users, Loader2, Workflow, Radio, MessageCircle, Trash2 } from 'lucide-react'
import { api, ProviderInfo, ConversationInfo, MessageInfo, MultiAIResult, OrchestrateResult, QuotaInfo, API_BASE } from '../services/api'

type Mode = 'A' | 'B' | 'C'

const ConversationsPage: React.FC = () => {
  const [mode, setMode] = useState<Mode>('A')
  const queryClient = useQueryClient()

  const { data: providers } = useQuery<ProviderInfo[]>({
    queryKey: ['providers'],
    queryFn: async () => (await api.get('/providers/available')).data,
  })

  const { data: conversations } = useQuery<ConversationInfo[]>({
    queryKey: ['conversations'],
    queryFn: async () => (await api.get('/conversations/')).data,
  })

  const { data: quota } = useQuery<QuotaInfo>({
    queryKey: ['quota'],
    queryFn: async () => (await api.get('/providers/quota')).data,
    refetchInterval: 30000,
  })

  const [activeConv, setActiveConv] = useState<number | null>(null)
  const [input, setInput] = useState('')
  const [objective, setObjective] = useState('')
  const [selectedProviders, setSelectedProviders] = useState<string[]>([])

  // Mode A streaming state
  const [streamText, setStreamText] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [useStreaming, setUseStreaming] = useState(true)
  const streamRef = useRef('')

  // Mode C state
  const [orchResult, setOrchResult] = useState<OrchestrateResult | null>(null)
  const [orchRunning, setOrchRunning] = useState(false)

  const { data: messages } = useQuery<MessageInfo[]>({
    queryKey: ['messages', activeConv],
    queryFn: async () => (await api.get(`/conversations/${activeConv}/messages`)).data,
    enabled: activeConv !== null,
  })

  const [multiResult, setMultiResult] = useState<MultiAIResult | null>(null)

  const createConv = useMutation({
    mutationFn: async (provider_id: string) =>
      (await api.post('/conversations/', { title: `Chat con ${provider_id}`, provider_id })).data as ConversationInfo,
    onSuccess: (conv) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      setActiveConv(conv.id)
    },
  })

  const deleteConv = useMutation({
    mutationFn: async (conversation_id: number) =>
      (await api.delete(`/conversations/${conversation_id}`)).data as { deleted: number },
    onSuccess: (_data, conversation_id) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      if (activeConv === conversation_id) {
        setActiveConv(null)
        setStreamText('')
      }
    },
  })

  const requestDeleteConv = (c: ConversationInfo) => {
    if (window.confirm(`¿Eliminar "${c.title}" y todo su historial?`)) {
      deleteConv.mutate(c.id)
    }
  }

  const sendMessage = useMutation({
    mutationFn: async ({ conversation_id, content }: { conversation_id: number; content: string }) =>
      (await api.post(`/conversations/${conversation_id}/messages`, { content })).data as MessageInfo,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['messages', activeConv] })
      setInput('')
      setStreamText('')
    },
  })

  // Streaming send via SSE
  const sendStreaming = async () => {
    if (!activeConv || !input.trim()) return
    const conv = conversations?.find((c) => c.id === activeConv)
    const providerId = conv?.provider_id || freeProviders[0]?.provider_id
    if (!providerId) return

    const history = (messages || []).slice(-20).map((m) => ({ role: m.role, content: m.content }))
    const userContent = input
    const convId = activeConv
    setInput('')
    setStreaming(true)
    setStreamText('')
    streamRef.current = ''

    // Optimistic: show the user message immediately
    queryClient.setQueryData<MessageInfo[]>(['messages', convId], (old) => [
      ...(old || []),
      { id: -Date.now(), role: 'user', content: userContent, provider_id: providerId, model: null, created_at: new Date().toISOString() },
    ])

    let errorMsg: string | null = null
    try {
      const resp = await fetch(`${API_BASE}/tasks/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider_id: providerId, message: userContent, conversation_id: convId, history }),
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
            const evt = JSON.parse(line.slice(5).trim())
            if (evt.type === 'chunk' && evt.delta) {
              streamRef.current += evt.delta
              setStreamText(streamRef.current)
            } else if (evt.type === 'error') {
              errorMsg = evt.message
              streamRef.current += `\n[ERROR: ${evt.message}]`
              setStreamText(streamRef.current)
            }
          } catch { /* ignore */ }
        }
      }
    } catch (e) {
      errorMsg = String(e)
      setStreamText(`[ERROR de conexión: ${e}]`)
    } finally {
      setStreaming(false)
      // Wait for the persisted messages (user + assistant) before hiding the bubble
      await queryClient.invalidateQueries({ queryKey: ['messages', convId] })
      if (!errorMsg) setStreamText('') // success: swap bubble -> persisted messages
      // on error the bubble stays visible until the next message
    }
  }

  const runMulti = useMutation({
    mutationFn: async () =>
      (await api.post('/tasks/multi', { objective, providers: selectedProviders.length ? selectedProviders : undefined })).data as MultiAIResult,
    onSuccess: (data) => setMultiResult(data),
  })

  const runOrchestrate = async () => {
    if (!objective.trim()) return
    setOrchRunning(true)
    setOrchResult(null)
    try {
      const resp = await api.post('/tasks/orchestrate', { objective, providers: selectedProviders.length ? selectedProviders : undefined })
      setOrchResult(resp.data as OrchestrateResult)
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Error de orquestación'
      setOrchResult({ task_id: 0, status: 'FAILED', objective, subtasks: [], succeeded: 0, failed: 0, providers_used: [], error: detail })
    } finally {
      setOrchRunning(false)
    }
  }

  const freeProviders = providers?.filter((p) => p.free && p.available) || []

  const statusColor: Record<string, string> = {
    SUCCEEDED: 'text-green-500', FAILED: 'text-red-500', RUNNING: 'text-blue-500 animate-pulse',
    PENDING: 'text-gray-400', RETRYING: 'text-yellow-500', CANCELLED: 'text-gray-400',
  }

  return (
    <div className="space-y-6 h-[calc(100vh-8rem)]">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold gradient-text">Conversaciones</h1>
          <p className="text-gray-600 dark:text-gray-400">Individual · Colaboración · Orquestación</p>
        </div>
        <div className="flex items-center gap-3">
          {quota && quota.models.length > 0 && (
            <span
              title="Mensajes gratis disponibles en la ventana actual (estilo Copilot). Si un modelo se agota, falla al siguiente automáticamente."
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border ${quota.can_chat ? 'border-green-300 bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300 dark:border-green-700' : 'border-yellow-300 bg-yellow-50 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300 dark:border-yellow-700'}`}
            >
              <MessageCircle className="w-3.5 h-3.5" />
              {quota.can_chat
                ? (() => {
                    const withLimit = quota.active_models
                      .map((id) => quota.models.find((m) => m.model === id))
                      .find((m) => m != null && m.known_limit != null)
                    return withLimit && withLimit.known_limit != null
                      ? `Chat: ${withLimit.known_limit - withLimit.messages_used} mensajes libres`
                      : 'Chat listo'
                  })()
                : (() => {
                    const secs = quota.models.map((m) => m.seconds_until_reset ?? 0).sort((a, b) => b - a)[0]
                    const mins = secs ? Math.ceil(secs / 60) : null
                    return `Cuota al límite${mins ? ` · en ${mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins}m`}` : ''}`
                  })()}
            </span>
          )}
          <div className="flex rounded-lg overflow-hidden border border-gray-300 dark:border-gray-600">
            <button onClick={() => setMode('A')} className={`px-3 py-2 text-sm flex items-center gap-1 ${mode === 'A' ? 'bg-nexus-600 text-white' : ''}`}><Sparkles className="w-4 h-4" />A</button>
            <button onClick={() => setMode('B')} className={`px-3 py-2 text-sm flex items-center gap-1 ${mode === 'B' ? 'bg-nexus-600 text-white' : ''}`}><Users className="w-4 h-4" />B</button>
            <button onClick={() => setMode('C')} className={`px-3 py-2 text-sm flex items-center gap-1 ${mode === 'C' ? 'bg-nexus-600 text-white' : ''}`}><Workflow className="w-4 h-4" />C</button>
          </div>
        </div>
      </div>

      {freeProviders.length === 0 && (
        <div className="p-4 rounded-lg bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-300 text-sm">
          No hay proveedores gratuitos disponibles. Ve a <strong>Configuración → Claves</strong> y añade una clave de Google Gemini (tier gratuito) desde <a className="underline" href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">aistudio.google.com/apikey</a>.
        </div>
      )}

      {/* ── MODE A ── */}
      {mode === 'A' && (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 h-[calc(100%-6rem)]">
          <div className="lg:col-span-1 space-y-2 overflow-y-auto">
            <button onClick={() => freeProviders[0] && createConv.mutate(freeProviders[0].provider_id)} disabled={!freeProviders.length || createConv.isPending} className="btn-primary w-full flex items-center justify-center gap-2">
              <Plus className="w-4 h-4" /> Nueva conversación
            </button>
            {conversations?.map((c) => (
              <div key={c.id} className={`flex items-center gap-1 rounded-lg border ${activeConv === c.id ? 'border-nexus-500 bg-nexus-50 dark:bg-nexus-900/30' : 'border-gray-200 dark:border-gray-700'}`}>
                <button onClick={() => { setActiveConv(c.id); setStreamText('') }} className="flex-1 text-left p-3 min-w-0">
                  <div className="font-medium text-sm truncate">{c.title}</div>
                  <div className="text-xs text-gray-500">{c.provider_id}</div>
                </button>
                <button
                  onClick={() => requestDeleteConv(c)}
                  title="Eliminar conversación"
                  className="p-2 mr-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
          <div className="lg:col-span-3 flex flex-col border rounded-lg dark:border-gray-700">
            <div className="flex items-center justify-between px-3 py-2 border-b dark:border-gray-700">
              <span className="text-xs text-gray-500">{activeConv ? `Conversación #${activeConv}` : 'Sin selección'}</span>
              <label className="flex items-center gap-1 text-xs text-gray-500 cursor-pointer">
                <input type="checkbox" checked={useStreaming} onChange={(e) => setUseStreaming(e.target.checked)} />
                <Radio className="w-3 h-3" /> streaming
              </label>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {!activeConv && <p className="text-gray-500 text-center mt-10">Selecciona o crea una conversación</p>}
              {messages?.map((m) => (
                <div key={m.id} className={`max-w-[80%] p-3 rounded-lg ${m.role === 'user' ? 'ml-auto bg-nexus-600 text-white' : 'bg-gray-100 dark:bg-gray-800'}`}>
                  <div className="text-[11px] opacity-60 mb-1">{m.role === 'user' ? 'Tú' : m.provider_id}{m.model ? ` · ${m.model}` : ''}</div>
                  <div className="whitespace-pre-wrap text-sm">{m.content}</div>
                </div>
              ))}
              {(streaming || streamText) && (
                <div className="max-w-[80%] p-3 rounded-lg bg-gray-100 dark:bg-gray-800">
                  <div className="text-[11px] opacity-60 mb-1 flex items-center gap-1"><Radio className="w-3 h-3 animate-pulse" /> {streaming ? 'en vivo' : 'respuesta'}</div>
                  <div className="whitespace-pre-wrap text-sm">{streamText}<span className="inline-block w-2 h-4 bg-nexus-500 animate-pulse ml-0.5" /></div>
                </div>
              )}
            </div>
            <div className="p-3 border-t dark:border-gray-700 flex gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && activeConv && input.trim() && !streaming) {
                    useStreaming ? sendStreaming() : sendMessage.mutate({ conversation_id: activeConv, content: input })
                  }
                }}
                placeholder={activeConv ? 'Escribe un mensaje…' : 'Crea una conversación primero'}
                className="flex-1 px-3 py-2 rounded-lg border bg-transparent border-gray-300 dark:border-gray-600 text-sm"
                disabled={streaming}
              />
              <button
                onClick={() => activeConv && input.trim() && (useStreaming ? sendStreaming() : sendMessage.mutate({ conversation_id: activeConv, content: input }))}
                disabled={!activeConv || !input.trim() || streaming || sendMessage.isPending}
                className="btn-primary"
              >
                {streaming || sendMessage.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── MODE B ── */}
      {mode === 'B' && (
        <div className="space-y-4">
          <textarea value={objective} onChange={(e) => setObjective(e.target.value)} placeholder="Describe la tarea para los modelos…" rows={3} className="w-full px-4 py-3 rounded-lg border bg-transparent border-gray-300 dark:border-gray-600" />
          <div className="flex gap-2 flex-wrap">
            {freeProviders.map((p) => (
              <label key={p.provider_id} className={`px-3 py-1.5 rounded-full text-sm border cursor-pointer flex items-center gap-1 ${selectedProviders.includes(p.provider_id) ? 'bg-nexus-600 text-white border-nexus-600' : 'border-gray-300 dark:border-gray-600'}`}>
                <input type="checkbox" className="hidden" checked={selectedProviders.includes(p.provider_id)} onChange={(e) => setSelectedProviders((prev) => e.target.checked ? [...prev, p.provider_id] : prev.filter((x) => x !== p.provider_id))} />
                {p.name}
              </label>
            ))}
          </div>
          <button onClick={() => runMulti.mutate()} disabled={!objective.trim() || runMulti.isPending} className="btn-primary flex items-center gap-2">
            {runMulti.isPending ? <><Loader2 className="w-4 h-4 animate-spin" /> Ejecutando…</> : <>Ejecutar en {selectedProviders.length || freeProviders.length} modelos</>}
          </button>
          {multiResult && (
            <div className="space-y-4">
              <div className="text-sm text-gray-600 dark:text-gray-400">Tarea #{multiResult.task_id} · {multiResult.status}</div>
              <div className="grid gap-3 md:grid-cols-2">
                {multiResult.responses.map((r) => (
                  <div key={r.provider_id} className="p-4 rounded-lg border dark:border-gray-700">
                    <div className="flex justify-between text-sm font-medium mb-2">
                      <span>{r.provider_id}{r.model ? ` · ${r.model}` : ''}</span>
                      <span className="text-xs text-gray-500">{r.latency_ms} ms · {r.status}</span>
                    </div>
                    <div className="text-sm whitespace-pre-wrap max-h-64 overflow-y-auto">{r.content || r.error}</div>
                  </div>
                ))}
              </div>
              {multiResult.synthesis && (
                <div className="p-4 rounded-lg border border-nexus-300 dark:border-nexus-700 bg-nexus-50/50 dark:bg-nexus-900/20">
                  <h3 className="font-semibold mb-2">Síntesis consolidada</h3>
                  <div className="text-sm whitespace-pre-wrap">{multiResult.synthesis}</div>
                </div>
              )}
              {multiResult.disagreements.length > 0 && (
                <div className="p-4 rounded-lg bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-300">
                  <h3 className="font-semibold mb-1 text-sm">Discrepancias detectadas</h3>
                  <ul className="text-sm list-disc pl-5">{multiResult.disagreements.map((d, i) => <li key={i}>{d}</li>)}</ul>
                </div>
              )}
              {multiResult.limitations.length > 0 && (
                <div className="p-4 rounded-lg bg-gray-50 dark:bg-gray-800 border text-sm">
                  <h3 className="font-semibold mb-1">Limitaciones</h3>
                  <ul className="list-disc pl-5">{multiResult.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── MODE C ── */}
      {mode === 'C' && (
        <div className="space-y-4">
          <div>
            <h2 className="font-semibold flex items-center gap-2 mb-1"><Workflow className="w-4 h-4" /> Orquestador de objetivos</h2>
            <p className="text-sm text-gray-500">Describe un objetivo; el sistema lo descompone en subtareas con dependencias y las ejecuta en paralelo cuando es posible.</p>
          </div>
          <textarea value={objective} onChange={(e) => setObjective(e.target.value)} placeholder="Ej: Analiza la estructura de este proyecto, identifica el lenguaje y las dependencias, y produce un informe de riesgos…" rows={4} className="w-full px-4 py-3 rounded-lg border bg-transparent border-gray-300 dark:border-gray-600" />
          <button onClick={runOrchestrate} disabled={!objective.trim() || orchRunning || freeProviders.length === 0} className="btn-primary flex items-center gap-2">
            {orchRunning ? <><Loader2 className="w-4 h-4 animate-spin" /> Orquestando…</> : <>Planificar y ejecutar</>}
          </button>

          {orchResult && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 text-sm">
                <span className={`font-semibold ${statusColor[orchResult.status] || ''}`}>{orchResult.status}</span>
                <span className="text-gray-500">Tarea #{orchResult.task_id}</span>
                <span className="text-gray-500">{orchResult.succeeded} ok · {orchResult.failed} fallos</span>
                {orchResult.providers_used.length > 0 && <span className="text-gray-500">Proveedores: {orchResult.providers_used.join(', ')}</span>}
              </div>
              {orchResult.error && <div className="p-3 rounded bg-red-50 dark:bg-red-900/20 text-red-600 text-sm">{orchResult.error}</div>}
              <div className="space-y-2">
                {orchResult.subtasks.map((st) => (
                  <div key={st.id} className="p-3 rounded-lg border dark:border-gray-700">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-gray-400">{st.id}</span>
                        <span className="font-medium text-sm">{st.title}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500">{st.kind}</span>
                      </div>
                      <span className={`text-xs font-medium ${statusColor[st.status] || ''}`}>{st.status}{st.attempts > 1 ? ` (${st.attempts} intentos)` : ''}</span>
                    </div>
                    {st.depends_on.length > 0 && <div className="text-[11px] text-gray-400 mt-1">Depende de: {st.depends_on.join(', ')}</div>}
                    {st.result && <div className="mt-2 text-sm whitespace-pre-wrap max-h-48 overflow-y-auto text-gray-700 dark:text-gray-300">{st.result}</div>}
                    {st.error && <div className="mt-2 text-xs text-red-500">{st.error}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default ConversationsPage
