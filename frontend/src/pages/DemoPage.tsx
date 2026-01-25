import { Link } from 'react-router-dom'

const steps = [
  { label: 'Upload leads CSV', description: 'Import your prospect list from a .csv file', to: '/leads' },
  { label: 'Score top leads', description: 'Run the scoring engine to qualify leads', to: '/leads' },
  { label: 'View "Why ADINA chose this lead"', description: 'Click a score badge to see reasoning', to: '/leads' },
  { label: 'Draft outreach', description: 'Generate a personalized email for qualified leads', to: '/leads' },
  { label: 'Add contact email', description: 'Expand details and set a recipient address', to: '/leads' },
  { label: 'Approve', description: 'Mark the draft as ready to send', to: '/leads' },
  { label: 'Dry run send', description: 'Test the workflow without actually sending', to: '/leads' },
  { label: 'Paste inbound reply → get follow-up draft', description: 'Classify a reply and generate a response', to: '/inbox' },
]

export default function DemoPage() {
  return (
    <div className="max-w-lg">
      <h1 className="text-xl font-semibold text-warm-cream mb-1">Demo Walkthrough</h1>
      <p className="text-xs text-warm-gray mb-5">Follow these steps to explore ADINA end-to-end.</p>

      <ol className="space-y-3">
        {steps.map((step, i) => (
          <li key={i}>
            <Link
              to={step.to}
              className="flex items-start gap-3 bg-soft-navy/50 border border-warm-gray/10 rounded-lg px-4 py-3 hover:border-terracotta/40 transition-colors group"
            >
              <span className="w-5 h-5 rounded-full bg-terracotta/20 text-terracotta text-[11px] font-semibold flex items-center justify-center shrink-0 mt-0.5">
                {i + 1}
              </span>
              <div>
                <span className="text-sm font-medium text-warm-cream group-hover:text-terracotta transition-colors">
                  {step.label}
                </span>
                <p className="text-xs text-warm-gray mt-0.5">{step.description}</p>
              </div>
            </Link>
          </li>
        ))}
      </ol>
    </div>
  )
}
