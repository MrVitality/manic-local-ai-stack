'use client'

import { useRef, useEffect } from 'react'
import { useChatStore } from '@/lib/store'
import { useChat } from '@/hooks/useChat'
import MessageList from './MessageList'
import MessageInput from './MessageInput'

export default function ChatArea() {
  const { currentConversation, error } = useChatStore()
  const { sendMessage, stopGeneration, regenerateLastMessage, isGenerating } = useChat()
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [currentConversation?.messages])

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto">
        {!currentConversation || currentConversation.messages.length === 0 ? (
          <EmptyState />
        ) : (
          <MessageList 
            messages={currentConversation.messages} 
            onRegenerate={regenerateLastMessage}
          />
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mx-4 mb-2 p-3 bg-red-900/50 border border-red-700 rounded-lg text-red-200 text-sm flex items-center gap-2">
          <ErrorIcon className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
          <button 
            onClick={() => useChatStore.getState().setError(null)}
            className="ml-auto hover:text-white"
          >
            <CloseIcon className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Input Area */}
      <div className="border-t border-gray-700 p-4">
        <MessageInput
          onSend={sendMessage}
          onStop={stopGeneration}
          isGenerating={isGenerating}
        />
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
      <div className="w-16 h-16 mb-6 rounded-full bg-blue-600/20 flex items-center justify-center">
        <BotIcon className="w-8 h-8 text-blue-400" />
      </div>
      <h2 className="text-xl font-semibold mb-2">How can I help you today?</h2>
      <p className="text-gray-400 max-w-md mb-8">
        Start a conversation with your local AI assistant. Ask questions, get help with coding, 
        creative writing, analysis, and more.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-lg w-full">
        <SuggestionCard
          icon="💡"
          title="Explain a concept"
          description="Break down complex topics"
        />
        <SuggestionCard
          icon="💻"
          title="Help with code"
          description="Debug or write code"
        />
        <SuggestionCard
          icon="✍️"
          title="Write content"
          description="Draft emails, articles, etc."
        />
        <SuggestionCard
          icon="📊"
          title="Analyze data"
          description="Get insights from data"
        />
      </div>
    </div>
  )
}

interface SuggestionCardProps {
  icon: string
  title: string
  description: string
}

function SuggestionCard({ icon, title, description }: SuggestionCardProps) {
  return (
    <div className="p-4 bg-gray-800 rounded-lg border border-gray-700 hover:border-gray-600 cursor-pointer transition-colors">
      <span className="text-2xl mb-2 block">{icon}</span>
      <h3 className="font-medium text-sm">{title}</h3>
      <p className="text-xs text-gray-500">{description}</p>
    </div>
  )
}

// Icons
function BotIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  )
}

function ErrorIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  )
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
    </svg>
  )
}
