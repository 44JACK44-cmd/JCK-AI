import axios from 'axios'

// Running inside a Tauri desktop window → talk to the local backend directly;
// in the browser (Vite dev / static hosting) → same-origin with a proxy.
export const IS_TAURI =
  typeof window !== 'undefined' &&
  ('__TAURI__' in window || '__TAURI_IPC__' in window || '__TAURI_METADATA__' in window)

// Capacitor (Android) → WebView loads local assets, so the backend must be
// reached over the LAN. Priority: localStorage override > build-time
// VITE_BACKEND_URL > localhost fallback (emulator).
const IS_CAPACITOR =
  typeof window !== 'undefined' && 'Capacitor' in window

const capacitorBackend = (() => {
  if (!IS_CAPACITOR) return ''
  const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('nexus_backend_url') : null
  const fromEnv = (import.meta as { env?: Record<string, string | undefined> }).env?.VITE_BACKEND_URL
  return (stored || fromEnv || 'http://127.0.0.1:8000').replace(/\/$/, '')
})()

export const API_BASE = IS_TAURI
  ? 'http://127.0.0.1:8000/api/v1'
  : IS_CAPACITOR
    ? `${capacitorBackend}/api/v1`
    : '/api/v1'

// Stored backend URL for the Android app (empty when not in Capacitor).
export const BACKEND_OVERRIDE = IS_CAPACITOR ? capacitorBackend : ''

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000,
})

export interface ProviderInfo {
  name: string
  provider_id: string
  available: boolean
  free: boolean
  status: string
  capabilities: string[]
  limits: Record<string, unknown>
  last_checked: string
  model: string
  requires_auth: boolean
  auth_method: string
}

export interface TaskInfo {
  id: number
  objective: string
  mode: string
  status: string
  providers: string[]
  result: string | null
  error: string | null
  created_at: string | null
}

export interface ConversationInfo {
  id: number
  title: string
  provider_id: string | null
  model: string | null
  created_at: string
  updated_at: string | null
}

export interface MessageInfo {
  id: number
  role: string
  content: string
  provider_id: string | null
  model: string | null
  created_at: string
}

export interface MultiAIResult {
  task_id: number
  status: string
  responses: {
    provider_id: string
    status: string
    content: string | null
    model?: string
    error: string | null
    latency_ms: number
  }[]
  synthesis: string | null
  disagreements: string[]
  limitations: string[]
}

export interface BrainStateInfo {
  tasks: {
    id: number
    objective: string
    mode: string
    status: string
    providers: string[]
    created_at: string | null
  }[]
  status_counts: Record<string, number>
  providers: {
    name: string
    provider_id: string
    available: boolean
    free: boolean
    status: string
  }[]
  free_mode: { enabled: boolean; strict: boolean }
  memory_enabled: boolean
  recent_events: number
}

export interface FileEntry {
  name: string
  path: string
  is_dir: boolean
  size: number | null
  modified: number
}

export interface KeyInfo {
  provider_id: string
  masked: string
  updated_at: string | null
  env_fallback: boolean
}

export interface KeyVerify {
  provider_id: string
  available: boolean
  status: string
  message: string
  free_route: boolean
}

export interface SubtaskResult {
  id: string
  kind: string
  title: string
  status: string
  result: string | null
  error: string | null
  depends_on: string[]
  provider_id: string | null
  attempts: number
  latency_ms: number
}

export interface OrchestrateResult {
  task_id: number
  status: string
  objective: string
  subtasks: SubtaskResult[]
  succeeded: number
  failed: number
  providers_used: string[]
  error?: string
}

export interface QuotaModel {
  model: string
  messages_used: number
  known_limit: number | null
  available: boolean
  resets_at: string | null
  seconds_until_reset: number | null
  retry_text: string | null
}

export interface QuotaInfo {
  provider_id: string
  window_seconds: number
  models: QuotaModel[]
  can_chat: boolean
  active_models: string[]
  exhausted_models: string[]
}

export interface GitStatus {
  is_repo: boolean
  branch: string | null
  files: { path: string; index: string; worktree: string; label: string }[]
  ahead: number
  behind: number
  error: string | null
}

export interface GitDiff {
  is_repo: boolean
  diff: string
  truncated: boolean
  error: string | null
}

export interface GitCommitResult {
  ok: boolean
  output: string
  error: string | null
}

export interface WebSearchResult {
  query: string
  provider: string
  count: number
  results: { title: string; url: string; snippet: string }[]
}

export interface MemorySearchHit {
  id: number
  task_id: string | null
  objective: string | null
  outcome: string | null
  evaluation: string | null
  created_at: string | null
  score: number
}

export interface MemorySearchResult {
  query: string
  count: number
  indexed: number
  results: MemorySearchHit[]
}

export interface AgentEvent {
  event: 'start' | 'step' | 'tool' | 'observation' | 'final' | 'error' | 'done' | 'end'
  task_id?: number
  provider?: string
  cwd?: string
  max_steps?: number
  step?: number
  thought?: string
  action?: string
  params?: Record<string, unknown>
  output?: string
  answer?: string
  detail?: string
  status?: string
  steps?: number
  tools_used?: string[]
  duration_ms?: number
  exhausted?: boolean
}

export interface ScheduledTaskInfo {
  id: number
  name: string
  objective: string
  mode: string
  providers: string[]
  interval_minutes: number
  enabled: boolean
  last_run_at: string | null
  last_status: string | null
  last_result: string | null
  run_count: number
  created_at: string | null
}
