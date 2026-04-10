/** Floating histogram popup — persists even when selecting other nodes */

import { useRef, useCallback, useState } from 'react'
import { useGraphStore } from '../hooks/useGraphStore'

interface HistogramPopupProps {
  nodeId: string
}

const EMPTY_DATA: string[] = []

/** Aggregate raw data into { label, count, color } buckets */
function computeHistogramBuckets(data: string[], mode: string, label0?: string, label1?: string) {
  if (mode === 'binary') {
    let count0 = 0
    let count1 = 0
    for (const v of data) {
      if (v.trim() === '0') count0++
      else count1++
    }
    return [
      { label: label0 || 'Pass', count: count0, color: '#22C55E' },
      { label: label1 || 'Fail', count: count1, color: '#EF4444' },
    ]
  }
  const counts: Record<string, number> = {}
  for (const v of data) {
    const key = v.trim() || '(empty)'
    counts[key] = (counts[key] || 0) + 1
  }
  const colors = ['#3B82F6', '#22C55E', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#14B8A6', '#F97316']
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([key, count], i) => ({ label: key, count, color: colors[i % colors.length] }))
}

export default function HistogramPopup({ nodeId }: HistogramPopupProps) {
  const data = useGraphStore((s) => s.histogramData?.[nodeId] ?? EMPTY_DATA)
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
  const label0 = String(config.bin_label_0 || 'Pass')
  const label1 = String(config.bin_label_1 || 'Fail')
  const updateNodeConfig = useGraphStore((s) => s.updateNodeConfig)
  const [editingBin, setEditingBin] = useState<string | null>(null)

  // Draggable state — persisted in store so positions survive save/load
  const savedPos = useGraphStore((s) => s.histogramPositions?.[nodeId])
  const setHistogramPosition = useGraphStore((s) => s.setHistogramPosition)
  const [pos, setPos] = useState(() => {
    if (savedPos) return savedPos
    // Stagger position based on how many are open, and persist it
    const idx = useGraphStore.getState().openHistograms.indexOf(nodeId)
    const initial = { x: 120 + Math.max(idx, 0) * 30, y: 100 + Math.max(idx, 0) * 30 }
    // Defer store update to avoid set-during-render
    setTimeout(() => useGraphStore.getState().setHistogramPosition(nodeId, initial), 0)
    return initial
  })
  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number; _lastPos?: { x: number; y: number } } | null>(null)
  const popupRef = useRef<HTMLDivElement>(null)

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
      const newPos = {
        x: dragRef.current.origX + (ev.clientX - dragRef.current.startX),
        y: dragRef.current.origY + (ev.clientY - dragRef.current.startY),
      }
      setPos(newPos)
      // Store ref to latest position for mouseUp
      dragRef.current._lastPos = newPos
    }

    const handleMouseUp = () => {
      // Persist final position to store for save/load
      const finalPos = dragRef.current?._lastPos
      if (finalPos) {
        setHistogramPosition(nodeId, finalPos)
      }
      dragRef.current = null
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }, [pos, nodeId, setHistogramPosition])

  // Aggregate into proper buckets
  const total = data.length
  const buckets = computeHistogramBuckets(data, mode, label0, label1)
  const maxCount = Math.max(1, ...buckets.map((b) => b.count))

  return (
    <div
      ref={popupRef}
      className="fixed bg-white rounded-lg shadow-xl border border-gray-200 z-50"
      style={{
        left: pos.x,
        top: pos.y,
        width: 300,
        minHeight: 140,
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
          {total > 0 && <span className="text-[9px] text-gray-400">({total})</span>}
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

      {/* Histogram bars */}
      <div className="p-4">
        {total === 0 ? (
          <div className="flex items-center justify-center min-h-[80px]">
            <span className="text-gray-300 italic text-[10px]">Press Play to collect data...</span>
          </div>
        ) : (
          <>
            {/* Vertical bar chart */}
            <div className="flex items-end gap-3 justify-center" style={{ height: 100 }}>
              {buckets.map((b) => {
                const heightPct = maxCount > 0 ? (b.count / maxCount) * 100 : 0
                const pct = total > 0 ? ((b.count / total) * 100).toFixed(0) : '0'
                return (
                  <div key={b.label} className="flex flex-col items-center" style={{ flex: 1, maxWidth: 80 }}>
                    <span className="text-[10px] font-bold text-gray-700 mb-1">{b.count}</span>
                    <div className="w-full flex items-end" style={{ height: 64 }}>
                      <div
                        className="w-full rounded-t transition-all duration-500"
                        style={{
                          height: `${Math.max(heightPct, 3)}%`,
                          backgroundColor: b.color,
                        }}
                      />
                    </div>
                    {mode === 'binary' && editingBin === b.label ? (
                      <input
                        autoFocus
                        className="text-[9px] font-semibold mt-1 w-full text-center border-b border-gray-300 outline-none bg-transparent"
                        style={{ color: b.color }}
                        defaultValue={b.label}
                        onBlur={(e) => {
                          const val = e.target.value.trim() || b.label
                          const key = b === buckets[0] ? 'bin_label_0' : 'bin_label_1'
                          updateNodeConfig(nodeId, { [key]: val })
                          setEditingBin(null)
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                        }}
                      />
                    ) : (
                      <span
                        className="text-[9px] font-semibold mt-1 cursor-pointer hover:underline"
                        style={{ color: b.color }}
                        onClick={() => mode === 'binary' && setEditingBin(b.label)}
                        title="Click to rename"
                      >{b.label}</span>
                    )}
                    <span className="text-[8px] text-gray-400">{pct}%</span>
                  </div>
                )
              })}
            </div>
            <p className="text-[9px] text-gray-300 mt-2 text-center">{total} samples</p>
          </>
        )}
      </div>
    </div>
  )
}
