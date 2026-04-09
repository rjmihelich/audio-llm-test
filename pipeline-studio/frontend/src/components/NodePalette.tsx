/** Left sidebar — draggable block palette organized by category, with search */

import { useState } from 'react'
import type { NodeTypeRegistry } from '../api/client'

interface NodePaletteProps {
  registry: NodeTypeRegistry | undefined
  isLoading: boolean
}

export default function NodePalette({ registry, isLoading }: NodePaletteProps) {
  const [search, setSearch] = useState('')

  if (isLoading || !registry) {
    return (
      <div className="w-56 bg-white border-r border-gray-200 p-4">
        <div className="text-sm text-gray-400">Loading blocks...</div>
      </div>
    )
  }

  const searchLower = search.toLowerCase()

  // Group node types by category, filtering by search
  const grouped: Record<string, typeof registry.node_types[string][]> = {}
  for (const nodeDef of Object.values(registry.node_types)) {
    if (search && !nodeDef.label.toLowerCase().includes(searchLower) &&
        !nodeDef.description.toLowerCase().includes(searchLower) &&
        !nodeDef.type_id.toLowerCase().includes(searchLower)) {
      continue
    }
    if (!grouped[nodeDef.category]) grouped[nodeDef.category] = []
    grouped[nodeDef.category].push(nodeDef)
  }

  const categoryOrder = ['sources', 'processing', 'telephony', 'network', 'speech', 'llm', 'evaluation', 'output']
  const hasResults = Object.values(grouped).some(g => g.length > 0)

  return (
    <div className="w-56 bg-white border-r border-gray-200 flex flex-col shrink-0 overflow-y-auto">
      <div className="px-4 py-3 border-b border-gray-100">
        <h2 className="text-sm font-bold text-gray-800">Blocks</h2>
        <p className="text-[10px] text-gray-400 mt-0.5">Drag onto canvas</p>
      </div>

      {/* Search input */}
      <div className="px-3 py-2 border-b border-gray-100">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search blocks..."
          className="w-full border border-gray-200 rounded px-2 py-1 text-xs focus:outline-none focus:border-blue-300 focus:ring-1 focus:ring-blue-200"
        />
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-3">
        {categoryOrder.map((catKey) => {
          const cat = registry.categories[catKey]
          const nodes = grouped[catKey]
          if (!cat || !nodes?.length) return null

          return (
            <div key={catKey}>
              <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider px-2 mb-1">
                {cat.label}
              </div>
              <div className="space-y-0.5">
                {nodes.map((nodeDef) => (
                  <PaletteItem key={nodeDef.type_id} nodeDef={nodeDef} />
                ))}
              </div>
            </div>
          )
        })}

        {!hasResults && search && (
          <div className="text-xs text-gray-400 px-2 py-4 text-center">
            No blocks match &ldquo;{search}&rdquo;
          </div>
        )}
      </div>
    </div>
  )
}

function PaletteItem({ nodeDef }: { nodeDef: NodeTypeRegistry['node_types'][string] }) {
  const onDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData('application/pipeline-node-type', nodeDef.type_id)
    e.dataTransfer.effectAllowed = 'move'
  }

  return (
    <div
      draggable
      onDragStart={onDragStart}
      className="flex items-center gap-2 px-2 py-1.5 rounded-md cursor-grab hover:bg-gray-50 active:cursor-grabbing transition-colors"
      title={nodeDef.description}
    >
      <div
        className="w-2.5 h-2.5 rounded-sm shrink-0"
        style={{ backgroundColor: nodeDef.color }}
      />
      <span className="text-xs text-gray-700 truncate">{nodeDef.label}</span>
    </div>
  )
}
