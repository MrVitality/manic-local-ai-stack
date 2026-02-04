'use client'

import { useState, useRef, useEffect, KeyboardEvent } from 'react'

interface MessageInputProps {
  onSend: (message: string) => void
  onStop: () => void
  isGenerating: boolean
  placeholder?: string
}

export default function MessageInput({
  onSend,
  onStop,
  isGenerating,
  placeholder = 'Type a message...',
}: MessageInputProps) {
  const [message, setMessage] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }
  }, [message])

  // Focus on mount
  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  const handleSubmit = () => {
    if (message.trim() && !isGenerating) {
      onSend(message)
      setMessage('')
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="relative max-w-3xl mx-auto">
      <div className="relative flex items-end gap-2 bg-gray-800 rounded-xl border border-gray-700 focus-within:border-blue-500 transition-colors">
        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={isGenerating}
          rows={1}
          className="flex-1 px-4 py-3 bg-transparent resize-none focus:outline-none placeholder-gray-500 disabled:opacity-50"
          style={{ maxHeight: '200px' }}
        />

        {/* Actions */}
        <div className="flex items-center gap-1 p-2">
          {isGenerating ? (
            <button
              onClick={onStop}
              className="p-2 bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
              title="Stop generating"
            >
              <StopIcon className="w-5 h-5" />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={!message.trim()}
              className="p-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Send message (Enter)"
            >
              <SendIcon className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>

      {/* Helper text */}
      <div className="mt-2 text-xs text-gray-500 text-center">
        Press <kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-gray-400">Enter</kbd> to send, 
        <kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-gray-400 ml-1">Shift + Enter</kbd> for new line
      </div>
    </div>
  )
}

// Icons
function SendIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
    </svg>
  )
}

function StopIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="currentColor" viewBox="0 0 24 24">
      <rect x="6" y="6" width="12" height="12" rx="1" />
    </svg>
  )
}
