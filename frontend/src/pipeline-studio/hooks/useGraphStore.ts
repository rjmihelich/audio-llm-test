/** Zustand store for pipeline editor graph state — with undo/redo history */

import { create } from 'zustand'
import {
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type OnConnect,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
  type Connection,
} from '@xyflow/react'

interface Snapshot {
  nodes: Node[]
  edges: Edge[]
}

export interface ModelStatus {
  status: 'loading' | 'ready' | 'error'
  model?: string
  loadTimeMs?: number
  error?: string
}

interface GraphState {
  nodes: Node[]
  edges: Edge[]
  selectedNodeId: string | null
  pipelineId: string | null
  pipelineName: string
  isDirty: boolean

  // Per-node output logs (text_output nodes get their own log)
  outputLogs: Record<string, string[]>
  appendOutputLog: (nodeId: string, text: string) => void
  clearOutputLog: (nodeId: string) => void
  clearAllOutputLogs: () => void

  // Per-node live state from pipeline execution
  routerStates: Record<string, number>
  evalStates: Record<string, { passed: boolean; score: number }>
  histogramData: Record<string, string[]>
  setRouterStates: (states: Record<string, number>) => void
  setEvalStates: (states: Record<string, { passed: boolean; score: number }>) => void
  appendHistogramValue: (nodeId: string, value: string) => void
  clearHistogramData: (nodeId: string) => void
  clearAllLiveState: () => void

  // Floating histogram popups (node IDs that are open)
  openHistograms: string[]
  toggleHistogram: (nodeId: string) => void
  closeHistogram: (nodeId: string) => void

  // Model warmup status per node ID
  modelStatus: Record<string, ModelStatus>
  setModelStatus: (nodeId: string, status: ModelStatus) => void
  clearModelStatus: (nodeId: string) => void

  // History
  _past: Snapshot[]
  _future: Snapshot[]
  _pushHistory: () => void
  undo: () => void
  redo: () => void
  canUndo: () => boolean
  canRedo: () => boolean

  // Actions
  setNodes: (nodes: Node[]) => void
  setEdges: (edges: Edge[]) => void
  onNodesChange: OnNodesChange
  onEdgesChange: OnEdgesChange
  onConnect: OnConnect
  addNode: (node: Node) => void
  removeNode: (id: string) => void
  removeEdges: (ids: string[]) => void
  updateNodeConfig: (nodeId: string, config: Record<string, unknown>) => void
  selectNode: (id: string | null) => void
  duplicateSelected: () => void
  setPipeline: (id: string | null, name: string, nodes: Node[], edges: Edge[]) => void
  setDirty: (dirty: boolean) => void
  clear: () => void
}

const MAX_HISTORY = 50

export const useGraphStore = create<GraphState>((set, get) => ({
  nodes: [],
  edges: [],
  selectedNodeId: null,
  pipelineId: null,
  pipelineName: 'Untitled Pipeline',
  isDirty: false,

  outputLogs: {},
  appendOutputLog: (nodeId, text) => set((s) => ({
    outputLogs: {
      ...s.outputLogs,
      [nodeId]: [...(s.outputLogs[nodeId] || []).slice(-199), text],
    },
  })),
  clearOutputLog: (nodeId) => set((s) => {
    const { [nodeId]: _, ...rest } = s.outputLogs
    return { outputLogs: { ...rest, [nodeId]: [] } }
  }),
  clearAllOutputLogs: () => set({ outputLogs: {} }),

  routerStates: {},
  evalStates: {},
  histogramData: {},
  setRouterStates: (states) => set({ routerStates: states }),
  setEvalStates: (states) => set({ evalStates: states }),
  appendHistogramValue: (nodeId, value) => set((s) => ({
    histogramData: {
      ...s.histogramData,
      [nodeId]: [...(s.histogramData[nodeId] || []).slice(-199), value],
    },
  })),
  clearHistogramData: (nodeId) => set((s) => ({
    histogramData: { ...s.histogramData, [nodeId]: [] },
  })),
  clearAllLiveState: () => set({
    outputLogs: {},
    routerStates: {},
    evalStates: {},
    histogramData: {},
  }),

  openHistograms: [],
  toggleHistogram: (nodeId) => set((s) => ({
    openHistograms: s.openHistograms.includes(nodeId)
      ? s.openHistograms.filter((id) => id !== nodeId)
      : [...s.openHistograms, nodeId],
  })),
  closeHistogram: (nodeId) => set((s) => ({
    openHistograms: s.openHistograms.filter((id) => id !== nodeId),
  })),

  modelStatus: {},
  setModelStatus: (nodeId, status) => set((s) => ({
    modelStatus: { ...s.modelStatus, [nodeId]: status },
  })),
  clearModelStatus: (nodeId) => set((s) => {
    const { [nodeId]: _, ...rest } = s.modelStatus
    return { modelStatus: rest }
  }),

  _past: [],
  _future: [],

  _pushHistory: () => {
    const { nodes, edges, _past } = get()
    const snapshot: Snapshot = {
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
    }
    set({
      _past: [..._past.slice(-MAX_HISTORY), snapshot],
      _future: [],
    })
  },

  undo: () => {
    const { _past, nodes, edges } = get()
    if (_past.length === 0) return
    const prev = _past[_past.length - 1]
    const currentSnapshot: Snapshot = {
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
    }
    set({
      nodes: prev.nodes,
      edges: prev.edges,
      _past: _past.slice(0, -1),
      _future: [currentSnapshot, ...get()._future],
      isDirty: true,
    })
  },

  redo: () => {
    const { _future, nodes, edges } = get()
    if (_future.length === 0) return
    const next = _future[0]
    const currentSnapshot: Snapshot = {
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
    }
    set({
      nodes: next.nodes,
      edges: next.edges,
      _past: [...get()._past, currentSnapshot],
      _future: _future.slice(1),
      isDirty: true,
    })
  },

  canUndo: () => get()._past.length > 0,
  canRedo: () => get()._future.length > 0,

  setNodes: (nodes) => {
    get()._pushHistory()
    set({ nodes, isDirty: true })
  },
  setEdges: (edges) => {
    get()._pushHistory()
    set({ edges, isDirty: true })
  },

  onNodesChange: (changes) => {
    // Only push history for structural changes (add/remove), not position/select
    const isStructural = changes.some(c => c.type === 'remove' || c.type === 'add')
    if (isStructural) get()._pushHistory()

    set({
      nodes: applyNodeChanges(changes, get().nodes),
      isDirty: true,
    })
    // Track selection
    for (const change of changes) {
      if (change.type === 'select' && change.selected) {
        set({ selectedNodeId: change.id })
      }
    }
  },

  onEdgesChange: (changes) => {
    const isStructural = changes.some(c => c.type === 'remove' || c.type === 'add')
    if (isStructural) get()._pushHistory()

    set({
      edges: applyEdgeChanges(changes, get().edges),
      isDirty: true,
    })
  },

  onConnect: (connection: Connection) => {
    get()._pushHistory()
    const edge: Edge = {
      ...connection,
      id: `e_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      type: 'typed',
      data: { edge_type: 'normal', sourceHandle: connection.sourceHandle },
    } as Edge
    set({
      edges: addEdge(edge, get().edges),
      isDirty: true,
    })
  },

  addNode: (node) => {
    get()._pushHistory()
    set((s) => ({
      nodes: [...s.nodes, node],
      isDirty: true,
    }))
  },

  removeNode: (id) => {
    get()._pushHistory()
    set((s) => ({
      nodes: s.nodes.filter((n) => n.id !== id),
      edges: s.edges.filter((e) => e.source !== id && e.target !== id),
      selectedNodeId: s.selectedNodeId === id ? null : s.selectedNodeId,
      isDirty: true,
    }))
  },

  removeEdges: (ids) => {
    get()._pushHistory()
    const idSet = new Set(ids)
    set((s) => ({
      edges: s.edges.filter((e) => !idSet.has(e.id)),
      isDirty: true,
    }))
  },

  updateNodeConfig: (nodeId, config) => set((s) => ({
    nodes: s.nodes.map((n) =>
      n.id === nodeId
        ? { ...n, data: { ...n.data, config: { ...((n.data as Record<string, unknown>).config as Record<string, unknown> || {}), ...config } } }
        : n
    ),
    isDirty: true,
  })),

  selectNode: (id) => set({ selectedNodeId: id }),

  duplicateSelected: () => {
    const { selectedNodeId, nodes } = get()
    if (!selectedNodeId) return
    const node = nodes.find(n => n.id === selectedNodeId)
    if (!node) return

    get()._pushHistory()
    const newId = `${node.type}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
    const newNode: Node = {
      ...node,
      id: newId,
      position: { x: node.position.x + 40, y: node.position.y + 40 },
      selected: false,
      data: JSON.parse(JSON.stringify(node.data)),
    }
    set((s) => ({
      nodes: [...s.nodes, newNode],
      selectedNodeId: newId,
      isDirty: true,
    }))
  },

  setPipeline: (id, name, nodes, edges) => set({
    pipelineId: id,
    pipelineName: name,
    nodes,
    edges,
    isDirty: false,
    selectedNodeId: null,
    _past: [],
    _future: [],
  }),

  setDirty: (dirty) => set({ isDirty: dirty }),

  clear: () => set({
    nodes: [],
    edges: [],
    selectedNodeId: null,
    pipelineId: null,
    pipelineName: 'Untitled Pipeline',
    isDirty: false,
    _past: [],
    _future: [],
  }),
}))
