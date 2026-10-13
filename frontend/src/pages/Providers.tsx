import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Shield, RefreshCw, KeyRound, CheckCircle, XCircle, AlertTriangle, MessageCircle } from 'lucide-react'
import { api, ProviderInfo, QuotaInfo } from '../services/api'

const statusColor: Record<string, string> = {
  FREE_AVAILABLE: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  FREE_LIMIT_REACHED: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
  AUTH_REQUIRED: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  UNAVAILABLE: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  PAID_ROUTE_BLOCKED: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300',
  UNSUPPORTED: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
}

const ProvidersPage: React.FC = () => {
  const queryClient = useQueryClient()
  const [testKeys, setTestKeys] = useState<Record<string, string>>({})
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; message: string }>>({})

  const { data: providers, isLoading, refetch } = useQuery<ProviderInfo[]>({
    queryKey: ['providers'],
    queryFn: async () => (await api.get('/providers/')).data,
    refetchInterval: 60000,
  })

  const { data: freeMode } = useQuery({
    queryKey: ['free-mode'],
    queryFn: async () => (await api.get('/providers/free-mode')).data,
  })

  const { data: quota } = useQuery<QuotaInfo>({
    queryKey: ['quota'],
    queryFn: async () => (await api.get('/providers/quota')).data,
    refetchInterval: 30000,
  })

  const checkMutation = useMutation({
    mutationFn: async ({ provider_id, api_key }: { provider_id: string; api_key?: string }) =>
      (await api.post('/providers/check', { provider_id, api_key })).data,
    onSuccess: (data, vars) => {
      setTestResults((prev) => ({
        ...prev,
        [vars.provider_id]: { ok: data.available, message: data.message },
      }))
      queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
    onError: (err: unknown, vars) => {
      const message = axiosMessage(err)
      setTestResults((prev) => ({ ...prev, [vars.provider_id]: { ok: false, message } }))
    },
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold gradient-text">Proveedores IA</h1>
          <p className="text-gray-600 dark:text-gray-400">
            Estado real de integraciones y política FREE MODE
          </p>
        </div>
        <button onClick={() => refetch()} className="btn-secondary flex items-center gap-2">
          <RefreshCw className="w-4 h-4" /> Actualizar
        </button>
      </div>

      {freeMode && (
        <div className={`p-4 rounded-lg border ${freeMode.enabled ? 'border-green-300 bg-green-50 dark:bg-green-900/20 dark:border-green-800' : 'border-yellow-300 bg-yellow-50 dark:bg-yellow-900/20'}`}>
          <div className="flex items-center gap-2">
            <Shield className={`w-5 h-5 ${freeMode.enabled ? 'text-green-600' : 'text-yellow-600'}`} />
            <span className="font-medium">
              FREE MODE {freeMode.enabled ? 'ACTIVO' : 'INACTIVO'} {freeMode.strict ? '(estricto)' : '(no estricto)'}
            </span>
            <span className="text-sm text-gray-600 dark:text-gray-400 ml-4">
              Permitidos: {freeMode.allowed_providers?.join(', ') || '—'}
              {freeMode.blocked_providers?.length > 0 && <> · Bloqueados: {freeMode.blocked_providers.join(', ')}</>}
            </span>
          </div>
        </div>
      )}

      {quota && quota.models.length > 0 && (
        <div className={`p-4 rounded-lg border ${quota.can_chat ? 'border-green-300 bg-green-50 dark:bg-green-900/20 dark:border-green-800' : 'border-yellow-300 bg-yellow-50 dark:bg-yellow-900/20'}`}>
          <div className="flex items-center gap-2 mb-2">
            <MessageCircle className={`w-5 h-5 ${quota.can_chat ? 'text-green-600' : 'text-yellow-600'}`} />
            <span className="font-medium">
              Chat libre: {quota.can_chat ? 'disponible ahora' : `agotado temporalmente (libera en ${quota.exhausted_models.length > 0 ? '~' + formatReset(quota) : 'unos minutos'})`}
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400 ml-auto">
              ventana actual: últimas {Math.round(quota.window_seconds / 60)} min
            </span>
          </div>
          <div className="space-y-1.5">
            {quota.models.map((m) => (
              <div key={m.model} className="flex items-center gap-3 text-sm">
                <span className={`w-2 h-2 rounded-full ${m.available ? 'bg-green-500' : 'bg-yellow-500'}`} />
                <span className="font-mono text-xs text-gray-700 dark:text-gray-300">{m.model}</span>
                <span className="text-gray-600 dark:text-gray-400">
                  {m.known_limit != null
                    ? `${m.messages_used}/${m.known_limit} mensajes`
                    : `${m.messages_used} mensajes en ventana`}
                </span>
                {!m.available && m.retry_text && (
                  <span className="text-xs text-yellow-700 dark:text-yellow-400">
                    libera en {m.retry_text}
                  </span>
                )}
                {m.available && m.known_limit != null && m.known_limit > m.messages_used && (
                  <span className="text-xs text-green-700 dark:text-green-400">
                    quedan {m.known_limit - m.messages_used}
                  </span>
                )}
              </div>
            ))}
          </div>
          <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-2">
            Cada mensaje normal del chat consume 1 unidad. Si un modelo se agota, el sistema usa automáticamente el siguiente (failover).
          </p>
        </div>
      )}

      {isLoading ? (
        <div className="animate-pulse space-y-3">
          {[...Array(4)].map((_, i) => <div key={i} className="h-20 bg-gray-200 dark:bg-gray-700 rounded-lg" />)}
        </div>
      ) : (
        <div className="space-y-3">
          {providers?.map((p) => (
            <div key={p.provider_id} className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-3">
                  {p.available ? <CheckCircle className="w-5 h-5 text-green-500" /> : p.status === 'PAID_ROUTE_BLOCKED' ? <AlertTriangle className="w-5 h-5 text-purple-500" /> : <XCircle className="w-5 h-5 text-gray-400" />}
                  <div>
                    <div className="font-semibold text-gray-900 dark:text-white">{p.name}</div>
                    <div className="text-xs text-gray-500">
                      {p.provider_id} · {p.auth_method} · verificado {new Date(p.last_checked).toLocaleString()}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`px-3 py-1 rounded-full text-xs font-medium ${statusColor[p.status] || ''}`}>{p.status}</span>
                  {p.free && <span className="text-xs text-green-600 dark:text-green-400 flex items-center gap-1"><Shield className="w-3 h-3" />gratis</span>}
                </div>
              </div>
              <div className="mt-3 flex items-center gap-2 flex-wrap">
                <KeyRound className="w-4 h-4 text-gray-400" />
                <input
                  type="password"
                  placeholder={`API key de ${p.name} (opcional)`}
                  value={testKeys[p.provider_id] || ''}
                  onChange={(e) => setTestKeys((prev) => ({ ...prev, [p.provider_id]: e.target.value }))}
                  className="flex-1 min-w-[220px] px-3 py-1.5 text-sm rounded border bg-transparent border-gray-300 dark:border-gray-600"
                />
                <button
                  onClick={() => checkMutation.mutate({ provider_id: p.provider_id, api_key: testKeys[p.provider_id] || undefined })}
                  disabled={checkMutation.isPending}
                  className="btn-primary text-sm py-1.5"
                >
                  {checkMutation.isPending ? 'Probando…' : 'Probar conexión'}
                </button>
                {testResults[p.provider_id] && (
                  <span className={`text-xs ${testResults[p.provider_id].ok ? 'text-green-600' : 'text-red-500'}`}>
                    {testResults[p.provider_id].message}
                  </span>
                )}
              </div>
              {p.capabilities?.length > 0 && (
                <div className="mt-2 flex gap-2 flex-wrap">
                  {p.capabilities.map((c) => (
                    <span key={c} className="px-2 py-0.5 text-[11px] rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">{c}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function axiosMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const resp = (err as { response?: { data?: { detail?: string } } }).response
    return resp?.data?.detail || 'Error de conexión'
  }
  return String(err)
}

function formatReset(quota: QuotaInfo): string {
  const seconds = quota.exhausted_models
    .map((id) => quota.models.find((m) => m.model === id)?.seconds_until_reset ?? 0)
    .sort((a, b) => b - a)[0]
  if (!seconds) return 'unos minutos'
  const m = Math.ceil(seconds / 60)
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m} min`
}

export default ProvidersPage
