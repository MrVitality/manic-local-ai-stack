'use client'

import { useState, useEffect } from 'react'
import { useChatStore } from '@/lib/store'
import { useModels } from '@/hooks/useModels'
import { formatModelSize, checkHealth } from '@/lib/api'
import type { Settings } from '@/types'

interface SettingsModalProps {
  isOpen: boolean
  onClose: () => void
}

export default function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const { settings, updateSettings } = useChatStore()
  const { models, refreshModels, isLoadingModels } = useModels()
  const [localSettings, setLocalSettings] = useState<Settings>(settings)
  const [activeTab, setActiveTab] = useState<'general' | 'models' | 'advanced'>('general')
  const [connectionStatus, setConnectionStatus] = useState<'checking' | 'connected' | 'disconnected'>('checking')

  // Sync local settings when modal opens
  useEffect(() => {
    if (isOpen) {
      setLocalSettings(settings)
      checkConnection()
    }
  }, [isOpen, settings])

  const checkConnection = async () => {
    setConnectionStatus('checking')
    const isHealthy = await checkHealth()
    setConnectionStatus(isHealthy ? 'connected' : 'disconnected')
  }

  const handleSave = () => {
    updateSettings(localSettings)
    onClose()
  }

  const handleReset = () => {
    setLocalSettings(settings)
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-gray-800 rounded-xl w-full max-w-2xl max-h-[90vh] overflow-hidden mx-4 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold">Settings</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-700 rounded"
          >
            <CloseIcon className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-700">
          {(['general', 'models', 'advanced'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`
                px-4 py-3 text-sm font-medium capitalize
                ${activeTab === tab 
                  ? 'text-blue-400 border-b-2 border-blue-400' 
                  : 'text-gray-400 hover:text-gray-200'}
              `}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {activeTab === 'general' && (
            <GeneralSettings
              settings={localSettings}
              onChange={setLocalSettings}
              connectionStatus={connectionStatus}
              onCheckConnection={checkConnection}
            />
          )}
          {activeTab === 'models' && (
            <ModelsSettings
              models={models}
              isLoading={isLoadingModels}
              onRefresh={refreshModels}
            />
          )}
          {activeTab === 'advanced' && (
            <AdvancedSettings
              settings={localSettings}
              onChange={setLocalSettings}
            />
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-gray-700">
          <button onClick={handleReset} className="btn-secondary">
            Reset
          </button>
          <button onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button onClick={handleSave} className="btn-primary">
            Save Changes
          </button>
        </div>
      </div>
    </div>
  )
}

// General Settings Tab
interface GeneralSettingsProps {
  settings: Settings
  onChange: (settings: Settings) => void
  connectionStatus: 'checking' | 'connected' | 'disconnected'
  onCheckConnection: () => void
}

function GeneralSettings({ settings, onChange, connectionStatus, onCheckConnection }: GeneralSettingsProps) {
  return (
    <div className="space-y-6">
      {/* Connection Status */}
      <div className="card p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-medium">Connection Status</h3>
            <p className="text-sm text-gray-400">Ollama API connection</p>
          </div>
          <div className="flex items-center gap-3">
            <div className={`
              flex items-center gap-2 px-3 py-1.5 rounded-full text-sm
              ${connectionStatus === 'connected' ? 'bg-green-900/50 text-green-400' :
                connectionStatus === 'disconnected' ? 'bg-red-900/50 text-red-400' :
                'bg-yellow-900/50 text-yellow-400'}
            `}>
              <div className={`w-2 h-2 rounded-full ${
                connectionStatus === 'connected' ? 'bg-green-400' :
                connectionStatus === 'disconnected' ? 'bg-red-400' :
                'bg-yellow-400 animate-pulse'
              }`} />
              {connectionStatus === 'checking' ? 'Checking...' :
               connectionStatus === 'connected' ? 'Connected' : 'Disconnected'}
            </div>
            <button onClick={onCheckConnection} className="btn-ghost text-sm">
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* API URL */}
      <div>
        <label className="block text-sm font-medium mb-2">API URL</label>
        <input
          type="text"
          value={settings.apiUrl}
          onChange={(e) => onChange({ ...settings, apiUrl: e.target.value })}
          className="input-base"
          placeholder="http://localhost:8080"
        />
        <p className="text-xs text-gray-500 mt-1">
          The URL of your Ollama API endpoint
        </p>
      </div>

      {/* Temperature */}
      <div>
        <label className="block text-sm font-medium mb-2">
          Temperature: {settings.temperature}
        </label>
        <input
          type="range"
          min="0"
          max="2"
          step="0.1"
          value={settings.temperature}
          onChange={(e) => onChange({ ...settings, temperature: parseFloat(e.target.value) })}
          className="w-full accent-blue-500"
        />
        <div className="flex justify-between text-xs text-gray-500 mt-1">
          <span>Precise (0)</span>
          <span>Balanced (0.7)</span>
          <span>Creative (2)</span>
        </div>
      </div>

      {/* Stream Responses */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium">Stream Responses</h3>
          <p className="text-sm text-gray-400">Show responses as they generate</p>
        </div>
        <ToggleSwitch
          enabled={settings.streamResponses}
          onChange={(enabled) => onChange({ ...settings, streamResponses: enabled })}
        />
      </div>
    </div>
  )
}

// Models Settings Tab
interface ModelsSettingsProps {
  models: Array<{ name: string; size: number; modified_at: string; details?: { parameter_size: string } }>
  isLoading: boolean
  onRefresh: () => void
}

function ModelsSettings({ models, isLoading, onRefresh }: ModelsSettingsProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-medium">Installed Models</h3>
        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="btn-secondary text-sm flex items-center gap-2"
        >
          <RefreshIcon className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {isLoading ? (
        <div className="text-center py-8 text-gray-400">
          Loading models...
        </div>
      ) : models.length === 0 ? (
        <div className="text-center py-8">
          <p className="text-gray-400 mb-4">No models installed</p>
          <p className="text-sm text-gray-500">
            Pull models using: <code className="bg-gray-900 px-2 py-1 rounded">ollama pull llama3.2</code>
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {models.map((model) => (
            <div key={model.name} className="card p-3 flex items-center justify-between">
              <div>
                <h4 className="font-medium">{model.name}</h4>
                <p className="text-sm text-gray-500">
                  {formatModelSize(model.size)}
                  {model.details?.parameter_size && ` • ${model.details.parameter_size}`}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Advanced Settings Tab
interface AdvancedSettingsProps {
  settings: Settings
  onChange: (settings: Settings) => void
}

function AdvancedSettings({ settings, onChange }: AdvancedSettingsProps) {
  return (
    <div className="space-y-6">
      {/* System Prompt */}
      <div>
        <label className="block text-sm font-medium mb-2">System Prompt</label>
        <textarea
          value={settings.systemPrompt}
          onChange={(e) => onChange({ ...settings, systemPrompt: e.target.value })}
          className="input-base h-32 resize-none"
          placeholder="You are a helpful AI assistant..."
        />
        <p className="text-xs text-gray-500 mt-1">
          This prompt is sent at the beginning of each conversation to set the AI&apos;s behavior
        </p>
      </div>

      {/* Max Tokens */}
      <div>
        <label className="block text-sm font-medium mb-2">
          Max Response Length: {settings.maxTokens} tokens
        </label>
        <input
          type="range"
          min="256"
          max="4096"
          step="256"
          value={settings.maxTokens}
          onChange={(e) => onChange({ ...settings, maxTokens: parseInt(e.target.value) })}
          className="w-full accent-blue-500"
        />
        <div className="flex justify-between text-xs text-gray-500 mt-1">
          <span>Short (256)</span>
          <span>Medium (2048)</span>
          <span>Long (4096)</span>
        </div>
      </div>

      {/* Default Model */}
      <div>
        <label className="block text-sm font-medium mb-2">Default Model</label>
        <input
          type="text"
          value={settings.defaultModel}
          onChange={(e) => onChange({ ...settings, defaultModel: e.target.value })}
          className="input-base"
          placeholder="llama3.2:3b"
        />
        <p className="text-xs text-gray-500 mt-1">
          The model to use for new conversations
        </p>
      </div>
    </div>
  )
}

// Toggle Switch Component
interface ToggleSwitchProps {
  enabled: boolean
  onChange: (enabled: boolean) => void
}

function ToggleSwitch({ enabled, onChange }: ToggleSwitchProps) {
  return (
    <button
      onClick={() => onChange(!enabled)}
      className={`
        relative inline-flex h-6 w-11 items-center rounded-full transition-colors
        ${enabled ? 'bg-blue-600' : 'bg-gray-600'}
      `}
    >
      <span
        className={`
          inline-block h-4 w-4 transform rounded-full bg-white transition-transform
          ${enabled ? 'translate-x-6' : 'translate-x-1'}
        `}
      />
    </button>
  )
}

// Icons
function CloseIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
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
