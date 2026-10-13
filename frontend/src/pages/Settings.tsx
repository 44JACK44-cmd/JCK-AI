import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Smartphone, Trash2, Link2, Loader2, KeyRound, Shield, ShieldAlert, ExternalLink } from 'lucide-react'
import { api, KeyInfo, KeyVerify } from '../services/api'

const PROVIDER_META: Record<string, { name: string; free: boolean; url: string; note: string }> = {
  google: { name: 'Google Gemini', free: true, url: 'https://aistudio.google.com/apikey', note: 'Tier gratuito real vía AI Studio (rate-limited)' },
  deepseek: { name: 'DeepSeek', free: false, url: 'https://platform.deepseek.com', note: 'Prepago. Sin saldo = 402. No es ruta gratuita.' },
  anthropic: { name: 'Anthropic Claude', free: false, url: 'https://console.anthropic.com', note: 'Créditos iniciales limitados; no tier gratuito permanente.' },
  openai: { name: 'OpenAI', free: false, url: 'https://platform.openai.com', note: 'Pago obligatorio. Bloqueado en FREE MODE.' },
}

interface DeviceInfo {
  id: number
  name: string
  is_revoked: boolean
  last_seen: string | null
  created_at: string | null
}

const SettingsPage: React.FC = () => {
  const queryClient = useQueryClient()
  const [pairCode, setPairCode] = useState<string | null>(null)
  const [confirmCode, setConfirmCode] = useState('')
  const [deviceToken, setDeviceToken] = useState<string | null>(null)
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({})
  const [verifyResults, setVerifyResults] = useState<Record<string, KeyVerify | null>>({})

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: async () => (await fetch('/health')).json(),
  })

  const { data: freeMode } = useQuery({
    queryKey: ['free-mode'],
    queryFn: async () => (await api.get('/providers/free-mode')).data,
  })

  const { data: keys, refetch: refetchKeys } = useQuery<KeyInfo[]>({
    queryKey: ['keys'],
    queryFn: async () => (await api.get('/keys/')).data,
  })

  const { data: devices } = useQuery<DeviceInfo[]>({
    queryKey: ['devices'],
    queryFn: async () => (await api.get('/devices/')).data,
  })

  const saveKey = useMutation({
    mutationFn: async ({ provider_id, api_key }: { provider_id: string; api_key: string }) =>
      (await api.post('/keys/', { provider_id, api_key })).data as KeyInfo,
    onSuccess: (_data, vars) => {
      setKeyInputs((p) => ({ ...p, [vars.provider_id]: '' }))
      refetchKeys()
      queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
  })

  const verifyKey = useMutation({
    mutationFn: async (provider_id: string) =>
      (await api.post(`/keys/${provider_id}/verify`)).data as KeyVerify,
    onSuccess: (data) => setVerifyResults((p) => ({ ...p, [data.provider_id]: data })),
  })

  const deleteKey = useMutation({
    mutationFn: async (provider_id: string) => (await api.delete(`/keys/${provider_id}`)).data,
    onSuccess: () => {
      refetchKeys()
      queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
  })

  const startPair = useMutation({
    mutationFn: async () => (await api.post('/devices/pair/start', { device_name: 'Android NEXUS' })).data,
    onSuccess: (data) => setPairCode(data.code),
  })

  const confirmPair = useMutation({
    mutationFn: async (code: string) => (await api.post('/devices/pair/confirm', { code })).data,
    onSuccess: (data) => {
      setDeviceToken(data.token)
      setPairCode(null)
      setConfirmCode('')
      queryClient.invalidateQueries({ queryKey: ['devices'] })
    },
  })

  const revoke = useMutation({
    mutationFn: async (id: number) => (await api.delete(`/devices/${id}`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['devices'] }),
  })

  const storedByKey = Object.fromEntries((keys || []).map((k) => [k.provider_id, k]))

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h1 className="text-3xl font-bold gradient-text">Configuración</h1>
        <p className="text-gray-600 dark:text-gray-400">Claves de proveedor, FREE MODE y dispositivos vinculados</p>
      </div>

      {/* ── API Keys ── */}
      <section className="p-5 rounded-lg border dark:border-gray-700">
        <h2 className="font-semibold mb-1 flex items-center gap-2"><KeyRound className="w-4 h-4" /> Claves de proveedores (cifradas en reposo)</h2>
        <p className="text-xs text-gray-500 mb-4">
          Las claves se cifran con Fernet (AES) y nunca se devuelven completas por la API. Verificación real contra la API del proveedor.
        </p>
        <div className="space-y-4">
          {Object.entries(PROVIDER_META).map(([pid, meta]) => {
            const stored = storedByKey[pid]
            const vr = verifyResults[pid]
            return (
              <div key={pid} className="p-4 rounded-lg border dark:border-gray-700">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{meta.name}</span>
                    {meta.free
                      ? <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300 flex items-center gap-1"><Shield className="w-3 h-3" />ruta gratuita</span>
                      : <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300 flex items-center gap-1"><ShieldAlert className="w-3 h-3" />prepago/pago</span>}
                  </div>
                  <a href={meta.url} target="_blank" rel="noreferrer" className="text-xs text-nexus-600 flex items-center gap-1 hover:underline">
                    Obtener clave <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
                <p className="text-xs text-gray-500 mb-2">{meta.note}</p>
                <div className="flex gap-2 items-center flex-wrap">
                  {stored ? (
                    <span className="text-sm font-mono text-gray-600 dark:text-gray-300">{stored.masked} {stored.env_fallback && <span className="text-[10px] text-gray-400">(de .env)</span>}</span>
                  ) : (
                    <span className="text-sm text-gray-400">sin clave</span>
                  )}
                  <input
                    type="password"
                    placeholder={`Pegar clave de ${meta.name}`}
                    value={keyInputs[pid] || ''}
                    onChange={(e) => setKeyInputs((p) => ({ ...p, [pid]: e.target.value }))}
                    className="flex-1 min-w-[200px] px-3 py-1.5 text-sm rounded border bg-transparent border-gray-300 dark:border-gray-600"
                  />
                  <button
                    onClick={() => keyInputs[pid] && saveKey.mutate({ provider_id: pid, api_key: keyInputs[pid] })}
                    disabled={!keyInputs[pid] || saveKey.isPending}
                    className="btn-primary text-sm py-1.5"
                  >Guardar</button>
                  <button
                    onClick={() => verifyKey.mutate(pid)}
                    disabled={verifyKey.isPending}
                    className="btn-secondary text-sm py-1.5"
                  >{verifyKey.isPending ? 'Verificando…' : 'Verificar'}</button>
                  {stored && (
                    <button onClick={() => deleteKey.mutate(pid)} className="text-red-500 p-1.5" title="Eliminar clave"><Trash2 className="w-4 h-4" /></button>
                  )}
                </div>
                {vr && (
                  <div className={`mt-2 text-xs p-2 rounded ${vr.available ? 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300' : 'bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-300'}`}>
                    <strong>{vr.status}</strong> — {vr.message} {vr.free_route && '✓ ruta gratuita verificada'}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </section>

      {/* ── Sistema ── */}
      <section className="p-5 rounded-lg border dark:border-gray-700">
        <h2 className="font-semibold mb-3">Sistema</h2>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div><span className="text-gray-500">Servicio:</span> {health?.service} v{health?.version}</div>
          <div><span className="text-gray-500">Estado:</span> <span className="text-green-600">{health?.status}</span></div>
          <div><span className="text-gray-500">Entorno:</span> {health?.environment}</div>
          <div><span className="text-gray-500">FREE MODE:</span> {health?.free_mode ? 'Activo' : 'Inactivo'}</div>
        </div>
      </section>

      {/* ── FREE MODE ── */}
      <section className="p-5 rounded-lg border dark:border-gray-700">
        <h2 className="font-semibold mb-3">Política FREE MODE</h2>
        {freeMode && (
          <div className="text-sm space-y-1">
            <div>Habilitado: <strong>{freeMode.enabled ? 'Sí' : 'No'} {freeMode.strict && '(estricto)'}</strong></div>
            <div>Proveedores permitidos: {freeMode.allowed_providers?.join(', ') || 'ninguno aún'}</div>
            <div>Bloqueados: {freeMode.blocked_providers?.join(', ') || 'ninguno'}</div>
            <p className="text-xs text-gray-500 mt-2">
              En modo estricto ninguna ruta de pago se ejecuta y no hay fallback hacia proveedores de pago.
            </p>
          </div>
        )}
      </section>

      {/* ── Devices ── */}
      <section className="p-5 rounded-lg border dark:border-gray-700">
        <h2 className="font-semibold mb-1 flex items-center gap-2"><Smartphone className="w-4 h-4" /> Dispositivos vinculados (Android ↔ Windows)</h2>
        <p className="text-xs text-gray-500 mb-3">Emparejamiento iniciado por el usuario con código temporal y token de alcance limitado.</p>

        <div className="flex gap-2 mb-4 flex-wrap">
          <button onClick={() => startPair.mutate()} disabled={startPair.isPending} className="btn-primary text-sm flex items-center gap-1">
            {startPair.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4" />} Generar código
          </button>
          <input value={confirmCode} onChange={(e) => setConfirmCode(e.target.value)} placeholder="Código de 6 dígitos" maxLength={6} className="px-3 py-2 text-sm rounded-lg border bg-transparent border-gray-300 dark:border-gray-600 w-40 font-mono" />
          <button onClick={() => confirmPair.mutate(confirmCode)} disabled={confirmCode.length !== 6 || confirmPair.isPending} className="btn-secondary text-sm">Confirmar</button>
        </div>

        {pairCode && (
          <div className="mb-4 p-3 rounded-lg bg-nexus-50 dark:bg-nexus-900/30 border border-nexus-200 dark:border-nexus-800">
            <div className="text-sm">Código de emparejamiento:</div>
            <div className="text-3xl font-mono font-bold tracking-widest">{pairCode}</div>
            <div className="text-xs text-gray-500">Introdúcelo en la app Android dentro del tiempo límite.</div>
          </div>
        )}

        {deviceToken && (
          <div className="mb-4 p-3 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-300 text-sm">
            <div className="font-medium mb-1">Token emitido (guárdalo de forma segura, no se volverá a mostrar):</div>
            <code className="text-xs break-all">{deviceToken}</code>
          </div>
        )}

        <div className="space-y-2">
          {devices?.length === 0 && <p className="text-sm text-gray-500">Sin dispositivos vinculados.</p>}
          {devices?.map((d) => (
            <div key={d.id} className="flex items-center justify-between p-3 rounded border dark:border-gray-700 text-sm">
              <div>
                <div className="font-medium">{d.name} {d.is_revoked && <span className="text-xs text-red-500 ml-1">(revocado)</span>}</div>
                <div className="text-xs text-gray-500">Vinculado: {d.created_at ? new Date(d.created_at).toLocaleString() : '—'} · Última vez: {d.last_seen ? new Date(d.last_seen).toLocaleString() : 'nunca'}</div>
              </div>
              {!d.is_revoked && (
                <button onClick={() => revoke.mutate(d.id)} className="text-red-500 hover:text-red-700 p-2" title="Revocar"><Trash2 className="w-4 h-4" /></button>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

export default SettingsPage
