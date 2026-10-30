import { createContext, useContext } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { post, request, jobKey } from './api';
import type {
  Analysis,
  Dataset,
  Job,
  Memory,
  PendingAction,
  RunSummary,
  Score,
  Task,
} from './types';
export const WorkspaceContext = createContext('');
export function useResource<T>(
  path: string,
  enabled = true,
  poll: boolean | number = false,
) {
  const scope = useContext(WorkspaceContext);
  return useQuery({
    queryKey: [scope, path],
    queryFn: ({ signal }) => request<T>(path, { signal }),
    enabled: enabled && Boolean(scope),
    staleTime: 10000,
    refetchInterval: typeof poll === 'number' ? poll : poll ? 2000 : false,
    retry: 1,
  });
}
export function useCatalog<T>(kind: string, page = 0) {
  return useResource<T[]>(`/api/v1/${kind}?limit=25&offset=${page * 25}`);
}
export const useDatasets = (page = 0) => useCatalog<Dataset>('datasets', page);
export const useTasks = () => useResource<Task[]>('/api/v1/tasks?limit=100');
export const useRuns = () => useCatalog<RunSummary>('runs');
export const useScores = () => useCatalog<Score>('scores');
export const useAnalyses = () => useCatalog<Analysis>('analyses');
export function useJobs(page = 0) {
  const scope = useContext(WorkspaceContext);
  return useQuery({
    queryKey: [scope, `/api/v1/jobs?limit=25&offset=${page * 25}`],
    queryFn: ({ signal }) =>
      request<Job[]>(`/api/v1/jobs?limit=25&offset=${page * 25}`, { signal }),
    refetchInterval: (query) =>
      query.state.data?.some(
        (j) => j.state === 'queued' || j.state === 'running',
      )
        ? 2000
        : 10000,
    enabled: Boolean(scope),
  });
}
export function useAction<T, V>(action: (value: V) => Promise<T>) {
  const client = useQueryClient();
  const scope = useContext(WorkspaceContext);
  return useMutation({
    mutationFn: action,
    onSuccess: () => client.invalidateQueries({ queryKey: [scope] }),
  });
}
export function useJobAction() {
  return useAction<Job, { kind: string; body: Record<string, unknown> }>(
    (input) =>
      post<Job>(`/api/v1/jobs/${input.kind}`, {
        ...input.body,
        idempotency_key: jobKey(),
      }),
  );
}
export const useMemory = () => useResource<Memory>('/api/v1/memory');
export const usePendingActions = () =>
  useResource<PendingAction[]>('/api/v1/actions?status=pending', true, 15000);
export interface WorkspaceIdentity {
  user_id: string;
  organization_id: string | null;
  role: 'owner' | 'admin' | 'member' | 'viewer';
  can_manage: boolean;
  can_edit: boolean;
}
export const useIdentity = () =>
  useResource<WorkspaceIdentity>('/api/v1/workspace/identity');
export const useReasons = (scoreId: string) =>
  useResource<import('./brief-ui').Reasons>(
    `/api/v1/scores/${scoreId}/reasons`,
    Boolean(scoreId),
  );
