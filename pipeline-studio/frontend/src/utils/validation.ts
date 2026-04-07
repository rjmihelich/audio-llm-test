/** Client-side graph validation — mirrors backend validation rules */

import type { ValidationResult, NodeTypeRegistry } from '../api/client'

interface GraphNode {
  id: string
  type?: string
  data?: Record<string, unknown>
}

interface GraphEdge {
  id: string
  source: string
  sourceHandle?: string
  target: string
  targetHandle?: string
  data?: { edge_type?: string }
}

interface GraphJson {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export function validateGraph(graph: GraphJson, registry: NodeTypeRegistry): ValidationResult {
  const errors: string[] = []
  const warnings: string[] = []
  const { nodes, edges } = graph

  if (nodes.length === 0) {
    errors.push('Graph has no nodes')
    return { valid: false, errors, warnings }
  }

  // Build lookup maps
  const nodeMap = new Map(nodes.map(n => [n.id, n]))
  const nodeTypeId = (n: GraphNode) => (n.data?.type_id as string) || n.type || ''

  // 1. Check all node types are known
  for (const n of nodes) {
    const tid = nodeTypeId(n)
    if (!registry.node_types[tid]) {
      errors.push(`Unknown node type "${tid}" on node ${n.id}`)
    }
  }

  // 2. Check edge endpoints exist
  for (const e of edges) {
    if (!nodeMap.has(e.source)) {
      errors.push(`Edge ${e.id}: source node "${e.source}" not found`)
    }
    if (!nodeMap.has(e.target)) {
      errors.push(`Edge ${e.id}: target node "${e.target}" not found`)
    }
  }

  // 3. Check port type compatibility
  for (const e of edges) {
    const srcNode = nodeMap.get(e.source)
    const tgtNode = nodeMap.get(e.target)
    if (!srcNode || !tgtNode) continue

    const srcDef = registry.node_types[nodeTypeId(srcNode)]
    const tgtDef = registry.node_types[nodeTypeId(tgtNode)]
    if (!srcDef || !tgtDef) continue

    const srcPort = srcDef.outputs.find(p => p.name === e.sourceHandle)
    // For dynamic inputs (mixer), handle audio_in_N → treat as audio
    let tgtPort = tgtDef.inputs.find(p => p.name === e.targetHandle)
    if (!tgtPort && e.targetHandle?.startsWith('audio_in_') && tgtDef.dynamic_inputs) {
      tgtPort = { name: e.targetHandle, type: 'audio', required: false, description: '' }
    }

    if (srcPort && tgtPort && srcPort.type !== tgtPort.type) {
      errors.push(`Type mismatch on edge ${e.id}: ${srcPort.type} → ${tgtPort.type}`)
    }
  }

  // 4. Cycle detection (excluding feedback edges)
  const forwardEdges = edges.filter(e => e.data?.edge_type !== 'feedback')
  const adj = new Map<string, string[]>()
  const inDegree = new Map<string, number>()
  for (const n of nodes) {
    adj.set(n.id, [])
    inDegree.set(n.id, 0)
  }
  for (const e of forwardEdges) {
    if (adj.has(e.source) && inDegree.has(e.target)) {
      adj.get(e.source)!.push(e.target)
      inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1)
    }
  }
  // Kahn's algorithm
  const queue = [...inDegree.entries()].filter(([, d]) => d === 0).map(([id]) => id)
  let visited = 0
  while (queue.length > 0) {
    const n = queue.shift()!
    visited++
    for (const neighbor of adj.get(n) || []) {
      const d = (inDegree.get(neighbor) || 1) - 1
      inDegree.set(neighbor, d)
      if (d === 0) queue.push(neighbor)
    }
  }
  if (visited < nodes.length) {
    errors.push('Graph contains a cycle in forward (non-feedback) edges')
  }

  // 5. Check at least one source and one sink
  const sourceTypes = new Set(['speech_source', 'noise_generator', 'audio_file'])
  const sinkTypes = new Set(['text_output', 'audio_output', 'eval_output'])

  const hasSources = nodes.some(n => sourceTypes.has(nodeTypeId(n)))
  const hasSinks = nodes.some(n => sinkTypes.has(nodeTypeId(n)) || nodeTypeId(n) === 'eval_analysis')

  if (!hasSources) {
    warnings.push('No source nodes (speech, noise, audio file) in graph')
  }
  if (!hasSinks) {
    warnings.push('No output or evaluation nodes in graph')
  }

  // 6. Check required inputs have connections
  for (const n of nodes) {
    const def = registry.node_types[nodeTypeId(n)]
    if (!def) continue

    for (const input of def.inputs) {
      if (!input.required) continue
      const hasConnection = edges.some(
        e => e.target === n.id && (e.targetHandle === input.name ||
          (input.name.startsWith('audio_in') && e.targetHandle?.startsWith('audio_in')))
      )
      if (!hasConnection) {
        warnings.push(`${def.label} "${n.id}": required input "${input.name}" has no connection`)
      }
    }
  }

  return { valid: errors.length === 0, errors, warnings }
}
