import { useEffect, useRef, useState } from 'react'

export interface BrainEvent {
  id: string
  type: string
  task_id: number | null
  status: string | null
  timestamp: number
  data: Record<string, unknown>
}

/**
 * Subscribe to the backend SSE brain event stream (real events only).
 */
export function useEventStream(path = '/api/v1/brain/events?limit=50') {
  const [events, setEvents] = useState<BrainEvent[]>([])
  const [connected, setConnected] = useState(false)
  const sourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    const source = new EventSource(path)
    sourceRef.current = source

    source.onopen = () => setConnected(true)
    source.onerror = () => setConnected(false)
    source.onmessage = (msg) => {
      try {
        const event: BrainEvent = JSON.parse(msg.data)
        setEvents((prev) => [...prev.slice(-499), event])
      } catch {
        /* ignore malformed events */
      }
    }

    return () => {
      source.close()
      sourceRef.current = null
      setConnected(false)
    }
  }, [path])

  return { events, connected }
}

/** Kept for API compatibility with App.tsx; real transport is SSE. */
export function useSocket() {
  return useEventStream()
}
