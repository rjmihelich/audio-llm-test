/** React Query hooks for Pipeline API */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../api/client'
import { STATIC_REGISTRY } from '../utils/staticRegistry'

export function useNodeTypes() {
  return useQuery({
    queryKey: ['node-types'],
    queryFn: async () => {
      try {
        return await api.fetchNodeTypes()
      } catch {
        // Fallback to static registry when backend is unavailable
        return STATIC_REGISTRY
      }
    },
    staleTime: Infinity,
    retry: false,
  })
}

export function usePipelines(isTemplate?: boolean) {
  return useQuery({
    queryKey: ['pipelines', isTemplate],
    queryFn: () => api.listPipelines(isTemplate),
    staleTime: 30_000,
    retry: false,
    // Silently fail — callers use STATIC_TEMPLATES as fallback
    meta: { silent: true },
  })
}

export function usePipeline(id: string | null) {
  return useQuery({
    queryKey: ['pipeline', id],
    queryFn: () => api.getPipeline(id!),
    enabled: !!id,
  })
}

export function useCreatePipeline() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.createPipeline,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipelines'] }),
  })
}

export function useUpdatePipeline() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Parameters<typeof api.updatePipeline>[1]) =>
      api.updatePipeline(id, data),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      qc.invalidateQueries({ queryKey: ['pipeline', vars.id] })
    },
  })
}

export function useDeletePipeline() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.deletePipeline,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipelines'] }),
  })
}

export function useValidateGraph() {
  return useMutation({
    mutationFn: api.validateGraphInline,
  })
}

export function useExecutePreview() {
  return useMutation({
    mutationFn: api.executePreview,
  })
}
