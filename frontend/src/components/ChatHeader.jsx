export default function ChatHeader() {
  return (
    <header className="chat-header">
      <div className="chat-header-inner">
        <div className="chat-header-icon" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
            <polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
        </div>
        <div className="chat-header-text">
          <h1 className="chat-header-title">Hotel Guest Assistant</h1>
          <p className="chat-header-subtitle">How can we help with your stay?</p>
        </div>
        <div className="chat-header-status" aria-label="Assistant is online">
          <span className="status-dot" />
          <span className="status-label">Online</span>
        </div>
      </div>
    </header>
  )
}
