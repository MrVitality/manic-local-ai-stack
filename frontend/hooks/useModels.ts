'use client'

import { useEffect, useCallback } from 'react'
import { useChatStore } from '@/lib/store'
import { fetchModels } from '@/lib/api'

export function useModels() {
  const { 
    models, 
    selectedModel, 
    isLoadingModels,
    setModels, 
    setSelectedModel, 
    setIsLoadingModels,
    setError 
  } = useChatStore()

  const loadModels = useCallback(async () => {
    setIsLoadingModels(true)
    setError(null)
    
    try {
      const fetchedModels = await fetchModels()
      setModels(fetchedModels)
      
      // Set default model if not set or if current model not available
      if (fetchedModels.length > 0) {
        const modelExists = fetchedModels.some(m => m.name === selectedModel)
        if (!modelExists) {
          setSelectedModel(fetchedModels[0].name)
        }
      }
    } catch (error) {
      console.error('Failed to fetch models:', error)
      setError('Failed to connect to Ollama. Make sure it\'s running.')
    } finally {
      setIsLoadingModels(false)
    }
  }, [selectedModel, setModels, setSelectedModel, setIsLoadingModels, setError])

  useEffect(() => {
    loadModels()
  }, [loadModels])

  return {
    models,
    selectedModel,
    isLoadingModels,
    setSelectedModel,
    refreshModels: loadModels,
  }
}
