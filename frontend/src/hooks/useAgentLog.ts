import { useContext } from 'react'
import { AgentLogContext } from '../context/AgentLogContext'

export function useAgentLog() {
  return useContext(AgentLogContext)
}
