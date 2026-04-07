/** Custom edge colored by port type, dashed for feedback, with animated flow */

import { type EdgeProps, getSmoothStepPath } from '@xyflow/react'
import { PORT_COLORS, portTypeFromHandle, type PortType } from '../utils/portTypes'

export default function TypedEdge({
  id,
  sourceX, sourceY,
  targetX, targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}: EdgeProps) {
  const isFeedback = data?.edge_type === 'feedback'

  // Determine color from source handle name
  const sourceHandle = (data as Record<string, unknown>)?.sourceHandle as string | undefined
  const portType = sourceHandle ? portTypeFromHandle(sourceHandle) : 'audio'
  const color = PORT_COLORS[portType as PortType] || PORT_COLORS.audio

  const [edgePath] = getSmoothStepPath({
    sourceX, sourceY,
    targetX, targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 16,
  })

  return (
    <>
      {/* Invisible wider path for easier click target */}
      <path
        id={id}
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        className="react-flow__edge-interaction"
      />
      {/* Visible edge */}
      <path
        d={edgePath}
        fill="none"
        stroke={selected ? '#3B82F6' : color}
        strokeWidth={selected ? 2.5 : 2}
        strokeDasharray={isFeedback ? '8 4' : undefined}
        strokeLinecap="round"
        className="react-flow__edge-path"
        style={{ filter: selected ? 'drop-shadow(0 0 3px rgba(59,130,246,0.5))' : undefined }}
      />
      {/* Animated flow dot */}
      {!isFeedback && (
        <circle r={3} fill={color} opacity={0.7}>
          <animateMotion dur="2s" repeatCount="indefinite" path={edgePath} />
        </circle>
      )}
      {/* Feedback icon */}
      {isFeedback && (
        <circle r={3} fill="#F97316" opacity={0.8}>
          <animateMotion dur="3s" repeatCount="indefinite" path={edgePath} />
        </circle>
      )}
    </>
  )
}
