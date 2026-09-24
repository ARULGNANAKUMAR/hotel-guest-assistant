import { useState, useCallback } from 'react'
import ChatHeader from './components/ChatHeader'
import MessageList from './components/MessageList'
import ChatInput from './components/ChatInput'
import { sendMessage } from './services/assistantApi'

let nextId = 1

function makeMessage(role, content, meta = {}) {
  return { id: nextId++, role, content, timestamp: new Date().toISOString(), ...meta }
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [context, setContext] = useState(null)

  const handleSend = useCallback(async (text) => {
    const userMsg = makeMessage('user', text)
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)

    try {
      const result = await sendMessage(text, context)

      if (result.context) {
        setContext(result.context)
      }

      // Pass type + data through so MessageBubble can render rich content
      const assistantMsg = makeMessage('assistant', result.message, {
        msgType: result.type,
        msgData: result.data,
      })
      setMessages((prev) => [...prev, assistantMsg])
    } catch (err) {
      const safe = err?.message?.length < 300 ? err.message
        : "Sorry, I'm having trouble connecting right now. Please try again."
      const errMsg = makeMessage('assistant', safe, { msgType: 'error' })
      setMessages((prev) => [...prev, errMsg])
    } finally {
      setLoading(false)
    }
  }, [context])

  const handleSuggestion = useCallback((question) => {
    handleSend(question)
  }, [handleSend])

  return (
    <div className="chat-shell">
      <ChatHeader />
      <MessageList messages={messages} onSuggestion={handleSuggestion} />
      {loading && (
        <div className="typing-indicator" aria-live="polite" aria-label="Assistant is typing">
          <span /><span /><span />
        </div>
      )}
      <ChatInput onSend={handleSend} disabled={loading} />
    </div>
  )
}
