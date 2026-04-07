/** Right panel — configuration for the selected node */

import { useGraphStore } from '../hooks/useGraphStore'
import type { NodeTypeRegistry, ConfigFieldDef } from '../api/client'

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
