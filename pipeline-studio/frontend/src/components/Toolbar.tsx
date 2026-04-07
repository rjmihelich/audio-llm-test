/** Top toolbar — pipeline name, save, validate, run, templates, export/import, stats */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useReactFlow } from '@xyflow/react'
import { useGraphStore } from '../hooks/useGraphStore'
import {
  useCreatePipeline,
  useUpdatePipeline,
  usePipelines,
  useValidateGraph,
  useExecutePreview,
} from '../hooks/usePipelineApi'
import type { PipelineData, NodeTypeRegistry } from '../api/client'
import { STATIC_TEMPLATES } from '../utils/templates'
import { validateGraph as validateGraphLocal } from '../utils/validation'
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts'

interface ToolbarProps {
  registry: NodeTypeRegistry | undefined
}

export default function Toolbar({ registry }: ToolbarProps) {
  const {
    pipelineId, pipelineName, nodes, edges, isDirty,
    setPipeline, setDirty, canUndo, canRedo, undo, redo,
  } = useGraphStore()

  const [name, setName] = useState(pipelineName)
  const [showTemplates, setShowTemplates] = useState(false)
  const [validationMsg, setValidationMsg] = useState<string | null>(null)
  const [previewResult, setPreviewResult] = useState<string | null>(null)
  const templateRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const reactFlow = useReactFlow()

  const createMutation = useCreatePipeline()
  const updateMutation = useUpdatePipeline()
  const validateMutation = useValidateGraph()
  const previewMutation = useExecutePreview()
  const { data: backendTemplates } = usePipelines(true)
  const templates = backendTemplates && backendTemplates.length > 0 ? backendTemplates : STATIC_TEMPLATES

  // Sync name when pipeline changes
  useEffect(() => { setName(pipelineName) }, [pipelineName])

  // Close template dropdown on outside click
  useEffect(() => {
    if (!showTemplates) return
    const handler = (e: MouseEvent) => {
      if (templateRef.current && !templateRef.current.contains(e.target as Node)) {
        setShowTemplates(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showTemplates])

  // Auto-clear validation messages
  useEffect(() => {
    if (!validationMsg) return
    const t = setTimeout(() => setValidationMsg(null), 4000)
    return () => clearTimeout(t)
  }, [validationMsg])

  // Serialize graph for API
  const buildGraphJson = () => ({
    nodes: nodes.map((n) => {
      const { nodeDef, ...rest } = n.data as Record<string, unknown>
      return {
        id: n.id,
        type: (n.data as Record<string, unknown>).type_id || n.type,
        position: n.position,
        data: rest,
      }
    }),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      sourceHandle: e.sourceHandle,
      target: e.target,
      targetHandle: e.targetHandle,
      data: e.data || { edge_type: 'normal' },
    })),
    viewport: { x: 0, y: 0, zoom: 1 },
  })

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
  }, [pipelineId, name, nodes, edges, createMutation, updateMutation, setPipeline, setDirty])

  // Register keyboard shortcuts
  useKeyboardShortcuts(handleSave)

  const handleValidate = async () => {
    const graphJson = buildGraphJson()
    try {
      const result = await validateMutation.mutateAsync(graphJson)
      if (result.valid) {
        setValidationMsg(`Valid! ${result.warnings.length ? `(${result.warnings.length} warnings)` : ''}`)
      } else {
        setValidationMsg(`Invalid: ${result.errors.join('; ')}`)
      }
    } catch {
      if (registry) {
        const result = validateGraphLocal(
          graphJson as { nodes: any[]; edges: any[] },
          registry,
        )
        if (result.valid) {
          setValidationMsg(`Valid (local)! ${result.warnings.length ? `(${result.warnings.length} warnings)` : ''}`)
        } else {
          setValidationMsg(`Invalid: ${result.errors.join('; ')}`)
        }
      } else {
        setValidationMsg('Validation unavailable')
      }
    }
  }

  const handlePreview = async () => {
    if (!pipelineId) {
      setPreviewResult('Save the pipeline first')
      return
    }
    try {
      const result = await previewMutation.mutateAsync(pipelineId)
      setPreviewResult(JSON.stringify(result, null, 2))
    } catch (e) {
      setPreviewResult(`Preview error: ${e instanceof Error ? e.message : 'unknown'}`)
    }
  }

  const loadTemplate = (tmpl: PipelineData) => {
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
    // Auto-fit after loading template
    setTimeout(() => reactFlow.fitView({ padding: 0.15, duration: 300 }), 50)
  }

  // Export pipeline as JSON file
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
  }

  // Import pipeline from JSON file
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
    // Reset input so same file can be re-imported
    e.target.value = ''
  }

  // Count feedback edges
  const feedbackCount = edges.filter(e => (e.data as Record<string, unknown>)?.edge_type === 'feedback').length

  return (
    <>
      <div className="h-12 bg-white border-b border-gray-200 flex items-center px-4 gap-2 shrink-0">
        {/* Pipeline name */}
        <input
          type="text"
          value={name}
          onChange={(e) => { setName(e.target.value); setDirty(true) }}
          className="border border-gray-200 rounded px-2 py-1 text-sm font-medium w-48"
          placeholder="Pipeline name"
        />

        {isDirty && <span className="text-xs text-amber-500 shrink-0">unsaved</span>}

        {/* Undo / Redo */}
        <div className="flex gap-0.5 ml-1">
          <button
            onClick={undo}
            disabled={!canUndo()}
            className="px-1.5 py-1 text-xs text-gray-500 hover:bg-gray-100 rounded disabled:opacity-30"
            title="Undo (Ctrl+Z)"
          >
            ↶
          </button>
          <button
            onClick={redo}
            disabled={!canRedo()}
            className="px-1.5 py-1 text-xs text-gray-500 hover:bg-gray-100 rounded disabled:opacity-30"
            title="Redo (Ctrl+Shift+Z)"
          >
            ↷
          </button>
        </div>

        <div className="w-px h-6 bg-gray-200" />

        {/* Actions */}
        <button
          onClick={handleSave}
          disabled={createMutation.isPending || updateMutation.isPending}
          className="px-3 py-1 bg-slate-800 text-white text-xs font-medium rounded hover:bg-slate-700 disabled:opacity-50"
          title="Ctrl+S"
        >
          {createMutation.isPending || updateMutation.isPending ? 'Saving...' : 'Save'}
        </button>

        <button
          onClick={handleValidate}
          disabled={validateMutation.isPending}
          className="px-3 py-1 bg-white border border-gray-200 text-xs font-medium rounded hover:bg-gray-50"
        >
          Validate
        </button>

        <button
          onClick={handlePreview}
          disabled={previewMutation.isPending || !pipelineId}
          className="px-3 py-1 bg-white border border-gray-200 text-xs font-medium rounded hover:bg-gray-50 disabled:opacity-50"
        >
          Run Preview
        </button>

        <div className="w-px h-6 bg-gray-200" />

        {/* Templates */}
        <div className="relative" ref={templateRef}>
          <button
            onClick={() => setShowTemplates(!showTemplates)}
            className="px-3 py-1 bg-white border border-gray-200 text-xs font-medium rounded hover:bg-gray-50"
          >
            Templates
          </button>
          {showTemplates && templates && (
            <div className="absolute top-8 left-0 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-50 w-72">
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

        {/* Export / Import */}
        <button
          onClick={handleExport}
          disabled={nodes.length === 0}
          className="px-2 py-1 bg-white border border-gray-200 text-xs font-medium rounded hover:bg-gray-50 disabled:opacity-50"
          title="Export pipeline as JSON"
        >
          Export
        </button>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="px-2 py-1 bg-white border border-gray-200 text-xs font-medium rounded hover:bg-gray-50"
          title="Import pipeline from JSON"
        >
          Import
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".json"
          onChange={handleImport}
          className="hidden"
        />

        {/* Spacer */}
        <div className="flex-1" />

        {/* Stats bar */}
        <div className="flex gap-3 text-[10px] text-gray-400 shrink-0">
          <span>{nodes.length} nodes</span>
          <span>{edges.length} edges</span>
          {feedbackCount > 0 && <span className="text-orange-400">{feedbackCount} feedback</span>}
        </div>

        {/* Status messages */}
        {validationMsg && (
          <span className={`text-xs shrink-0 ml-2 ${validationMsg.startsWith('Valid') || validationMsg === 'Saved!' || validationMsg === 'Imported!' ? 'text-green-600' : 'text-red-500'}`}>
            {validationMsg}
          </span>
        )}
      </div>

      {/* Preview result modal */}
      {previewResult && (
        <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50" onClick={() => setPreviewResult(null)}>
          <div className="bg-white rounded-lg shadow-xl p-4 max-w-lg max-h-96 overflow-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-2">
              <h3 className="text-sm font-bold">Preview Result</h3>
              <button onClick={() => setPreviewResult(null)} className="text-gray-400 hover:text-gray-600 text-sm">Close</button>
            </div>
            <pre className="text-xs font-mono bg-gray-50 rounded p-3 whitespace-pre-wrap">{previewResult}</pre>
          </div>
        </div>
      )}
    </>
  )
}
