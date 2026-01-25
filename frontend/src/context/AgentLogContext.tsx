import { createContext, useState, useCallback, useRef, type ReactNode } from 'react'

export interface LogEntry {
  type: 'log'
  message: string
  timestamp: Date
}

export interface RunStep {
  message: string
  timestamp: Date
}

export interface RunEntry {
  type: 'run'
  id: number
  title: string
  steps: RunStep[]
  summary: string | null
  status: 'running' | 'done' | 'error'
  timestamp: Date
}

export type AgentEntry = LogEntry | RunEntry

export interface AgentLogContextValue {
  entries: AgentEntry[]
  addLog: (message: string) => void
  startRun: (title: string) => number
  logToRun: (runId: number, message: string) => void
  endRun: (runId: number, summary: string, status?: 'done' | 'error') => void
  clearLogs: () => void
}

export const AgentLogContext = createContext<AgentLogContextValue>({
  entries: [],
  addLog: () => {},
  startRun: () => 0,
  logToRun: () => {},
  endRun: () => {},
  clearLogs: () => {},
})

export function AgentLogProvider({ children }: { children: ReactNode }) {
  const [entries, setEntries] = useState<AgentEntry[]>([])
  const nextId = useRef(0)

  const addLog = useCallback((message: string) => {
    setEntries((prev) => [{ type: 'log', message, timestamp: new Date() }, ...prev])
  }, [])

  const startRun = useCallback((title: string) => {
    const id = nextId.current++
    const run: RunEntry = {
      type: 'run',
      id,
      title,
      steps: [],
      summary: null,
      status: 'running',
      timestamp: new Date(),
    }
    setEntries((prev) => [run, ...prev])
    return id
  }, [])

  const logToRun = useCallback((runId: number, message: string) => {
    setEntries((prev) =>
      prev.map((e) =>
        e.type === 'run' && e.id === runId
          ? { ...e, steps: [...e.steps, { message, timestamp: new Date() }] }
          : e
      )
    )
  }, [])

  const endRun = useCallback((runId: number, summary: string, status: 'done' | 'error' = 'done') => {
    setEntries((prev) =>
      prev.map((e) =>
        e.type === 'run' && e.id === runId
          ? { ...e, summary, status }
          : e
      )
    )
  }, [])

  const clearLogs = useCallback(() => {
    setEntries([])
  }, [])

  return (
    <AgentLogContext.Provider value={{ entries, addLog, startRun, logToRun, endRun, clearLogs }}>
      {children}
    </AgentLogContext.Provider>
  )
}
