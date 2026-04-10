/** Top toolbar — File menu, transport controls (Play/Pause/Stop), templates, stats */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useReactFlow } from '@xyflow/react'
import { useGraphStore } from '../hooks/useGraphStore'
import {
  useCreatePipeline,
  useUpdatePipeline,
  useDeletePipeline,
  usePipelines,
  useValidateGraph,
} from '../hooks/usePipelineApi'
import { executeInline } from '../api/client'
import type { PipelineData, NodeTypeRegistry } from '../api/client'
import { STATIC_TEMPLATES, type Template } from '../utils/templates'
import { validateGraph as validateGraphLocal } from '../utils/validation'
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts'

type TransportState = 'stopped' | 'playing' | 'paused' | 'loading'

interface ToolbarProps {
  registry: NodeTypeRegistry | undefined
}

export default function Toolbar({ registry }: ToolbarProps) {
  const {
    pipelineId, pipelineName, nodes, edges, isDirty,
    setPipeline, setDirty, canUndo, canRedo, undo, redo, clear,
  } = useGraphStore()

  const [name, setName] = useState(pipelineName)
  const [showFileMenu, setShowFileMenu] = useState(false)
  const [showOpenDialog, setShowOpenDialog] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const [validationMsg, setValidationMsg] = useState<string | null>(null)
  const fileMenuRef = useRef<HTMLDivElement>(null)
  const templateRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Transport state
  const [transport, setTransport] = useState<TransportState>('stopped')
  const [nowPlaying, setNowPlaying] = useState<string | null>(null)
  const [iterationCount, setIterationCount] = useState(0)
  const [lastError, setLastError] = useState<string | null>(null)
  const stopRequestedRef = useRef(false)
  const currentAudioRef = useRef<HTMLAudioElement | null>(null)

  const reactFlow = useReactFlow()

  const createMutation = useCreatePipeline()
  const updateMutation = useUpdatePipeline()
  const deleteMutation = useDeletePipeline()
  const validateMutation = useValidateGraph()
  const { data: savedPipelines, refetch: refetchPipelines } = usePipelines(false)
  const { data: backendTemplates } = usePipelines(true)
  const templates = backendTemplates && backendTemplates.length > 0 ? backendTemplates : STATIC_TEMPLATES

  // Sync name when pipeline changes
  useEffect(() => { setName(pipelineName) }, [pipelineName])

  // Close dropdowns on outside click
  useEffect(() => {
    if (!showFileMenu && !showTemplates) return
    const handler = (e: MouseEvent) => {
      if (showFileMenu && fileMenuRef.current && !fileMenuRef.current.contains(e.target as Node)) {
        setShowFileMenu(false)
      }
      if (showTemplates && templateRef.current && !templateRef.current.contains(e.target as Node)) {
        setShowTemplates(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showFileMenu, showTemplates])

  // Auto-clear validation messages
  useEffect(() => {
    if (!validationMsg) return
    const t = setTimeout(() => setValidationMsg(null), 4000)
    return () => clearTimeout(t)
  }, [validationMsg])

  // Serialize graph for API — reads fresh from store each call
  const buildGraphJson = useCallback(() => {
    const { nodes: currentNodes, edges: currentEdges } = useGraphStore.getState()
    return {
      nodes: currentNodes.map((n) => {
        const { nodeDef, ...rest } = n.data as Record<string, unknown>
        return {
          id: n.id,
          type: (n.data as Record<string, unknown>).type_id || n.type,
          position: n.position,
          data: rest,
        }
      }),
      edges: currentEdges.map((e) => ({
        id: e.id,
        source: e.source,
        sourceHandle: e.sourceHandle,
        target: e.target,
        targetHandle: e.targetHandle,
        data: e.data || { edge_type: 'normal' },
      })),
      viewport: { x: 0, y: 0, zoom: 1 },
    }
  }, [])

  const handleSave = useCallback(async () => {
    const graphJson = buildGraphJson()
    try {
      if (pipelineId) {
        await updateMutation.mutateAsync({ id: pipelineId, name, graph_json: graphJson })
      } else {
        const result = await createMutation.mutateAsync({ name, graph_json: graphJson })
        setPipeline(result.id, result.name, nodes, edges)
      }
      setDirty(false)
      setValidationMsg('Saved!')
    } catch (e) {
      setValidationMsg(`Save failed: ${e instanceof Error ? e.message : 'unknown'}`)
    }
  }, [pipelineId, name, nodes, edges, buildGraphJson, createMutation, updateMutation, setPipeline, setDirty])

  const handleSaveAs = useCallback(async () => {
    const newName = prompt('Save as:', name)
    if (!newName) return
    const graphJson = buildGraphJson()
    try {
      const result = await createMutation.mutateAsync({ name: newName, graph_json: graphJson })
      setPipeline(result.id, result.name, nodes, edges)
      setName(result.name)
      setDirty(false)
      setValidationMsg('Saved as new pipeline!')
    } catch (e) {
      setValidationMsg(`Save failed: ${e instanceof Error ? e.message : 'unknown'}`)
    }
  }, [name, nodes, edges, buildGraphJson, createMutation, setPipeline, setDirty])

  useKeyboardShortcuts(handleSave)

  // ---- Transport controls ----

  const playOneIteration = useCallback(async (): Promise<boolean> => {
    // Build graph from CURRENT store state (picks up real-time config changes)
    const graphJson = buildGraphJson()
    setTransport('loading')

    try {
      const result = await executeInline(graphJson) as Record<string, any>

      if (stopRequestedRef.current) return false

      if (!result.success) {
        setLastError(result.error || 'Execution failed')
        return false
      }

      setLastError(null)
      setNowPlaying(result.source_text || null)
      setIterationCount((c) => c + 1)

      // Push text results to output log for text_output sidebar
      // Prefer text_output_text (what actually arrived at the Text Output node)
      const textOut = result.text_output_text || result.transcription_text || result.llm_response_text || result.source_text
      if (textOut) {
        useGraphStore.getState().appendOutputLog(textOut)
      }

      if (result.audio_wav_base64) {
        setTransport('playing')
        return new Promise<boolean>((resolve) => {
          // Use blob URL instead of data URL for better browser compatibility
          const byteChars = atob(result.audio_wav_base64)
          const byteArray = new Uint8Array(byteChars.length)
          for (let i = 0; i < byteChars.length; i++) {
            byteArray[i] = byteChars.charCodeAt(i)
          }
          const blob = new Blob([byteArray], { type: 'audio/wav' })
          const url = URL.createObjectURL(blob)
          const audio = new Audio(url)
          currentAudioRef.current = audio
          audio.onended = () => {
            currentAudioRef.current = null
            URL.revokeObjectURL(url)
            resolve(!stopRequestedRef.current)
          }
          audio.onerror = (e) => {
            console.error('Audio playback error:', e)
            currentAudioRef.current = null
            URL.revokeObjectURL(url)
            resolve(!stopRequestedRef.current)
          }
          audio.play().catch((err) => {
            console.error('Audio play() rejected:', err)
            currentAudioRef.current = null
            URL.revokeObjectURL(url)
            resolve(!stopRequestedRef.current)
          })
        })
      }

      // No audio output — still continue loop
      setTransport('playing')
      return !stopRequestedRef.current
    } catch (e) {
      setLastError(e instanceof Error ? e.message : 'Unknown error')
      return false
    }
  }, [buildGraphJson])

  const handlePlay = useCallback(async () => {
    stopRequestedRef.current = false
    setLastError(null)
    setIterationCount(0)
    useGraphStore.getState().clearOutputLog()
    setTransport('loading')

    // Continuous playback loop
    let shouldContinue = true
    while (shouldContinue && !stopRequestedRef.current) {
      shouldContinue = await playOneIteration()
    }

    // Loop ended
    if (currentAudioRef.current) {
      currentAudioRef.current.pause()
      currentAudioRef.current = null
    }
    setTransport('stopped')
    setNowPlaying(null)
  }, [playOneIteration])

  const handlePause = useCallback(() => {
    if (currentAudioRef.current) {
      if (transport === 'paused') {
        currentAudioRef.current.play()
        setTransport('playing')
      } else {
        currentAudioRef.current.pause()
        setTransport('paused')
      }
    }
  }, [transport])

  const handleStop = useCallback(() => {
    stopRequestedRef.current = true
    if (currentAudioRef.current) {
      currentAudioRef.current.pause()
      currentAudioRef.current = null
    }
    setTransport('stopped')
    setNowPlaying(null)
    setIterationCount(0)
    setLastError(null)
  }, [])

  // ---- File operations ----

  const handleNew = () => {
    if (transport !== 'stopped') handleStop()
    if (isDirty && !confirm('Discard unsaved changes?')) return
    clear()
    setName('Untitled Pipeline')
    setShowFileMenu(false)
  }

  const handleOpen = () => {
    if (transport !== 'stopped') handleStop()
    refetchPipelines()
    setShowOpenDialog(true)
    setShowFileMenu(false)
  }

  const loadPipeline = (pipeline: PipelineData) => {
    if (transport !== 'stopped') handleStop()
    if (isDirty && !confirm('Discard unsaved changes?')) return
    const graph = pipeline.graph_json as { nodes?: unknown[]; edges?: unknown[] }
    const loadedNodes = (graph.nodes || []).map((n: any) => {
      const typeId = n.type || n.data?.type_id || ''
      const nodeDef = registry?.node_types[typeId]
      return { ...n, data: { ...n.data, nodeDef } }
    })
    const loadedEdges = (graph.edges || []).map((e: any) => ({
      ...e,
      id: e.id || `e_${Math.random().toString(36).slice(2, 8)}`,
    }))
    setPipeline(pipeline.id, pipeline.name, loadedNodes, loadedEdges)
    setName(pipeline.name)
    setShowOpenDialog(false)
    setTimeout(() => reactFlow.fitView({ padding: 0.15, duration: 300 }), 50)
    setValidationMsg('Loaded!')
  }

  const handleDeletePipeline = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Delete this pipeline permanently?')) return
    try {
      await deleteMutation.mutateAsync(id)
      refetchPipelines()
      if (pipelineId === id) {
        clear()
        setName('Untitled Pipeline')
      }
    } catch (err) {
      setValidationMsg(`Delete failed: ${err instanceof Error ? err.message : 'unknown'}`)
    }
  }

  const handleValidate = async () => {
    const graphJson = buildGraphJson()
    try {
      const result = await validateMutation.mutateAsync(graphJson)
      if (result.valid) {
        setValidationMsg(`No errors${result.warnings.length ? ` (${result.warnings.length} warnings)` : ''}`)
      } else {
        setValidationMsg(`Errors: ${result.errors.join('; ')}`)
      }
    } catch {
      if (registry) {
        const result = validateGraphLocal(
          graphJson as { nodes: any[]; edges: any[] },
          registry,
        )
        if (result.valid) {
          setValidationMsg(`No errors${result.warnings.length ? ` (${result.warnings.length} warnings)` : ''}`)
        } else {
          setValidationMsg(`Errors: ${result.errors.join('; ')}`)
        }
      } else {
        setValidationMsg('Validation unavailable')
      }
    }
  }

  const loadTemplate = (tmpl: PipelineData | Template) => {
    if (transport !== 'stopped') handleStop()
    if (isDirty && !confirm('Discard unsaved changes?')) return
    const graph = tmpl.graph_json as { nodes?: unknown[]; edges?: unknown[] }
    const tmplNodes = (graph.nodes || []).map((n: any) => {
      const typeId = n.type || n.data?.type_id || ''
      const nodeDef = registry?.node_types[typeId]
      return { ...n, data: { ...n.data, nodeDef } }
    })
    const tmplEdges = (graph.edges || []).map((e: any) => ({
      ...e,
      id: e.id || `e_${Math.random().toString(36).slice(2, 8)}`,
    }))
    setPipeline(null, `${tmpl.name} (copy)`, tmplNodes, tmplEdges)
    setName(`${tmpl.name} (copy)`)
    setShowTemplates(false)
    setTimeout(() => reactFlow.fitView({ padding: 0.15, duration: 300 }), 50)
  }

  const handleExport = () => {
    const graphJson = buildGraphJson()
    const exportData = { name, graph_json: graphJson }
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${name.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase()}.json`
    a.click()
    URL.revokeObjectURL(url)
    setShowFileMenu(false)
  }

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target?.result as string)
        const graph = data.graph_json || data
        const importNodes = (graph.nodes || []).map((n: any) => {
          const typeId = n.type || n.data?.type_id || ''
          const nodeDef = registry?.node_types[typeId]
          return { ...n, data: { ...n.data, nodeDef } }
        })
        const importEdges = (graph.edges || []).map((e: any) => ({
          ...e,
          id: e.id || `e_${Math.random().toString(36).slice(2, 8)}`,
        }))
        setPipeline(null, data.name || 'Imported Pipeline', importNodes, importEdges)
        setName(data.name || 'Imported Pipeline')
        setTimeout(() => reactFlow.fitView({ padding: 0.15, duration: 300 }), 50)
        setValidationMsg('Imported!')
      } catch {
        setValidationMsg('Import failed — invalid JSON')
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const feedbackCount = edges.filter(e => (e.data as Record<string, unknown>)?.edge_type === 'feedback').length
  const isSaving = createMutation.isPending || updateMutation.isPending
  const isPlaying = transport === 'playing' || transport === 'loading' || transport === 'paused'

  return (
    <>
      <div className="h-12 bg-white border-b border-gray-200 flex items-center px-4 gap-2 shrink-0">
        {/* File menu */}
        <div className="relative" ref={fileMenuRef}>
          <button
            onClick={() => setShowFileMenu(!showFileMenu)}
            className="px-3 py-1 bg-white border border-gray-200 text-xs font-medium rounded hover:bg-gray-50"
          >
            File
          </button>
          {showFileMenu && (
            <div className="absolute top-8 left-0 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-50 w-52">
              <button onClick={handleNew} className="w-full text-left px-3 py-1.5 hover:bg-gray-50 text-xs flex justify-between">
                <span>New Pipeline</span>
                <span className="text-gray-300">Ctrl+N</span>
              </button>
              <button onClick={handleOpen} className="w-full text-left px-3 py-1.5 hover:bg-gray-50 text-xs flex justify-between">
                <span>Open...</span>
                <span className="text-gray-300">Ctrl+O</span>
              </button>
              <div className="h-px bg-gray-100 my-1" />
              <button onClick={() => { handleSave(); setShowFileMenu(false) }} disabled={isSaving} className="w-full text-left px-3 py-1.5 hover:bg-gray-50 text-xs flex justify-between disabled:opacity-50">
                <span>{pipelineId ? 'Save' : 'Save (new)'}</span>
                <span className="text-gray-300">Ctrl+S</span>
              </button>
              <button onClick={() => { handleSaveAs(); setShowFileMenu(false) }} disabled={isSaving} className="w-full text-left px-3 py-1.5 hover:bg-gray-50 text-xs disabled:opacity-50">
                Save As...
              </button>
              <div className="h-px bg-gray-100 my-1" />
              <button onClick={handleExport} disabled={nodes.length === 0} className="w-full text-left px-3 py-1.5 hover:bg-gray-50 text-xs disabled:opacity-50">
                Export as JSON
              </button>
              <button onClick={() => { fileInputRef.current?.click(); setShowFileMenu(false) }} className="w-full text-left px-3 py-1.5 hover:bg-gray-50 text-xs">
                Import from JSON
              </button>
            </div>
          )}
        </div>
        <input ref={fileInputRef} type="file" accept=".json" onChange={handleImport} className="hidden" />

        {/* Pipeline name */}
        <input
          type="text"
          value={name}
          onChange={(e) => { setName(e.target.value); setDirty(true) }}
          className="border border-gray-200 rounded px-2 py-1 text-sm font-medium w-48"
          placeholder="Pipeline name"
        />

        {isDirty && !isPlaying && <span className="text-xs text-amber-500 shrink-0">unsaved</span>}

        {/* Undo / Redo */}
        <div className="flex gap-0.5 ml-1">
          <button onClick={undo} disabled={!canUndo()} className="px-1.5 py-1 text-xs text-gray-500 hover:bg-gray-100 rounded disabled:opacity-30" title="Undo (Ctrl+Z)">↶</button>
          <button onClick={redo} disabled={!canRedo()} className="px-1.5 py-1 text-xs text-gray-500 hover:bg-gray-100 rounded disabled:opacity-30" title="Redo (Ctrl+Shift+Z)">↷</button>
        </div>

        <div className="w-px h-6 bg-gray-200" />

        {/* Save */}
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="px-3 py-1 bg-slate-800 text-white text-xs font-medium rounded hover:bg-slate-700 disabled:opacity-50"
          title="Save to database (Ctrl+S)"
        >
          {isSaving ? 'Saving...' : 'Save'}
        </button>

        {/* Check errors */}
        <button
          onClick={handleValidate}
          disabled={validateMutation.isPending}
          className="px-3 py-1 bg-white border border-gray-200 text-xs font-medium rounded hover:bg-gray-50"
          title="Check for connection errors and port mismatches"
        >
          Check Errors
        </button>

        <div className="w-px h-6 bg-gray-200" />

        {/* Transport controls */}
        <div className="flex items-center gap-1">
          {/* Play */}
          {transport === 'stopped' ? (
            <button
              onClick={handlePlay}
              disabled={nodes.length === 0}
              className="flex items-center gap-1.5 px-3 py-1 bg-emerald-600 text-white text-xs font-medium rounded hover:bg-emerald-500 disabled:opacity-50"
              title="Play — continuously execute pipeline with random utterances"
            >
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
              </svg>
              Play
            </button>
          ) : (
            <>
              {/* Pause / Resume */}
              <button
                onClick={handlePause}
                className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded ${
                  transport === 'paused'
                    ? 'bg-emerald-600 text-white hover:bg-emerald-500'
                    : 'bg-amber-500 text-white hover:bg-amber-400'
                }`}
                title={transport === 'paused' ? 'Resume' : 'Pause'}
              >
                {transport === 'paused' ? (
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
                  </svg>
                ) : (
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M5.5 3a1.5 1.5 0 00-1.5 1.5v11A1.5 1.5 0 005.5 17h1A1.5 1.5 0 008 15.5v-11A1.5 1.5 0 006.5 3h-1zm8 0a1.5 1.5 0 00-1.5 1.5v11a1.5 1.5 0 001.5 1.5h1a1.5 1.5 0 001.5-1.5v-11A1.5 1.5 0 0014.5 3h-1z" clipRule="evenodd" />
                  </svg>
                )}
              </button>
              {/* Stop */}
              <button
                onClick={handleStop}
                className="flex items-center gap-1 px-2.5 py-1 bg-red-500 text-white text-xs font-medium rounded hover:bg-red-400"
                title="Stop"
              >
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <rect x="4" y="4" width="12" height="12" rx="1.5" />
                </svg>
              </button>
            </>
          )}
        </div>

        {/* Now-playing info */}
        {isPlaying && (
          <div className="flex items-center gap-2 min-w-0 flex-1">
            {transport === 'loading' && (
              <span className="inline-block w-3 h-3 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin shrink-0" />
            )}
            {transport === 'playing' && (
              <div className="flex gap-0.5 items-end h-3 shrink-0">
                <div className="w-0.5 bg-emerald-500 animate-pulse" style={{ height: '8px', animationDelay: '0ms' }} />
                <div className="w-0.5 bg-emerald-500 animate-pulse" style={{ height: '12px', animationDelay: '150ms' }} />
                <div className="w-0.5 bg-emerald-500 animate-pulse" style={{ height: '6px', animationDelay: '300ms' }} />
                <div className="w-0.5 bg-emerald-500 animate-pulse" style={{ height: '10px', animationDelay: '100ms' }} />
              </div>
            )}
            {transport === 'paused' && (
              <span className="text-[10px] text-amber-500 font-medium shrink-0">PAUSED</span>
            )}
            <span className="text-[10px] text-gray-500 truncate">
              {nowPlaying ? `"${nowPlaying}"` : 'Generating...'}
            </span>
            {iterationCount > 0 && (
              <span className="text-[9px] text-gray-300 shrink-0">#{iterationCount}</span>
            )}
          </div>
        )}

        {/* Error display */}
        {lastError && transport === 'stopped' && (
          <span className="text-[10px] text-red-500 truncate max-w-xs">{lastError}</span>
        )}

        {/* Spacer (only when not playing) */}
        {!isPlaying && <div className="flex-1" />}

        {/* Templates */}
        {!isPlaying && (
          <div className="relative" ref={templateRef}>
            <button
              onClick={() => setShowTemplates(!showTemplates)}
              className="px-3 py-1 bg-white border border-gray-200 text-xs font-medium rounded hover:bg-gray-50"
            >
              Templates
            </button>
            {showTemplates && templates && (
              <div className="absolute top-8 right-0 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-50 w-72">
                {templates.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => loadTemplate(t)}
                    className="w-full text-left px-3 py-2 hover:bg-gray-50 text-xs"
                  >
                    <div className="font-medium text-gray-800">{t.name}</div>
                    <div className="text-gray-400 text-[10px] mt-0.5 line-clamp-2">{t.description}</div>
                  </button>
                ))}
                {templates.length === 0 && (
                  <div className="px-3 py-2 text-xs text-gray-400">No templates yet</div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Stats bar */}
        <div className="flex gap-3 text-[10px] text-gray-400 shrink-0">
          <span>{nodes.length} nodes</span>
          <span>{edges.length} edges</span>
          {feedbackCount > 0 && <span className="text-orange-400">{feedbackCount} feedback</span>}
          {pipelineId && <span className="text-blue-400" title={pipelineId}>saved</span>}
        </div>

        {/* Validation messages */}
        {validationMsg && !isPlaying && (
          <span className={`text-xs shrink-0 ml-2 ${validationMsg.startsWith('No errors') || validationMsg === 'Saved!' || validationMsg === 'Imported!' || validationMsg === 'Loaded!' || validationMsg.startsWith('Saved as') ? 'text-green-600' : 'text-red-500'}`}>
            {validationMsg}
          </span>
        )}
      </div>

      {/* Open Pipeline dialog */}
      {showOpenDialog && (
        <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50" onClick={() => setShowOpenDialog(false)}>
          <div className="bg-white rounded-lg shadow-xl w-[480px] max-h-[70vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center px-5 py-3 border-b border-gray-100">
              <h3 className="text-sm font-bold text-gray-800">Open Pipeline</h3>
              <button onClick={() => setShowOpenDialog(false)} className="text-gray-400 hover:text-gray-600 text-sm">Close</button>
            </div>
            <div className="flex-1 overflow-y-auto">
              {!savedPipelines || savedPipelines.length === 0 ? (
                <div className="px-5 py-8 text-center text-xs text-gray-400">
                  No saved pipelines yet. Use Save to store your first pipeline.
                </div>
              ) : (
                <div className="divide-y divide-gray-50">
                  {savedPipelines.map((p) => (
                    <div
                      key={p.id}
                      onClick={() => loadPipeline(p)}
                      className={`px-5 py-3 hover:bg-gray-50 cursor-pointer flex items-center justify-between group ${pipelineId === p.id ? 'bg-blue-50' : ''}`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-medium text-gray-800 truncate">{p.name}</div>
                        <div className="text-[10px] text-gray-400 mt-0.5">
                          {p.description || `${(p.graph_json as any)?.nodes?.length || 0} nodes`}
                          {p.updated_at && (
                            <span className="ml-2">{new Date(p.updated_at).toLocaleDateString()}</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0 ml-3">
                        {pipelineId === p.id && (
                          <span className="text-[9px] text-blue-500 font-medium">current</span>
                        )}
                        <button
                          onClick={(e) => handleDeletePipeline(p.id, e)}
                          className="text-[10px] text-red-400 hover:text-red-600 opacity-0 group-hover:opacity-100 transition-opacity"
                          title="Delete pipeline"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
