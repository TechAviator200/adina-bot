import { useState } from 'react'
import { useAgentLog } from '../../hooks/useAgentLog'
import type { RunEntry } from '../../context/AgentLogContext'

function RunCard({ run }: { run: RunEntry }) {
  const [expanded, setExpanded] = useState(run.status === 'running')

  const statusDot = run.status === 'running'
    ? 'bg-terracotta animate-pulse'
    : run.status === 'error'
      ? 'bg-red-400'
      : 'bg-green-500'

  return (
    <div className="bg-warm-cream/5 border border-warm-gray/10 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2 flex items-center gap-2 text-left"
      >
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${statusDot}`} />
        <span className="text-xs font-medium text-warm-cream flex-1 truncate">{run.title}</span>
        <span className="text-[10px] text-warm-gray">{expanded ? '▾' : '▸'}</span>
      </button>

      {expanded && run.steps.length > 0 && (
        <div className="px-3 pb-2 space-y-0.5">
          {run.steps.map((step, i) => (
            <p key={i} className="text-[11px] text-warm-gray pl-3 border-l border-warm-gray/20">
              {step.message}
            </p>
          ))}
        </div>
      )}

      {run.summary && (
        <div className={`px-3 py-1.5 text-[11px] font-medium border-t border-warm-gray/10 ${
          run.status === 'error' ? 'text-terracotta' : 'text-green-400'
        }`}>
          {run.summary}
        </div>
      )}

      <div className="px-3 pb-1.5">
        <span className="text-[10px] text-warm-gray">
          {run.timestamp.toLocaleTimeString()}
        </span>
      </div>
    </div>
  )
}

export default function AgentPanel() {
  const { entries, clearLogs } = useAgentLog()

  return (
    <aside className="w-80 bg-soft-navy border-l border-warm-gray/20 flex flex-col">
      <div className="p-4 flex items-center justify-between border-b border-warm-gray/20">
        <h2 className="text-warm-cream font-semibold text-sm">Agent</h2>
        {entries.length > 0 && (
          <button
            onClick={clearLogs}
            className="text-xs text-warm-gray hover:text-warm-cream transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {entries.length === 0 && (
          <p className="text-warm-gray text-xs text-center mt-8">
            Agent activity will appear here
          </p>
        )}
        {entries.map((entry, i) =>
          entry.type === 'run' ? (
            <RunCard key={`run-${entry.id}`} run={entry} />
          ) : (
            <div key={i} className="bg-warm-cream/5 border border-warm-gray/10 rounded-lg px-3 py-2 text-xs">
              <p className="text-warm-cream">{entry.message}</p>
              <span className="text-warm-gray text-[10px] mt-1 block">
                {entry.timestamp.toLocaleTimeString()}
              </span>
            </div>
          )
        )}
      </div>
    </aside>
  )
}
