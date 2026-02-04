import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Conversation, Message, Model, Settings } from '@/types'

interface ChatState {
  // Conversations
  conversations: Conversation[]
  currentConversationId: string | null
  currentConversation: Conversation | null
  
  // Models
  models: Model[]
  selectedModel: string
  isLoadingModels: boolean
  
  // UI State
  isGenerating: boolean
  error: string | null
  
  // Settings
  settings: Settings
  
  // Actions - Conversations
  createConversation: () => string
  deleteConversation: (id: string) => void
  selectConversation: (id: string) => void
  updateConversationTitle: (id: string, title: string) => void
  clearConversations: () => void
  
  // Actions - Messages
  addMessage: (conversationId: string, message: Message) => void
  updateMessage: (conversationId: string, messageId: string, updates: Partial<Message>) => void
  deleteMessage: (conversationId: string, messageId: string) => void
  
  // Actions - Models
  setModels: (models: Model[]) => void
  setSelectedModel: (model: string) => void
  setIsLoadingModels: (loading: boolean) => void
  
  // Actions - UI
  setIsGenerating: (generating: boolean) => void
  setError: (error: string | null) => void
  
  // Actions - Settings
  updateSettings: (settings: Partial<Settings>) => void
}

const defaultSettings: Settings = {
  defaultModel: 'llama3.2:3b',
  temperature: 0.7,
  maxTokens: 2048,
  systemPrompt: 'You are a helpful AI assistant.',
  streamResponses: true,
  apiUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080',
  theme: 'dark',
}

const generateId = () => Math.random().toString(36).substring(2, 15)

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      // Initial state
      conversations: [],
      currentConversationId: null,
      currentConversation: null,
      models: [],
      selectedModel: defaultSettings.defaultModel,
      isLoadingModels: false,
      isGenerating: false,
      error: null,
      settings: defaultSettings,
      
      // Conversation actions
      createConversation: () => {
        const id = generateId()
        const newConversation: Conversation = {
          id,
          title: 'New Chat',
          messages: [],
          model: get().selectedModel,
          createdAt: new Date(),
          updatedAt: new Date(),
        }
        
        set((state) => ({
          conversations: [newConversation, ...state.conversations],
          currentConversationId: id,
          currentConversation: newConversation,
        }))
        
        return id
      },
      
      deleteConversation: (id: string) => {
        set((state) => {
          const filtered = state.conversations.filter((c) => c.id !== id)
          const isCurrentDeleted = state.currentConversationId === id
          
          return {
            conversations: filtered,
            currentConversationId: isCurrentDeleted 
              ? (filtered[0]?.id || null) 
              : state.currentConversationId,
            currentConversation: isCurrentDeleted 
              ? (filtered[0] || null) 
              : state.currentConversation,
          }
        })
      },
      
      selectConversation: (id: string) => {
        set((state) => ({
          currentConversationId: id,
          currentConversation: state.conversations.find((c) => c.id === id) || null,
        }))
      },
      
      updateConversationTitle: (id: string, title: string) => {
        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === id ? { ...c, title, updatedAt: new Date() } : c
          ),
          currentConversation: state.currentConversation?.id === id
            ? { ...state.currentConversation, title, updatedAt: new Date() }
            : state.currentConversation,
        }))
      },
      
      clearConversations: () => {
        set({
          conversations: [],
          currentConversationId: null,
          currentConversation: null,
        })
      },
      
      // Message actions
      addMessage: (conversationId: string, message: Message) => {
        set((state) => {
          const conversations = state.conversations.map((c) => {
            if (c.id === conversationId) {
              const updatedConv = {
                ...c,
                messages: [...c.messages, message],
                updatedAt: new Date(),
              }
              // Auto-title based on first user message
              if (c.messages.length === 0 && message.role === 'user') {
                updatedConv.title = message.content.slice(0, 50) + (message.content.length > 50 ? '...' : '')
              }
              return updatedConv
            }
            return c
          })
          
          return {
            conversations,
            currentConversation: conversations.find((c) => c.id === conversationId) || null,
          }
        })
      },
      
      updateMessage: (conversationId: string, messageId: string, updates: Partial<Message>) => {
        set((state) => {
          const conversations = state.conversations.map((c) => {
            if (c.id === conversationId) {
              return {
                ...c,
                messages: c.messages.map((m) =>
                  m.id === messageId ? { ...m, ...updates } : m
                ),
                updatedAt: new Date(),
              }
            }
            return c
          })
          
          return {
            conversations,
            currentConversation: conversations.find((c) => c.id === conversationId) || null,
          }
        })
      },
      
      deleteMessage: (conversationId: string, messageId: string) => {
        set((state) => {
          const conversations = state.conversations.map((c) => {
            if (c.id === conversationId) {
              return {
                ...c,
                messages: c.messages.filter((m) => m.id !== messageId),
                updatedAt: new Date(),
              }
            }
            return c
          })
          
          return {
            conversations,
            currentConversation: conversations.find((c) => c.id === conversationId) || null,
          }
        })
      },
      
      // Model actions
      setModels: (models: Model[]) => set({ models }),
      setSelectedModel: (model: string) => set({ selectedModel: model }),
      setIsLoadingModels: (loading: boolean) => set({ isLoadingModels: loading }),
      
      // UI actions
      setIsGenerating: (generating: boolean) => set({ isGenerating: generating }),
      setError: (error: string | null) => set({ error }),
      
      // Settings actions
      updateSettings: (newSettings: Partial<Settings>) => {
        set((state) => ({
          settings: { ...state.settings, ...newSettings },
        }))
      },
    }),
    {
      name: 'ai-chat-storage',
      partialize: (state) => ({
        conversations: state.conversations,
        currentConversationId: state.currentConversationId,
        selectedModel: state.selectedModel,
        settings: state.settings,
      }),
    }
  )
)

// Initialize current conversation from persisted state
if (typeof window !== 'undefined') {
  const state = useChatStore.getState()
  if (state.currentConversationId) {
    const conversation = state.conversations.find(
      (c) => c.id === state.currentConversationId
    )
    if (conversation) {
      useChatStore.setState({ currentConversation: conversation })
    }
  }
}
