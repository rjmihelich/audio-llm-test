/** Global keyboard shortcuts for the pipeline editor */

import { useEffect } from 'react'
import { useGraphStore } from './useGraphStore'

export function useKeyboardShortcuts(onSave: () => void) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isMod = e.metaKey || e.ctrlKey
      const target = e.target as HTMLElement
      const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT'

      // Ctrl+S — save
      if (isMod && e.key === 's') {
        e.preventDefault()
        onSave()
        return
      }

      // Ctrl+Z — undo
      if (isMod && e.key === 'z' && !e.shiftKey) {
        e.preventDefault()
        useGraphStore.getState().undo()
        return
      }

      // Ctrl+Shift+Z or Ctrl+Y — redo
      if ((isMod && e.key === 'z' && e.shiftKey) || (isMod && e.key === 'y')) {
        e.preventDefault()
        useGraphStore.getState().redo()
        return
      }

      // Ctrl+D — duplicate selected node
      if (isMod && e.key === 'd') {
        e.preventDefault()
        useGraphStore.getState().duplicateSelected()
        return
      }

      // Don't handle delete/backspace if we're in an input field
      if (isInput) return

      // Backspace / Delete — remove selected node
      if (e.key === 'Backspace' || e.key === 'Delete') {
        const { selectedNodeId, removeNode } = useGraphStore.getState()
        if (selectedNodeId) {
          e.preventDefault()
          removeNode(selectedNodeId)
        }
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onSave])
}
