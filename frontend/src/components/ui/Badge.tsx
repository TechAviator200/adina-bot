const statusColors: Record<string, string> = {
  new: 'bg-warm-gray/20 text-warm-gray',
  qualified: 'bg-soft-navy text-warm-cream',
  drafted: 'bg-terracotta/20 text-terracotta',
  approved: 'bg-terracotta text-warm-cream',
  sent: 'bg-green-700 text-warm-cream',
}

interface BadgeProps {
  status: string
  className?: string
}

export default function Badge({ status, className = '' }: BadgeProps) {
  const color = statusColors[status] || 'bg-warm-gray/20 text-warm-gray'
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${color} ${className}`}>
      {status}
    </span>
  )
}
