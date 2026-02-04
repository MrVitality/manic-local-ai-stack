// =============================================================================
// API Utilities for Ollama and Backend Services
// =============================================================================

import type { Model, Message, ModelsResponse } from '@/types'

const getApiUrl = () => {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'
}

// =============================================================================
// Ollama API
// =============================================================================

export async function fetchModels(): Promise<Model[]> {
  const response = await fetch(`${getApiUrl()}/api/tags`)
  if (!response.ok) {
    throw new Error(`Failed to fetch models: ${response.statusText}`)
  }
  const data: ModelsResponse = await response.json()
  return data.models || []
}

export async function pullModel(modelName: string): Promise<ReadableStream<Uint8Array> | null> {
  const response = await fetch(`${getApiUrl()}/api/pull`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: modelName }),
  })
  return response.body
}

export async function deleteModel(modelName: string): Promise<void> {
  const response = await fetch(`${getApiUrl()}/api/delete`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: modelName }),
  })
  if (!response.ok) {
    throw new Error(`Failed to delete model: ${response.statusText}`)
  }
}

// =============================================================================
// Chat API - Streaming
// =============================================================================

export interface ChatOptions {
  model: string
  messages: Array<{ role: string; content: string }>
  temperature?: number
  maxTokens?: number
  systemPrompt?: string
  stream?: boolean
}

export async function* streamChat(options: ChatOptions): AsyncGenerator<string, void, unknown> {
  const { model, messages, temperature = 0.7, systemPrompt, stream = true } = options

  // Prepare messages with system prompt
  const allMessages = systemPrompt
    ? [{ role: 'system', content: systemPrompt }, ...messages]
    : messages

  const response = await fetch(`${getApiUrl()}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model,
      messages: allMessages,
      stream,
      options: {
        temperature,
      },
    }),
  })

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.statusText}`)
  }

  if (!stream) {
    const data = await response.json()
    yield data.message?.content || ''
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('No response body')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.trim()) {
          try {
            const data = JSON.parse(line)
            if (data.message?.content) {
              yield data.message.content
            }
            if (data.done) {
              return
            }
          } catch {
            // Skip invalid JSON lines
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

// =============================================================================
// Non-streaming Chat
// =============================================================================

export async function chat(options: ChatOptions): Promise<string> {
  let result = ''
  for await (const chunk of streamChat({ ...options, stream: false })) {
    result += chunk
  }
  return result
}

// =============================================================================
// Generate Embeddings
// =============================================================================

export async function generateEmbedding(text: string, model: string = 'nomic-embed-text'): Promise<number[]> {
  const response = await fetch(`${getApiUrl()}/api/embeddings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, prompt: text }),
  })

  if (!response.ok) {
    throw new Error(`Failed to generate embedding: ${response.statusText}`)
  }

  const data = await response.json()
  return data.embedding
}

// =============================================================================
// Health Check
// =============================================================================

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${getApiUrl()}/api/tags`, {
      method: 'GET',
      signal: AbortSignal.timeout(5000),
    })
    return response.ok
  } catch {
    return false
  }
}

// =============================================================================
// Format Helpers
// =============================================================================

export function formatModelSize(bytes: number): string {
  const gb = bytes / (1024 * 1024 * 1024)
  if (gb >= 1) {
    return `${gb.toFixed(1)} GB`
  }
  const mb = bytes / (1024 * 1024)
  return `${mb.toFixed(0)} MB`
}

export function formatDate(date: Date | string): string {
  const d = new Date(date)
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function generateMessageId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`
}
