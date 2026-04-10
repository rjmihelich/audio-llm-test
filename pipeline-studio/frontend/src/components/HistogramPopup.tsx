/** Floating histogram popup — persists even when selecting other nodes */

import { useRef, useCallback, useState, useEffect } from 'react'
import { useGraphStore } from '../hooks/useGraphStore'

interface HistogramPopupProps {
  nodeId: string
}

export default function HistogramPopup({ nodeId }: HistogramPopupProps) {
  const data = useGraphStore((s) => s.histogramData[nodeId] || [])
  const clearData = useGraphStore((s) => s.clearHistogramData)
  const closeHistogram = useGraphStore((s) => s.closeHistogram)
  const nodes = useGraphStore((s) => s.nodes)

  const node = nodes.find((n) => n.id === nodeId)
  const nodeLabel = node
    ? (node.data as Record<string, unknown>).label as string || 'Histogram'
    : 'Histogram'
  const config = node
    ? ((node.data as Record<string, unknown>).config as Record<string, unknown>) || {}
    : {}
  const mode = String(config.mode || 'binary')

  // Draggable state
  const [pos, setPos] = useState({ x: 100, y: 100 })
  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null)
  const popupRef = useRef<HTMLDivElement>(null)

  // Stagger position based on how many are open (set once on mount)
  useEffect(() => {
    const openHistograms = useGraphStore.getState().openHistograms
    const idx = openHistograms.indexOf(nodeId)
    if (idx >= 0) {
      setPos({ x: 120 + idx * 30, y: 100 + idx * 30 })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origX: pos.x,
      origY: pos.y,
    }

    const handleMouseMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      setPos({
        x: dragRef.current.origX + (ev.clientX - dragRef.current.startX),
        y: dragRef.current.origY + (ev.clientY - dragRef.current.startY),
      })
    }

    const handleMouseUp = () => {
      dragRef.current = null
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }, [pos])

  // Compute bucket counts
  const counts: Record<string, number> = {}
  for (const v of data) {
    const key = v || '(empty)'
    counts[key] = (counts[key] || 0) + 1
  }

  if (mode === 'binary') {
    if (!counts['0']) counts['0'] = 0
    if (!counts['1']) counts['1'] = 0
  }

  const sortedKeys = Object.keys(counts).sort()
  const maxCount = Math.max(1, ...Object.values(counts))
  const total = data.length

  const barColor = (key: string) => {
    if (mode === 'binary') return key === '0' ? '#22C55E' : '#EF4444'
    const colors = ['#3B82F6', '#22C55E', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#14B8A6', '#F97316']
    const idx = sortedKeys.indexOf(key) % colors.length
    return colors[idx]
  }

  const barLabel = (key: string) => {
    if (mode === 'binary') return key === '0' ? 'Pass' : 'Fail'
    return key
  }

  return (
    <div
      ref={popupRef}
      className="fixed bg-white rounded-lg shadow-xl border border-gray-200 z-50"
      style={{
        left: pos.x,
        top: pos.y,
        width: 280,
        minHeight: 120,
      }}
    >
      {/* Draggable title bar */}
      <div
        onMouseDown={handleMouseDown}
        className="flex items-center justify-between px-3 py-2 bg-gray-50 rounded-t-lg border-b border-gray-200 cursor-move select-none"
      >
        <div className="flex items-center gap-2">
          <svg className="w-3.5 h-3.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <span className="text-xs font-bold text-gray-700">{nodeLabel}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {total > 0 && (
            <button
              onClick={() => clearData(nodeId)}
              className="text-[9px] text-gray-400 hover:text-red-500 px-1"
              title="Clear histogram data"
            >
              Clear
            </button>
          )}
          <button
            onClick={() => closeHistogram(nodeId)}
            className="text-gray-400 hover:text-red-500 transition-colors"
            title="Close histogram"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Histogram content */}
      <div className="p-3">
        {total === 0 ? (
          <div className="flex items-center justify-center min-h-[60px]">
            <span className="text-gray-300 italic text-[10px]">Press Play to collect data...</span>
          </div>
        ) : (
          <div className="space-y-2">
            {sortedKeys.map((key) => {
              const count = counts[key]
              const pct = total > 0 ? (count / total) * 100 : 0
              return (
                <div key={key}>
                  <div className="flex items-center justify-between text-[10px] mb-0.5">
                    <span className="font-medium text-gray-600">{barLabel(key)}</span>
                    <span className="text-gray-400">{count} ({pct.toFixed(0)}%)</span>
                  </div>
                  <div className="h-5 bg-gray-100 rounded overflow-hidden">
                    <div
                      className="h-full rounded transition-all duration-300"
                      style={{
                        width: `${(count / maxCount) * 100}%`,
                        backgroundColor: barColor(key),
                      }}
                    />
                  </div>
                </div>
              )
            })}
            <p className="text-[9px] text-gray-300 mt-1">{total} samples</p>
          </div>
        )}
      </div>
    </div>
  )
}
