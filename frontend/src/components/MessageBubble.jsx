import AvailabilityCard from './AvailabilityCard'

/**
 * Renders one message. For availability_result messages the structured
 * card is shown below the assistant's prose text.
 */
export default function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  const isError = message.msgType === 'error'
  const showCard = !isUser && message.msgType === 'availability_result' && message.msgData

  // For availability_result the prose text is redundant with the card summary —
  // we still show it because it adds a natural conversational intro.
  const bubbleClass = [
    'message-bubble',
    isUser ? 'message-bubble--user' : 'message-bubble--assistant',
    isError ? 'message-bubble--error' : '',
  ].filter(Boolean).join(' ')

  return (
    <div className={`message-row ${isUser ? 'message-row--user' : 'message-row--assistant'}`}>
      {!isUser && (
        <div className="message-avatar" aria-hidden="true">A</div>
      )}

      <div className="message-bubble-wrap">
        <div className={bubbleClass}>
          {/* Preserve newlines in assistant messages (e.g. room lists) */}
          <p className="message-text" style={{ whiteSpace: 'pre-line' }}>{message.content}</p>
          <time className="message-time" dateTime={message.timestamp}>
            {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </time>
        </div>

        {showCard && <AvailabilityCard data={message.msgData} />}
      </div>

      {isUser && (
        <div className="message-avatar message-avatar--user" aria-hidden="true">You</div>
      )}
    </div>
  )
}
