/** Pipeline Studio — embedded as a page within the main app */

import '@xyflow/react/dist/style.css'
import './pipeline-studio.css'
import { Component, type ReactNode } from 'react'
import { ReactFlowProvider } from '@xyflow/react'
import Canvas from './components/Canvas'
import NodePalette from './components/NodePalette'
import ConfigPanel from './components/ConfigPanel'
import Toolbar from './components/Toolbar'
import HistogramPopup from './components/HistogramPopup'
import { useNodeTypes } from './hooks/usePipelineApi'
import { useGraphStore } from './hooks/useGraphStore'

/** Error boundary to prevent white-screen crashes */
class PipelineErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex flex-col items-center justify-center h-full bg-gray-50 p-8">
          <div className="bg-white border border-red-200 rounded-lg shadow-sm p-6 max-w-md">
            <h2 className="text-sm font-bold text-red-600 mb-2">Pipeline Studio Error</h2>
            <p className="text-xs text-gray-600 mb-3">{this.state.error.message}</p>
            <pre className="text-[9px] text-gray-400 bg-gray-50 rounded p-2 mb-3 max-h-32 overflow-auto">
              {this.state.error.stack}
            </pre>
            <button
              onClick={() => {
                this.setState({ error: null })
                window.location.reload()
              }}
              className="px-3 py-1.5 bg-slate-700 text-white text-xs rounded hover:bg-slate-600"
            >
              Reload
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

const EMPTY_ARRAY: string[] = []

export default function PipelineStudio() {
  const { data: registry, isLoading } = useNodeTypes()
  const openHistograms = useGraphStore((s) => s.openHistograms ?? EMPTY_ARRAY)

  return (
    <PipelineErrorBoundary>
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

          {/* Floating histogram popups */}
          {openHistograms.map((nodeId) => (
            <HistogramPopup key={nodeId} nodeId={nodeId} />
          ))}
        </div>
      </ReactFlowProvider>
    </PipelineErrorBoundary>
  )
}
