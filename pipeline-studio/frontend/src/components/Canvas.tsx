/** React Flow canvas wrapper with drag-and-drop support */

import { useCallback, useRef, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type IsValidConnection,
  type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import nodeTypes from '../nodes/nodeTypes'
import TypedEdge from './TypedEdge'
import { useGraphStore } from '../hooks/useGraphStore'
import { arePortsCompatible } from '../utils/portTypes'
import type { NodeTypeRegistry } from '../api/client'

const edgeTypes = { typed: TypedEdge }

interface CanvasProps {
  registry: NodeTypeRegistry | undefined
}

export default function Canvas({ registry }: CanvasProps) {
  const {
    nodes, edges,
    onNodesChange, onEdgesChange, onConnect,
    addNode, selectNode, removeEdges, toggleHistogram,
  } = useGraphStore()

  const reactFlowRef = useRef<ReactFlowInstance | null>(null)

  // Validate connections: only allow compatible port types
  const isValidConnection: IsValidConnection = useCallback((connection) => {
    if (!connection.sourceHandle || !connection.targetHandle) return false
    return arePortsCompatible(connection.sourceHandle, connection.targetHandle)
  }, [])

  // Handle drop from palette
  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const typeId = e.dataTransfer.getData('application/pipeline-node-type')
    if (!typeId || !registry) return

    const nodeDef = registry.node_types[typeId]
    if (!nodeDef) return

    const rfInstance = reactFlowRef.current
    if (!rfInstance) return

    const position = rfInstance.screenToFlowPosition({
      x: e.clientX,
      y: e.clientY,
    })

    // Build default config from field defaults
    const config: Record<string, unknown> = {}
    for (const field of nodeDef.config_fields) {
      config[field.name] = field.default
    }

    const newNode = {
      id: `${typeId}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      type: typeId,
      position,
      data: {
        type_id: typeId,
        label: nodeDef.label,
        config,
        nodeDef,
      },
    }

    addNode(newNode)
  }, [registry, addNode])

  // Inject nodeDef into existing nodes that don't have it
  const enrichedNodes = useMemo(() => nodes.map((n) => {
    const d = n.data as Record<string, unknown>
    if (!d.nodeDef && registry) {
      const typeId = (d.type_id as string) || n.type || ''
      const nodeDef = registry.node_types[typeId]
      if (nodeDef) {
        return { ...n, data: { ...d, nodeDef } }
      }
    }
    return n
  }), [nodes, registry])

  // Enrich edges: set type to 'typed' and inject sourceHandle into data
  const enrichedEdges = useMemo(() => edges.map((e) => ({
    ...e,
    type: 'typed',
    data: {
      ...(e.data || {}),
      edge_type: (e.data as Record<string, unknown>)?.edge_type || 'normal',
      sourceHandle: e.sourceHandle,
    },
  })), [edges])

  // Default edge options
  const defaultEdgeOptions = useMemo(() => ({
    type: 'typed' as const,
  }), [])

  return (
    <div className="flex-1 h-full">
      <ReactFlow
        nodes={enrichedNodes}
        edges={enrichedEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onInit={(instance) => { reactFlowRef.current = instance }}
        onNodeClick={(_event, node) => selectNode(node.id)}
        onNodeDoubleClick={(_event, node) => {
          const d = node.data as Record<string, unknown>
          if (d.type_id === 'histogram') {
            toggleHistogram(node.id)
          }
        }}
        onPaneClick={() => selectNode(null)}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        isValidConnection={isValidConnection}
        onDragOver={onDragOver}
        onDrop={onDrop}
        fitView
        fitViewOptions={{ padding: 0.5 }}
        defaultViewport={{ x: 0, y: 0, zoom: 0.65 }}
        minZoom={0.1}
        maxZoom={2}
        snapToGrid
        snapGrid={[20, 20]}
        deleteKeyCode={['Backspace', 'Delete']}
        onEdgesDelete={(edges) => removeEdges(edges.map(e => e.id))}
        multiSelectionKeyCode="Shift"
      >
        <Background gap={20} size={1} />
        <Controls />
        <MiniMap
          nodeColor={(n) => {
            const d = n.data as Record<string, unknown>
            const nodeDef = d?.nodeDef as { color?: string } | undefined
            return nodeDef?.color || '#94A3B8'
          }}
          maskColor="rgba(0,0,0,0.1)"
        />
      </ReactFlow>
    </div>
  )
}
