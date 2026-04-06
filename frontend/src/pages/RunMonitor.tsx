import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getRun, cancelRun } from "../api/client";

interface WsMessage {
  type: string;
  test_case_id?: string;
  backend?: string;
  passed?: boolean;
  latency_ms?: number;
  error?: string;
  progress_pct?: number;
  completed_cases?: number;
  total_cases?: number;
}

export default function RunMonitor() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [logs, setLogs] = useState<WsMessage[]>([]);
  const [wsStatus, setWsStatus] = useState<"connecting" | "open" | "closed">(
    "connecting"
  );
  const logsEndRef = useRef<HTMLDivElement>(null);

  const run = useQuery({
    queryKey: ["run", id],
    queryFn: () => getRun(id!),
    refetchInterval: 5000,
    enabled: !!id,
  });

  const cancel = useMutation({
    mutationFn: () => cancelRun(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["run", id] }),
  });

  // WebSocket connection
  useEffect(() => {
    if (!id) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws/runs/${id}`);

    ws.onopen = () => setWsStatus("open");
    ws.onclose = () => setWsStatus("closed");
    ws.onerror = () => setWsStatus("closed");

    ws.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data);
        setLogs((prev) => [...prev.slice(-199), msg]);
        // Refresh run data on progress updates
        if (msg.type === "progress" || msg.type === "completed") {
          queryClient.invalidateQueries({ queryKey: ["run", id] });
        }
      } catch {
        // ignore parse errors
      }
    };

    return () => ws.close();
  }, [id, queryClient]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const data = run.data;
  const progress = data?.progress_pct ?? 0;
  const isRunning = data?.status === "running";

  // Compute per-backend stats from logs
  const backendStats = new Map<string, { count: number; totalLatency: number }>();
  logs
    .filter((l) => l.type === "result" && l.backend)
    .forEach((l) => {
      const key = l.backend!;
      const existing = backendStats.get(key) ?? { count: 0, totalLatency: 0 };
      existing.count++;
      existing.totalLatency += l.latency_ms ?? 0;
      backendStats.set(key, existing);
    });

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Run Monitor</h2>
          <p className="text-sm text-gray-500 mt-0.5 font-mono">
            {id?.slice(0, 12)}...
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`w-2 h-2 rounded-full ${
              wsStatus === "open"
                ? "bg-green-500"
                : wsStatus === "connecting"
                  ? "bg-yellow-500"
                  : "bg-gray-400"
            }`}
          />
          <span className="text-xs text-gray-500 capitalize">{wsStatus}</span>

          {isRunning && (
            <button
              onClick={() => cancel.mutate()}
              disabled={cancel.isPending}
              className="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
            >
              Cancel Run
            </button>
          )}

          {data?.status === "completed" && (
            <Link
              to={`/results/${id}`}
              className="px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 transition-colors"
            >
              View Results
            </Link>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-700">Progress</span>
          <span className="text-sm text-gray-500">
            {data?.completed_cases ?? 0} / {data?.total_cases ?? 0} cases
          </span>
        </div>
        <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-500 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="flex items-center justify-between mt-2">
          <span className="text-xs text-gray-500">
            {data?.failed_cases ?? 0} failed
          </span>
          <span className="text-sm font-semibold text-gray-900">
            {progress.toFixed(1)}%
          </span>
        </div>
      </div>

      {/* Per-backend throughput */}
      {backendStats.size > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {[...backendStats.entries()].map(([backend, stats]) => (
            <div
              key={backend}
              className="bg-white rounded-xl border border-gray-200 shadow-sm p-4"
            >
              <p className="text-xs font-medium text-gray-500 mb-1">
                {backend.replace(/_/g, " ")}
              </p>
              <p className="text-lg font-semibold text-gray-900">
                {stats.count} done
              </p>
              <p className="text-xs text-gray-400">
                avg {(stats.totalLatency / stats.count).toFixed(0)}ms
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Live logs */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-700">Live Results</h3>
        </div>
        <div className="max-h-96 overflow-y-auto">
          {logs.length === 0 && (
            <p className="px-6 py-8 text-center text-gray-400 text-sm">
              Waiting for results...
            </p>
          )}
          {logs.map((log, i) => (
            <div
              key={i}
              className="px-6 py-2 border-b border-gray-50 flex items-center gap-3 text-sm"
            >
              {log.type === "result" && (
                <>
                  <span
                    className={`w-2 h-2 rounded-full shrink-0 ${
                      log.passed ? "bg-green-500" : log.error ? "bg-red-500" : "bg-yellow-500"
                    }`}
                  />
                  <span className="text-gray-500 font-mono text-xs w-20 shrink-0">
                    {log.backend}
                  </span>
                  <span className="text-gray-600 truncate">
                    {log.test_case_id?.slice(0, 8)}
                  </span>
                  {log.latency_ms != null && (
                    <span className="ml-auto text-xs text-gray-400 tabular-nums shrink-0">
                      {log.latency_ms.toFixed(0)}ms
                    </span>
                  )}
                  {log.error && (
                    <span className="text-xs text-red-500 truncate max-w-xs">
                      {log.error}
                    </span>
                  )}
                </>
              )}
              {log.type === "progress" && (
                <span className="text-gray-500">
                  Progress: {log.completed_cases}/{log.total_cases} (
                  {log.progress_pct?.toFixed(1)}%)
                </span>
              )}
              {log.type === "completed" && (
                <span className="text-green-600 font-medium">
                  Run completed
                </span>
              )}
            </div>
          ))}
          <div ref={logsEndRef} />
        </div>
      </div>
    </div>
  );
}
