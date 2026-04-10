/** Pipeline Studio — embedded as a page within the main app */

import '@xyflow/react/dist/style.css'
import './pipeline-studio.css'
import { ReactFlowProvider } from '@xyflow/react'
import Canvas from './components/Canvas'
import NodePalette from './components/NodePalette'
import ConfigPanel from './components/ConfigPanel'
import Toolbar from './components/Toolbar'
import { useNodeTypes } from './hooks/usePipelineApi'

export default function PipelineStudio() {
  const { data: registry, isLoading } = useNodeTypes()

  return (
    <ReactFlowProvider>
      <div className="flex flex-col h-full bg-gray-50">
        {/* Top toolbar */}
        <Toolbar registry={registry} />

        {/* Main content: palette | canvas | config */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left: block palette */}
          <NodePalette registry={registry} isLoading={isLoading} />

          {/* Center: React Flow canvas */}
          <Canvas registry={registry} />

          {/* Right: config panel */}
          <ConfigPanel registry={registry} />
        </div>
      </div>
    </ReactFlowProvider>
  )
}
