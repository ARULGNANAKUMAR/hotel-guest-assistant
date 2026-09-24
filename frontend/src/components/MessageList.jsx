import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'
import EmptyState from './EmptyState'

export default function MessageList({ messages, onSuggestion }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <main className="message-list" aria-live="polite" aria-label="Conversation">
      {messages.length === 0 ? (
        <EmptyState onSuggestion={onSuggestion} />
      ) : (
        <div className="message-list-inner">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
        </div>
      )}
      <div ref={bottomRef} />
    </main>
  )
}
