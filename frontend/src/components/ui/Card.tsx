import type { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
}

export default function Card({ children, className = '' }: CardProps) {
  return (
    <div className={`bg-warm-cream text-deep-charcoal rounded-lg p-4 shadow ${className}`}>
      {children}
    </div>
  )
}
