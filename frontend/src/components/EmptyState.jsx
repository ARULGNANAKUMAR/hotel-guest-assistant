const SUGGESTIONS = [
  { label: 'Check-in time',       question: 'What time is check-in?' },
  { label: 'Breakfast',           question: 'Is breakfast available?' },
  { label: 'Pool',                question: 'Do you have a pool?' },
  { label: 'Room availability',   question: 'I need a room for 2 adults.' },
]

export default function EmptyState({ onSuggestion }) {
  return (
    <div className="empty-state" role="region" aria-label="Welcome">
      <div className="empty-state-icon" aria-hidden="true">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
          <polyline points="9 22 9 12 15 12 15 22"/>
        </svg>
      </div>
      <h2 className="empty-state-title">Welcome to our hotel</h2>
      <p className="empty-state-body">
        Ask me about rooms, amenities, policies, or availability.
      </p>
      <nav aria-label="Quick questions">
        <div className="suggestion-chips">
          {SUGGESTIONS.map((s) => (
            <button
              key={s.label}
              className="suggestion-chip"
              onClick={() => onSuggestion(s.question)}
              type="button"
            >
              {s.label}
            </button>
          ))}
        </div>
      </nav>
    </div>
  )
}
