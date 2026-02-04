// Message types
export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: Date
  model?: string
  isStreaming?: boolean
  error?: string
}

// Conversation types
export interface Conversation {
  id: string
  title: string
  messages: Message[]
  model: string
  createdAt: Date
  updatedAt: Date
}

// Model types
export interface Model {
  name: string
  modified_at: string
  size: number
  digest: string
  details?: {
    family: string
    parameter_size: string
    quantization_level: string
  }
}

// API Response types
export interface ChatResponse {
  model: string
  created_at: string
  message: {
    role: string
    content: string
  }
  done: boolean
  total_duration?: number
  load_duration?: number
  prompt_eval_count?: number
  eval_count?: number
}

export interface ModelsResponse {
  models: Model[]
}

// Settings types
export interface Settings {
  defaultModel: string
  temperature: number
  maxTokens: number
  systemPrompt: string
  streamResponses: boolean
  apiUrl: string
  theme: 'dark' | 'light'
}

// RAG types
export interface Document {
  id: string
  title: string
  content: string
  metadata: Record<string, any>
  embedding?: number[]
  createdAt: Date
}

export interface SearchResult {
  id: string
  title: string
  content: string
  similarity: number
  metadata: Record<string, any>
}

// API Error
export interface ApiError {
  error: string
  message: string
  statusCode: number
}
