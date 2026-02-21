import { createContext, useState, useCallback, type ReactNode } from 'react'

interface LeadProfileContextValue {
  selectedLeadId: number | null
  setSelectedLeadId: (id: number | null) => void
  refreshKey: number
  refreshProfile: () => void
}

export const LeadProfileContext = createContext<LeadProfileContextValue>({
  selectedLeadId: null,
  setSelectedLeadId: () => {},
  refreshKey: 0,
  refreshProfile: () => {},
})

export function LeadProfileProvider({ children }: { children: ReactNode }) {
  const [selectedLeadId, setSelectedLeadId] = useState<number | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const refreshProfile = useCallback(() => {
    setRefreshKey((k) => k + 1)
  }, [])

  return (
    <LeadProfileContext.Provider value={{ selectedLeadId, setSelectedLeadId, refreshKey, refreshProfile }}>
      {children}
    </LeadProfileContext.Provider>
  )
}
