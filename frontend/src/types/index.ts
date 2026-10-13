// AI Provider Types
export interface AIProvider {
  name: string
  provider_id: string
  available: boolean
  free: boolean
  status: ProviderStatus
  capabilities: string[]
  limits: Record<string, any>
  last_checked: string
  model: string
  requires_auth: boolean
  auth_method: string
}

export type ProviderStatus = 
  | 'FREE_AVAILABLE'
  | 'FREE_LIMIT_REACHED'
  | 'AUTH_REQUIRED'
  | 'UNAVAILABLE'
  | 'PAID_ROUTE_BLOCKED'
  | 'UNSUPPORTED'
  | 'RATE_LIMITED'
  | 'ERROR'

// Conversation Types
export interface Message {
  id: string
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  timestamp: string
  metadata?: Record<string, any>
}

export interface Conversation {
  id: string
  title: string
  provider_id: string
  model: string
  messages: Message[]
  created_at: string
  updated_at: string
  metadata?: Record<string, any>
}

// Task Types
export type TaskStatus = 
  | 'PENDING'
  | 'RUNNING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'RETRYING'
  | 'CANCELLED'
  | 'WAITING_APPROVAL'

export interface Task {
  id: string
  title: string
  description: string
  status: TaskStatus
  progress: number
  created_at: string
  started_at?: string
  completed_at?: string
  provider_ids: string[]
  result?: any
  error?: string
  metadata?: Record<string, any>
}

// Project Types
export interface ProjectFile {
  name: string
  path: string
  type: 'file' | 'directory'
  size?: number
  last_modified: string
  content?: string
}

export interface Project {
  id: string
  name: string
  path: string
  type: string
  created_at: string
  updated_at: string
  files: ProjectFile[]
  metadata?: Record<string, any>
}

// Brain (Visualization) Types
export interface BrainNode {
  id: string
  type: 'provider' | 'agent' | 'tool' | 'task'
  label: string
  status: TaskStatus
  position: { x: number; y: number }
  metadata?: Record<string, any>
}

export interface BrainEdge {
  id: string
  source: string
  target: string
  label?: string
  type: string
}

export interface BrainState {
  nodes: BrainNode[]
  edges: BrainEdge[]
  timestamp: string
}

// Memory & Learning Types
export interface MemoryEntry {
  id: string
  task_id: string
  objective: string
  providers_used: string[]
  tools_used: string[]
  result: any
  evaluation: {
    accuracy: number
    quality: number
    efficiency: number
  }
  created_at: string
}

// Device Pairing Types
export interface Device {
  id: string
  name: string
  type: 'windows' | 'android' | 'web'
  last_seen: string
  status: 'online' | 'offline' | 'pairing'
  capabilities: string[]
}

// API Response Types
export interface ApiResponse<T = any> {
  success: boolean
  data?: T
  error?: string
  message?: string
  timestamp: string
}

export interface PaginatedResponse<T = any> extends ApiResponse<T[]> {
  page: number
  page_size: number
  total: number
  total_pages: number
}

// Event Types for WebSocket
export interface SystemEvent {
  type: string
  data: any
  timestamp: string
}

export interface TaskEvent extends SystemEvent {
  type: 'task_created' | 'task_updated' | 'task_completed' | 'task_failed'
  data: Task
}

export interface ProviderEvent extends SystemEvent {
  type: 'provider_status_changed'
  data: AIProvider
}

// Configuration Types
export interface FreeModeConfig {
  enabled: boolean
  strict: boolean
  blocked_providers: string[]
  allowed_providers: string[]
  policy_version: string
  last_updated: string
}

// User Types
export interface User {
  id: string
  email: string
  name: string
  avatar?: string
  preferences: UserPreferences
  created_at: string
}

export interface UserPreferences {
  theme: 'light' | 'dark' | 'auto'
  language: string
  notifications: {
    email: boolean
    push: boolean
    task_updates: boolean
  }
}

// File System Types
export interface FileOperation {
  type: 'read' | 'write' | 'create' | 'delete' | 'move'
  path: string
  content?: string
  new_path?: string
  timestamp: string
  success: boolean
  error?: string
}

// Terminal Types
export interface TerminalCommand {
  id: string
  command: string
  working_dir: string
  status: 'running' | 'completed' | 'failed'
  output?: string
  error?: string
  exit_code?: number
  started_at: string
  completed_at?: string
  duration?: number
}