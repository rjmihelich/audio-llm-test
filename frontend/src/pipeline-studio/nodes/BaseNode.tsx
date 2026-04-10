/** Shared node component shell — renders title bar, ports, and content area */

import { Handle, Position, type NodeProps } from '@xyflow/react'
import { PORT_COLORS, type PortType } from '../utils/portTypes'
import type { NodeTypeDef, PortDef } from '../api/client'
import { useGraphStore } from '../hooks/useGraphStore'

interface BaseNodeData {
  type_id: string
  label: string
  config: Record<string, unknown>
  nodeDef?: NodeTypeDef
}

export default function BaseNode({ data, selected, id }: NodeProps) {
  const d = data as unknown as BaseNodeData
  const nodeDef = d.nodeDef
  const modelStatus = useGraphStore((s) =>
    (d.type_id === 'llm' || d.type_id === 'llm_realtime') ? s.modelStatus[id] : undefined
  )

  if (!nodeDef) {
    return (
      <div className="bg-white border border-gray-300 rounded-lg shadow-sm p-3 min-w-[140px]">
        <div className="text-xs font-bold text-gray-500">{d.label || d.type_id}</div>
      </div>
    )
  }

  const inputs = nodeDef.inputs || []
  const outputs = nodeDef.outputs || []

  // For dynamic inputs (mixer), check how many are connected and show extras
  const dynamicInputs: PortDef[] = []
  if (nodeDef.dynamic_inputs) {
    // Show at least the defined inputs plus extras based on config
    for (let i = inputs.length; i < 6; i++) {
      dynamicInputs.push({
        name: `audio_in_${i}`,
        type: 'audio',
        required: false,
        description: `Input ${i + 1}`,
      })
    }
  }

  const allInputs = [...inputs, ...dynamicInputs]

  // For router nodes, only show outputs matching num_routes config
  let visibleOutputs = outputs
  if (d.type_id === 'router') {
    const numRoutes = Number(d.config?.num_routes ?? 2)
    visibleOutputs = outputs.filter((p) => {
      const match = p.name.match(/_(\d+)$/)
      return match ? parseInt(match[1]) < numRoutes : true
    })
  }

  return (
    <div
      className={`bg-white border-2 rounded-lg shadow-sm min-w-[160px] ${
        selected ? 'border-blue-500 ring-2 ring-blue-200' : 'border-gray-200'
      }`}
    >
      {/* Header */}
      <div
        className="px-3 py-1.5 rounded-t-md text-xs font-bold text-white"
        style={{ backgroundColor: nodeDef.color }}
      >
        {d.label || nodeDef.label}
      </div>

      {/* Body */}
      <div className="px-3 py-2 text-[10px] text-gray-500 relative">
        {/* Quick config summary */}
        {d.type_id === 'noise_generator' && (
          <div className="text-gray-700 font-medium">{String(d.config?.noise_type || 'pink_lpf')}</div>
        )}
        {d.type_id === 'mixer' && (
          <div className="text-gray-700 font-medium">Master: {String(d.config?.master_gain_db ?? 0)} dB</div>
        )}
        {d.type_id === 'router' && (
          <div className="text-gray-700 font-medium">{String(d.config?.num_routes ?? 2)} routes</div>
        )}
        {d.type_id === 'llm' && (
          <>
            <div className="text-gray-700 font-medium truncate max-w-[130px]">{String(d.config?.backend || '')}</div>
            {modelStatus?.status === 'loading' && (
              <div className="flex items-center gap-1 mt-0.5">
                <span className="inline-block w-2 h-2 border border-amber-400 border-t-transparent rounded-full animate-spin" />
                <span className="text-[9px] text-amber-600">Loading...</span>
              </div>
            )}
            {modelStatus?.status === 'ready' && modelStatus.model && (
              <div className="flex items-center gap-1 mt-0.5">
                <span className="text-[9px] text-emerald-500">&#10003;</span>
                <span className="text-[9px] text-emerald-600">{modelStatus.model}</span>
              </div>
            )}
            {modelStatus?.status === 'error' && (
              <div className="text-[9px] text-red-500 mt-0.5 truncate max-w-[130px]">Error loading</div>
            )}
          </>
        )}
        {d.type_id === 'llm_realtime' && (
          <div className="text-gray-700 font-medium">{String(d.config?.model || 'gpt-4o-realtime')}</div>
        )}
        {d.type_id === 'network_sim' && (
          <div className="text-gray-700 font-medium">{String(d.config?.latency_ms ?? 50)}ms</div>
        )}
        {d.type_id === 'echo_simulator' && (
          <div className="text-gray-700 font-medium">{String(d.config?.delay_ms ?? 100)}ms / {String(d.config?.gain_db ?? -6)}dB</div>
        )}
        {d.type_id === 'stt' && (
          <div className="text-gray-700 font-medium">{String(d.config?.backend || 'whisper')}</div>
        )}
        {d.type_id === 'tts' && (
          <div className="text-gray-700 font-medium">{String(d.config?.provider || 'edge')}</div>
        )}

        {/* Input handles */}
        {allInputs.map((port, i) => (
          <Handle
            key={port.name}
            type="target"
            position={Position.Left}
            id={port.name}
            className={`handle-${port.type}`}
            style={{
              top: `${28 + (i + 1) * 20}px`,
              background: PORT_COLORS[port.type as PortType],
              width: 10,
              height: 10,
              border: '2px solid white',
            }}
            title={`${port.name} (${port.type})`}
          />
        ))}

        {/* Output handles */}
        {visibleOutputs.map((port, i) => (
          <Handle
            key={port.name}
            type="source"
            position={Position.Right}
            id={port.name}
            className={`handle-${port.type}`}
            style={{
              top: `${28 + (i + 1) * 20}px`,
              background: PORT_COLORS[port.type as PortType],
              width: 10,
              height: 10,
              border: '2px solid white',
            }}
            title={`${port.name} (${port.type})`}
          />
        ))}

        {/* Port labels */}
        <div className="flex justify-between mt-1 gap-4">
          <div className="space-y-0.5">
            {allInputs.map((p) => (
              <div key={p.name} className="text-[9px] text-gray-400">{p.name}</div>
            ))}
          </div>
          <div className="space-y-0.5 text-right">
            {visibleOutputs.map((p) => (
              <div key={p.name} className="text-[9px] text-gray-400">{p.name}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
