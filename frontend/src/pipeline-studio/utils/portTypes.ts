/** Port type definitions, colors, and compatibility */

export type PortType = 'audio' | 'text' | 'evaluation'

export const PORT_COLORS: Record<PortType, string> = {
  audio: '#3B82F6',
  text: '#22C55E',
  evaluation: '#F97316',
}

export const PORT_LABELS: Record<PortType, string> = {
  audio: 'Audio',
  text: 'Text',
  evaluation: 'Eval',
}

export function portTypeFromHandle(handleId: string): PortType {
  if (handleId.startsWith('audio') || handleId === 'mic_in' || handleId === 'speaker_in') return 'audio'
  if (handleId.startsWith('text') || handleId === 'control' || handleId === 'value_in') return 'text'
  if (handleId.startsWith('eval')) return 'evaluation'
  return 'audio'
}

export function arePortsCompatible(sourceHandle: string, targetHandle: string): boolean {
  return portTypeFromHandle(sourceHandle) === portTypeFromHandle(targetHandle)
}

export function getHandleClassName(portType: PortType): string {
  return `handle-${portType}`
}
