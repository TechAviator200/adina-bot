import { createContext, useState, type ReactNode } from 'react'

interface LeadProfileContextValue {
  selectedLeadId: number | null
  setSelectedLeadId: (id: number | null) => void
}

export const LeadProfileContext = createContext<LeadProfileContextValue>({
  selectedLeadId: null,
  setSelectedLeadId: () => {},
})

export function LeadProfileProvider({ children }: { children: ReactNode }) {
  const [selectedLeadId, setSelectedLeadId] = useState<number | null>(null)

  return (
    <LeadProfileContext.Provider value={{ selectedLeadId, setSelectedLeadId }}>
      {children}
    </LeadProfileContext.Provider>
  )
}
