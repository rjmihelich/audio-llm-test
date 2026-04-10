/** Pipeline Studio API client */

const BASE = '/api/pipelines'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PortDef {
  name: string
  type: 'audio' | 'text' | 'evaluation'
  required: boolean
  description: string
}

export interface ConfigFieldDef {
  name: string
  type: 'string' | 'number' | 'select' | 'slider' | 'boolean' | 'json'
  label: string
  default: unknown
  options?: { value: string; label: string }[]
  min?: number
  max?: number
  step?: number
  description: string
  multiline?: boolean
}

export interface NodeTypeDef {
  type_id: string
  label: string
  category: string
  description: string
  color: string
  dynamic_inputs: boolean
  inputs: PortDef[]
  outputs: PortDef[]
  config_fields: ConfigFieldDef[]
}

export interface NodeTypeRegistry {
  categories: Record<string, { label: string; color: string }>
  node_types: Record<string, NodeTypeDef>
}

export interface PipelineData {
  id: string
  name: string
  description: string | null
  graph_json: Record<string, unknown>
  is_template: boolean
  version: number
  created_at: string
  updated_at: string
}

export interface ValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status}: ${body}`)
  }
  return res.json()
}

export async function fetchNodeTypes(): Promise<NodeTypeRegistry> {
  return json(await fetch(`${BASE}/node-types`))
}

export async function listPipelines(isTemplate?: boolean): Promise<PipelineData[]> {
  const params = isTemplate !== undefined ? `?is_template=${isTemplate}` : ''
  return json(await fetch(`${BASE}${params}`))
}

export async function getPipeline(id: string): Promise<PipelineData> {
  return json(await fetch(`${BASE}/${id}`))
}

export async function createPipeline(data: {
  name: string
  description?: string
  graph_json: Record<string, unknown>
  is_template?: boolean
}): Promise<PipelineData> {
  return json(await fetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }))
}

export async function updatePipeline(id: string, data: {
  name?: string
  description?: string
  graph_json?: Record<string, unknown>
}): Promise<PipelineData> {
  return json(await fetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }))
}

export async function deletePipeline(id: string): Promise<void> {
  const res = await fetch(`${BASE}/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`)
}

export async function validatePipeline(id: string): Promise<ValidationResult> {
  return json(await fetch(`${BASE}/${id}/validate`, { method: 'POST' }))
}

export async function validateGraphInline(graph: Record<string, unknown>): Promise<ValidationResult> {
  return json(await fetch(`${BASE}/validate-graph`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(graph),
  }))
}

export async function executePreview(id: string): Promise<Record<string, unknown>> {
  return json(await fetch(`${BASE}/${id}/execute-preview`, { method: 'POST' }))
}

export async function executeInline(graphJson: Record<string, unknown>): Promise<Record<string, unknown>> {
  return json(await fetch(`${BASE}/execute-inline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ graph_json: graphJson }),
  }))
}
