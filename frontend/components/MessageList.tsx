'use client'

import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism'
import type { Message } from '@/types'

interface MessageListProps {
  messages: Message[]
  onRegenerate?: () => void
}

export default function MessageList({ messages, onRegenerate }: MessageListProps) {
  return (
    <div className="py-4">
      {messages.map((message, index) => (
        <MessageItem
          key={message.id}
          message={message}
          isLast={index === messages.length - 1}
          onRegenerate={message.role === 'assistant' && index === messages.length - 1 ? onRegenerate : undefined}
        />
      ))}
    </div>
  )
}

interface MessageItemProps {
  message: Message
  isLast: boolean
  onRegenerate?: () => void
}

function MessageItem({ message, isLast, onRegenerate }: MessageItemProps) {
  const [copied, setCopied] = useState(false)
  const isUser = message.role === 'user'
  const isAssistant = message.role === 'assistant'

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div
      className={`
        px-4 py-6 animate-fade-in
        ${isUser ? 'bg-gray-800/50' : 'bg-gray-900'}
      `}
    >
      <div className="max-w-3xl mx-auto flex gap-4">
        {/* Avatar */}
        <div className={`
          w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0
          ${isUser ? 'bg-blue-600' : 'bg-green-600'}
        `}>
          {isUser ? (
            <UserIcon className="w-5 h-5 text-white" />
          ) : (
            <BotIcon className="w-5 h-5 text-white" />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-center gap-2 mb-1">
            <span className="font-medium text-sm">
              {isUser ? 'You' : 'Assistant'}
            </span>
            {message.model && (
              <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
                {message.model}
              </span>
            )}
          </div>

          {/* Message Content */}
          {message.error ? (
            <div className="text-red-400 text-sm">
              Error: {message.error}
            </div>
          ) : message.isStreaming && !message.content ? (
            <div className="flex items-center gap-2 text-gray-400">
              <LoadingDots />
              <span className="text-sm">Thinking...</span>
            </div>
          ) : (
            <div className="prose-chat">
              <ReactMarkdown
                components={{
                  code({ node, className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '')
                    const isInline = !match && !String(children).includes('\n')
                    
                    if (isInline) {
                      return (
                        <code className="bg-gray-800 px-1.5 py-0.5 rounded text-sm" {...props}>
                          {children}
                        </code>
                      )
                    }
                    
                    return (
                      <div className="relative group">
                        <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <CopyButton text={String(children).replace(/\n$/, '')} />
                        </div>
                        <SyntaxHighlighter
                          style={oneDark}
                          language={match?.[1] || 'text'}
                          PreTag="div"
                          customStyle={{
                            margin: 0,
                            borderRadius: '0.5rem',
                            fontSize: '0.875rem',
                          }}
                        >
                          {String(children).replace(/\n$/, '')}
                        </SyntaxHighlighter>
                      </div>
                    )
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
              {message.isStreaming && (
                <span className="typing-cursor">▌</span>
              )}
            </div>
          )}

          {/* Actions */}
          {isAssistant && !message.isStreaming && message.content && (
            <div className="flex items-center gap-2 mt-3">
              <button
                onClick={handleCopy}
                className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1"
              >
                {copied ? (
                  <>
                    <CheckIcon className="w-4 h-4" />
                    Copied!
                  </>
                ) : (
                  <>
                    <CopyIcon className="w-4 h-4" />
                    Copy
                  </>
                )}
              </button>
              {onRegenerate && (
                <button
                  onClick={onRegenerate}
                  className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1"
                >
                  <RefreshIcon className="w-4 h-4" />
                  Regenerate
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <button
      onClick={handleCopy}
      className="p-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs"
    >
      {copied ? 'Copied!' : 'Copy'}
    </button>
  )
}

function LoadingDots() {
  return (
    <div className="flex gap-1">
      <div className="w-2 h-2 bg-gray-500 rounded-full animate-pulse-slow" style={{ animationDelay: '0ms' }} />
      <div className="w-2 h-2 bg-gray-500 rounded-full animate-pulse-slow" style={{ animationDelay: '150ms' }} />
      <div className="w-2 h-2 bg-gray-500 rounded-full animate-pulse-slow" style={{ animationDelay: '300ms' }} />
    </div>
  )
}

// Icons
function UserIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
    </svg>
  )
}

function BotIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  )
}

function CopyIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
    </svg>
  )
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
    </svg>
  )
}

function RefreshIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  )
}
