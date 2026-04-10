/** Right panel — configuration for the selected node */

import { useState, useCallback, useEffect, useRef } from 'react'
import { useGraphStore } from '../hooks/useGraphStore'
import type { NodeTypeRegistry, ConfigFieldDef } from '../api/client'
import { warmupModel } from '../api/client'

interface ConfigPanelProps {
  registry: NodeTypeRegistry | undefined
}

export default function ConfigPanel({ registry }: ConfigPanelProps) {
  const { nodes, selectedNodeId, updateNodeConfig, removeNode } = useGraphStore()

  if (!selectedNodeId || !registry) {
    return (
      <div className="w-64 bg-white border-l border-gray-200 p-4">
        <p className="text-xs text-gray-400">Select a node to configure</p>
      </div>
    )
  }

  const node = nodes.find((n) => n.id === selectedNodeId)
  if (!node) return null

  const data = node.data as Record<string, unknown>
  const typeId = (data.type_id as string) || node.type || ''
  const nodeDef = registry.node_types[typeId]
  if (!nodeDef) return null

  const config = (data.config as Record<string, unknown>) || {}

  const handleChange = (fieldName: string, value: unknown) => {
    updateNodeConfig(selectedNodeId, { [fieldName]: value })

    // Trigger model warmup when LLM backend changes
    if (fieldName === 'backend' && (typeId === 'llm' || typeId === 'llm_realtime') && typeof value === 'string' && value) {
      const { setModelStatus } = useGraphStore.getState()
      setModelStatus(selectedNodeId, { status: 'loading' })
      warmupModel(value).then((result) => {
        if (result.status === 'ready') {
          setModelStatus(selectedNodeId, {
            status: 'ready',
            model: result.model,
            loadTimeMs: result.load_time_ms,
          })
        } else {
          setModelStatus(selectedNodeId, {
            status: 'error',
            model: result.model,
            error: result.error,
          })
        }
      }).catch((err) => {
        setModelStatus(selectedNodeId, {
          status: 'error',
          error: err.message,
        })
      })
    }
  }

  return (
    <div className="w-64 bg-white border-l border-gray-200 flex flex-col shrink-0 overflow-y-auto">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-100">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-gray-800">{nodeDef.label}</h3>
          <button
            onClick={() => removeNode(selectedNodeId)}
            className="text-xs text-red-500 hover:text-red-700"
            title="Delete node"
          >
            Delete
          </button>
        </div>
        <p className="text-[10px] text-gray-400 mt-0.5">{nodeDef.description}</p>
      </div>

      {/* Config fields */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {/* Label field (always present) */}
        <FieldRenderer
          field={{ name: '_label', type: 'string', label: 'Label', default: nodeDef.label, description: '' }}
          value={(data.label as string) || nodeDef.label}
          onChange={(v) => {
            // Update the node label directly
            useGraphStore.getState().setNodes(
              useGraphStore.getState().nodes.map((n) =>
                n.id === selectedNodeId ? { ...n, data: { ...n.data, label: v } } : n
              )
            )
          }}
        />

        {nodeDef.config_fields.map((field) => (
          <FieldRenderer
            key={field.name}
            field={field}
            value={config[field.name] ?? field.default}
            onChange={(v) => handleChange(field.name, v)}
          />
        ))}

        {/* Model warmup status for LLM nodes */}
        {(typeId === 'llm' || typeId === 'llm_realtime') && (
          <ModelStatusIndicator nodeId={selectedNodeId} />
        )}

        {/* Preview / Play button for source nodes */}
        {(typeId === 'speech_source' || typeId === 'far_end_source' || typeId === 'noise_generator') && (
          <PreviewButton nodeId={selectedNodeId} config={config} typeId={typeId} />
        )}

        {/* Running output log for text_output nodes — per-node */}
        {typeId === 'text_output' && (
          <OutputLog nodeId={selectedNodeId} />
        )}

        {/* Histogram display + popup toggle */}
        {typeId === 'histogram' && (
          <>
            <HistogramDisplay nodeId={selectedNodeId} config={config} />
            <HistogramPopupButton nodeId={selectedNodeId} />
          </>
        )}
      </div>

      {/* Node ID */}
      <div className="px-4 py-2 border-t border-gray-100 text-[9px] text-gray-300 font-mono truncate">
        {selectedNodeId}
      </div>
    </div>
  )
}

function FieldRenderer({
  field,
  value,
  onChange,
}: {
  field: ConfigFieldDef
  value: unknown
  onChange: (value: unknown) => void
}) {
  const label = field.label || field.name

  switch (field.type) {
    case 'string':
      if (field.multiline) {
        return (
          <div>
            <label className="text-[10px] font-medium text-gray-500 block mb-0.5">{label}</label>
            <textarea
              value={String(value || '')}
              onChange={(e) => onChange(e.target.value)}
              className="w-full border border-gray-200 rounded px-2 py-1 text-xs resize-y min-h-[80px]"
              placeholder={field.description || ''}
              rows={4}
            />
          </div>
        )
      }
      return (
        <div>
          <label className="text-[10px] font-medium text-gray-500 block mb-0.5">{label}</label>
          <input
            type="text"
            value={String(value || '')}
            onChange={(e) => onChange(e.target.value)}
            className="w-full border border-gray-200 rounded px-2 py-1 text-xs"
            placeholder={field.description || ''}
          />
        </div>
      )

    case 'number':
      return (
        <div>
          <label className="text-[10px] font-medium text-gray-500 block mb-0.5">{label}</label>
          <input
            type="number"
            value={value !== null && value !== undefined ? Number(value) : ''}
            onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
            className="w-full border border-gray-200 rounded px-2 py-1 text-xs"
            min={field.min ?? undefined}
            max={field.max ?? undefined}
            step={field.step ?? undefined}
          />
          {field.description && <p className="text-[9px] text-gray-300 mt-0.5">{field.description}</p>}
        </div>
      )

    case 'slider':
      return (
        <div>
          <label className="text-[10px] font-medium text-gray-500 flex justify-between mb-0.5">
            <span>{label}</span>
            <span className="text-gray-400 font-mono">{String(value)}</span>
          </label>
          <input
            type="range"
            value={Number(value)}
            onChange={(e) => onChange(Number(e.target.value))}
            className="w-full h-1.5 accent-slate-700"
            min={field.min ?? 0}
            max={field.max ?? 100}
            step={field.step ?? 1}
          />
        </div>
      )

    case 'select':
      return (
        <div>
          <label className="text-[10px] font-medium text-gray-500 block mb-0.5">{label}</label>
          <select
            value={String(value || '')}
            onChange={(e) => onChange(e.target.value)}
            className="w-full border border-gray-200 rounded px-2 py-1 text-xs bg-white"
          >
            {field.options?.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      )

    case 'boolean':
      return (
        <div className="flex items-center justify-between">
          <label className="text-[10px] font-medium text-gray-500">{label}</label>
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
            className="rounded accent-slate-700"
          />
        </div>
      )

    case 'json':
      return (
        <div>
          <label className="text-[10px] font-medium text-gray-500 block mb-0.5">{label}</label>
          <textarea
            value={typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
            onChange={(e) => {
              try {
                onChange(JSON.parse(e.target.value))
              } catch {
                // Allow partial JSON while typing
                onChange(e.target.value)
              }
            }}
            className="w-full border border-gray-200 rounded px-2 py-1 text-xs font-mono h-16 resize-y"
          />
          {field.description && <p className="text-[9px] text-gray-300 mt-0.5">{field.description}</p>}
        </div>
      )

    default:
      return null
  }
}

function ModelStatusIndicator({ nodeId }: { nodeId: string }) {
  const status = useGraphStore((s) => s.modelStatus[nodeId])

  if (!status) return null

  return (
    <div className="pt-2 border-t border-gray-100">
      <label className="text-[10px] font-medium text-gray-500 block mb-1">Model Status</label>
      {status.status === 'loading' && (
        <div className="flex items-center gap-2 text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
          <span className="inline-block w-3 h-3 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
          <span>Loading model...</span>
        </div>
      )}
      {status.status === 'ready' && (
        <div className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-2 py-1.5">
          <div className="flex items-center gap-1.5">
            <span className="text-emerald-500">&#10003;</span>
            <span className="font-medium">{status.model}</span>
          </div>
          {status.loadTimeMs !== undefined && status.loadTimeMs > 0 && (
            <div className="text-[10px] text-emerald-600 mt-0.5">
              Loaded in {status.loadTimeMs >= 1000
                ? `${(status.loadTimeMs / 1000).toFixed(1)}s`
                : `${status.loadTimeMs}ms`}
            </div>
          )}
        </div>
      )}
      {status.status === 'error' && (
        <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1.5">
          <div className="font-medium">Failed to load</div>
          <div className="text-[10px] text-red-500 mt-0.5 break-all">{status.error}</div>
        </div>
      )}
    </div>
  )
}

const EMPTY_LOG: string[] = []

function OutputLog({ nodeId }: { nodeId: string }) {
  const outputLog = useGraphStore((s) => s.outputLogs?.[nodeId] ?? EMPTY_LOG)
  const clearOutputLog = useGraphStore((s) => s.clearOutputLog)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [outputLog.length])

  return (
    <div className="pt-2 border-t border-gray-100">
      <div className="flex items-center justify-between mb-1">
        <label className="text-[10px] font-medium text-gray-500">Output Log</label>
        {outputLog.length > 0 && (
          <button
            onClick={() => clearOutputLog(nodeId)}
            className="text-[9px] text-gray-400 hover:text-red-500"
          >
            Clear
          </button>
        )}
      </div>
      <div
        ref={scrollRef}
        className="bg-gray-50 border border-gray-200 rounded p-2 text-xs font-mono max-h-[300px] min-h-[80px] overflow-y-auto whitespace-pre-wrap"
      >
        {outputLog.length === 0 ? (
          <span className="text-gray-300 italic text-[10px]">Press Play to see output...</span>
        ) : (
          outputLog.map((entry, i) => (
            <div key={i} className="pb-1 mb-1 border-b border-gray-100 last:border-0 last:mb-0 last:pb-0">
              <span className="text-[9px] text-gray-300 mr-1">#{i + 1}</span>
              <span className="text-gray-700">{entry}</span>
            </div>
          ))
        )}
      </div>
      {outputLog.length > 0 && (
        <p className="text-[9px] text-gray-300 mt-1">{outputLog.length} entries</p>
      )}
    </div>
  )
}

/** Aggregate raw data into { label, count, color } buckets */
function computeBuckets(data: string[], mode: string) {
  if (mode === 'binary') {
    // Exactly 2 buckets: "0" = Pass, everything else = Fail
    let pass = 0
    let fail = 0
    for (const v of data) {
      if (v.trim() === '0') pass++
      else fail++
    }
    return [
      { label: 'Pass (0)', count: pass, color: '#22C55E' },
      { label: 'Fail (1)', count: fail, color: '#EF4444' },
    ]
  }

  // Categorical / numeric: one bucket per unique value
  const counts: Record<string, number> = {}
  for (const v of data) {
    const key = v.trim() || '(empty)'
    counts[key] = (counts[key] || 0) + 1
  }
  const colors = ['#3B82F6', '#22C55E', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#14B8A6', '#F97316']
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([key, count], i) => ({ label: key, count, color: colors[i % colors.length] }))
}

function HistogramDisplay({ nodeId, config }: { nodeId: string; config: Record<string, unknown> }) {
  const data = useGraphStore((s) => s.histogramData?.[nodeId] ?? EMPTY_LOG)
  const clearData = useGraphStore((s) => s.clearHistogramData)
  const mode = String(config.mode || 'binary')
  const total = data.length
  const buckets = computeBuckets(data, mode)
  const maxCount = Math.max(1, ...buckets.map((b) => b.count))

  return (
    <div className="pt-2 border-t border-gray-100">
      <div className="flex items-center justify-between mb-1">
        <label className="text-[10px] font-medium text-gray-500">Histogram</label>
        {total > 0 && (
          <button onClick={() => clearData(nodeId)} className="text-[9px] text-gray-400 hover:text-red-500">
            Clear
          </button>
        )}
      </div>
      {total === 0 ? (
        <div className="bg-gray-50 border border-gray-200 rounded p-2 min-h-[60px] flex items-center justify-center">
          <span className="text-gray-300 italic text-[10px]">Press Play to collect data...</span>
        </div>
      ) : (
        <div className="bg-gray-50 border border-gray-200 rounded p-2">
          {/* Bars side by side */}
          <div className="flex items-end gap-2 justify-center" style={{ height: 80 }}>
            {buckets.map((b) => {
              const heightPct = maxCount > 0 ? (b.count / maxCount) * 100 : 0
              return (
                <div key={b.label} className="flex flex-col items-center flex-1">
                  <span className="text-[9px] text-gray-500 font-mono mb-0.5">{b.count}</span>
                  <div className="w-full flex items-end" style={{ height: 56 }}>
                    <div
                      className="w-full rounded-t transition-all duration-300"
                      style={{
                        height: `${Math.max(heightPct, 2)}%`,
                        backgroundColor: b.color,
                      }}
                    />
                  </div>
                  <span className="text-[8px] font-medium text-gray-600 mt-0.5 text-center leading-tight">{b.label}</span>
                </div>
              )
            })}
          </div>
          {/* Percentages */}
          <div className="flex gap-2 justify-center mt-1">
            {buckets.map((b) => (
              <span key={b.label} className="text-[9px] text-gray-400 flex-1 text-center">
                {total > 0 ? ((b.count / total) * 100).toFixed(0) : 0}%
              </span>
            ))}
          </div>
          <p className="text-[9px] text-gray-300 mt-1.5 text-center">{total} samples</p>
        </div>
      )}
    </div>
  )
}

function HistogramPopupButton({ nodeId }: { nodeId: string }) {
  const isOpen = useGraphStore((s) => s.openHistograms?.includes(nodeId) ?? false)
  const toggleHistogram = useGraphStore((s) => s.toggleHistogram)

  return (
    <div className="pt-1">
      <button
        onClick={() => toggleHistogram(nodeId)}
        className={`w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
          isOpen
            ? 'bg-blue-50 text-blue-600 border border-blue-200 hover:bg-blue-100'
            : 'bg-gray-100 text-gray-600 border border-gray-200 hover:bg-gray-200'
        }`}
      >
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
        {isOpen ? 'Close Popup' : 'Open Popup'}
      </button>
      <p className="text-[9px] text-gray-300 mt-0.5 text-center">or double-click the node</p>
    </div>
  )
}

function PreviewButton({ nodeId, config, typeId }: { nodeId: string; config: Record<string, unknown>; typeId: string }) {
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handlePreview = useCallback(async () => {
    setPlaying(true)
    setError(null)
    try {
      const resp = await fetch('/api/pipelines/preview-node', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: nodeId, type_id: typeId, config }),
      })
      if (!resp.ok) {
        const msg = await resp.text()
        throw new Error(msg || `HTTP ${resp.status}`)
      }
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audio.onended = () => { setPlaying(false); URL.revokeObjectURL(url) }
      audio.onerror = () => { setPlaying(false); setError('Playback failed'); URL.revokeObjectURL(url) }
      await audio.play()
    } catch (e) {
      setPlaying(false)
      setError(e instanceof Error ? e.message : 'Preview failed')
    }
  }, [nodeId, typeId, config])

  return (
    <div className="pt-2 border-t border-gray-100">
      <button
        onClick={handlePreview}
        disabled={playing}
        className={`w-full flex items-center justify-center gap-2 px-3 py-2 rounded text-xs font-medium transition-colors ${
          playing
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-slate-700 text-white hover:bg-slate-600'
        }`}
      >
        {playing ? (
          <>
            <span className="inline-block w-3 h-3 border-2 border-gray-300 border-t-transparent rounded-full animate-spin" />
            Playing...
          </>
        ) : (
          <>
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
              <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
            </svg>
            Preview
          </>
        )}
      </button>
      {error && <p className="text-[9px] text-red-500 mt-1">{error}</p>}
    </div>
  )
}
