'use client'

import { useCallback, useRef } from 'react'
import { useChatStore } from '@/lib/store'
import { streamChat, generateMessageId } from '@/lib/api'
import type { Message } from '@/types'

export function useChat() {
  const {
    currentConversation,
    currentConversationId,
    selectedModel,
    isGenerating,
    settings,
    createConversation,
    addMessage,
    updateMessage,
    setIsGenerating,
    setError,
  } = useChatStore()

  const abortControllerRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isGenerating) return

    // Ensure we have a conversation
    let conversationId = currentConversationId
    if (!conversationId) {
      conversationId = createConversation()
    }

    // Add user message
    const userMessage: Message = {
      id: generateMessageId(),
      role: 'user',
      content: content.trim(),
      timestamp: new Date(),
    }
    addMessage(conversationId, userMessage)

    // Create assistant message placeholder
    const assistantMessageId = generateMessageId()
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      model: selectedModel,
      isStreaming: true,
    }
    addMessage(conversationId, assistantMessage)

    setIsGenerating(true)
    setError(null)

    try {
      // Get current conversation messages for context
      const state = useChatStore.getState()
      const conversation = state.conversations.find(c => c.id === conversationId)
      const messages = conversation?.messages
        .filter(m => m.role !== 'system' && m.id !== assistantMessageId)
        .map(m => ({ role: m.role, content: m.content })) || []

      // Stream the response
      let fullContent = ''
      
      for await (const chunk of streamChat({
        model: selectedModel,
        messages,
        temperature: settings.temperature,
        systemPrompt: settings.systemPrompt,
        stream: settings.streamResponses,
      })) {
        fullContent += chunk
        updateMessage(conversationId, assistantMessageId, {
          content: fullContent,
        })
      }

      // Mark as complete
      updateMessage(conversationId, assistantMessageId, {
        content: fullContent,
        isStreaming: false,
      })
    } catch (error) {
      console.error('Chat error:', error)
      const errorMessage = error instanceof Error ? error.message : 'An error occurred'
      updateMessage(conversationId, assistantMessageId, {
        content: '',
        isStreaming: false,
        error: errorMessage,
      })
      setError(errorMessage)
    } finally {
      setIsGenerating(false)
    }
  }, [
    currentConversationId,
    selectedModel,
    isGenerating,
    settings,
    createConversation,
    addMessage,
    updateMessage,
    setIsGenerating,
    setError,
  ])

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsGenerating(false)
  }, [setIsGenerating])

  const regenerateLastMessage = useCallback(async () => {
    if (!currentConversation || currentConversation.messages.length < 2) return

    const messages = currentConversation.messages
    const lastUserMessageIndex = messages.findLastIndex(m => m.role === 'user')
    
    if (lastUserMessageIndex === -1) return

    const lastUserMessage = messages[lastUserMessageIndex]
    
    // Remove the last assistant message if it exists
    const lastAssistantMessage = messages[messages.length - 1]
    if (lastAssistantMessage.role === 'assistant') {
      useChatStore.getState().deleteMessage(currentConversation.id, lastAssistantMessage.id)
    }

    // Resend the last user message
    await sendMessage(lastUserMessage.content)
  }, [currentConversation, sendMessage])

  return {
    sendMessage,
    stopGeneration,
    regenerateLastMessage,
    isGenerating,
    currentConversation,
  }
}
