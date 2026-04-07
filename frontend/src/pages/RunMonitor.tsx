import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getRun, cancelRun, queryResults, type ResultResponse } from "../api/client";

interface LogEntry {
  type: string;
  test_case_id?: string;
  backend?: string;
  passed?: boolean;
  score?: number;
  latency_ms?: number;
  error?: string;
  error_stage?: string;
  traceback?: string;
  message?: string;
  completed?: number;
  total?: number;
  pct?: number;
  summary?: Record<string, unknown>;
}

function stageLabel(stage: string | undefined): string {
  switch (stage) {
    case "audio_load": return "Audio Load";
    case "backend_init": return "Backend Init";
    case "pipeline_init": return "Pipeline Init";
    case "pipeline": return "Pipeline";
    case "evaluation": return "Evaluation";
    case "timeout": return "Timeout";
    case "asr_init": return "ASR Init";
    default: return stage ?? "Unknown";
  }
}

function stageColor(stage: string | undefined): string {
  switch (stage) {
    case "audio_load": return "bg-orange-100 text-orange-700";
    case "backend_init":
    case "asr_init": return "bg-purple-100 text-purple-700";
    case "pipeline":
    case "pipeline_init": return "bg-red-100 text-red-700";
    case "timeout": return "bg-yellow-100 text-yellow-800";
    case "evaluation": return "bg-amber-100 text-amber-700";
    default: return "bg-gray-100 text-gray-600";
  }
}

export default function RunMonitor() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [wsLogs, setWsLogs] = useState<LogEntry[]>([]);
  const [wsStatus, setWsStatus] = useState<"connecting" | "open" | "closed">("connecting");
  const [expandedError, setExpandedError] = useState<number | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const prevCountRef = useRef(0);

  // Poll run status
  const run = useQuery({
    queryKey: ["run", id],
    queryFn: () => getRun(id!),
    refetchInterval: 2000,
    enabled: !!id,
  });

  // Poll results from DB (works even without WebSocket)
  const polledResults = useQuery({
    queryKey: ["run-results-poll", id],
    queryFn: () => queryResults(id!, { limit: 500 }),
    refetchInterval: 3000,
    enabled: !!id,
  });

  const cancel = useMutation({
    mutationFn: () => cancelRun(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["run", id] }),
  });

  // WebSocket connection (best-effort, not required)
  useEffect(() => {
    if (!id) return;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws/runs/${id}`);

    ws.onopen = () => setWsStatus("open");
    ws.onclose = () => setWsStatus("closed");
    ws.onerror = () => setWsStatus("closed");

    ws.onmessage = (event) => {
      try {
        const msg: LogEntry = JSON.parse(event.data);
        if (msg.type === "heartbeat" || msg.type === "pong") return;
        setWsLogs((prev) => [...prev.slice(-499), msg]);
        if (msg.type === "progress" || msg.type === "completed" || msg.type === "error") {
          queryClient.invalidateQueries({ queryKey: ["run", id] });
        }
      } catch { /* ignore */ }
    };

    return () => ws.close();
  }, [id, queryClient]);

  // Auto-scroll when new results arrive
  const resultCount = polledResults.data?.length ?? 0;
  useEffect(() => {
    if (resultCount > prevCountRef.current) {
      logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
      prevCountRef.current = resultCount;
    }
  }, [resultCount]);

  // Also scroll for WS logs
  useEffect(() => {
    if (wsLogs.length > 0) {
      logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [wsLogs]);

  const data = run.data;
  const isRunning = data?.status === "running" || data?.status === "pending";
  const isFailed = data?.status === "failed";
  const isCompleted = data?.status === "completed";

  // Use polled results as the primary data source (works without WS)
  const results = polledResults.data ?? [];

  // Compute progress from actual data
  const totalCases = data?.total_cases ?? 0;
  const completedCases = data?.completed_cases ?? 0;
  const failedCases = data?.failed_cases ?? 0;
  const passedCases = completedCases - failedCases;
  const progress = totalCases > 0 ? (completedCases / totalCases) * 100 : 0;

  // Per-backend stats from polled results
  const backendStats = new Map<string, { count: number; passed: number; errors: number; totalLatency: number }>();
  results.forEach((r) => {
    const key = r.llm_backend || "unknown";
    const existing = backendStats.get(key) ?? { count: 0, passed: 0, errors: 0, totalLatency: 0 };
    existing.count++;
    if (r.eval_passed) existing.passed++;
    if (r.error) existing.errors++;
    existing.totalLatency += r.total_latency_ms ?? 0;
    backendStats.set(key, existing);
  });

  // Error breakdown by stage from polled results
  const errorsByStage = new Map<string, number>();
  results.filter(r => r.error).forEach((r) => {
    const stage = r.error_stage || "unknown";
    errorsByStage.set(stage, (errorsByStage.get(stage) ?? 0) + 1);
  });

  // Use WS logs for info messages, polled results for result rows
  const infoLogs = wsLogs.filter(l => l.type === "info" || l.type === "error");

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Run Monitor</h2>
          <p className="text-sm text-gray-500 mt-0.5 font-mono">{id?.slice(0, 12)}...</p>
        </div>
        <div className="flex items-center gap-3">
          {wsStatus === "open" && (
            <>
              <span className="w-2 h-2 rounded-full bg-green-500" />
              <span className="text-xs text-gray-500">Live</span>
            </>
          )}

          {isRunning && (
            <button
              onClick={() => cancel.mutate()}
              disabled={cancel.isPending}
              className="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
            >
              Cancel Run
            </button>
          )}

          {(isCompleted || isFailed) && (
            <Link
              to={`/results/${id}`}
              className="px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 transition-colors"
            >
              View Results
            </Link>
          )}
        </div>
      </div>

      {/* Run-level error banner */}
      {isFailed && data?.error_message && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-5 mb-6">
          <div className="flex items-start gap-3">
            <span className="text-red-500 text-lg shrink-0">&#x26A0;</span>
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-semibold text-red-800">Run Failed</h4>
              <p className="text-sm text-red-700 mt-1 font-mono break-all">{data.error_message}</p>
              {data.error_details && "traceback" in data.error_details && (
                <details className="mt-3">
                  <summary className="text-xs text-red-600 cursor-pointer hover:text-red-800 font-medium">Show traceback</summary>
                  <pre className="mt-2 text-[10px] text-red-700 bg-red-100 rounded p-3 overflow-x-auto whitespace-pre-wrap">
                    {String(data.error_details.traceback)}
                  </pre>
                </details>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Progress bar */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-700">Progress</span>
          <span className="text-sm text-gray-500">
            {completedCases.toLocaleString()} / {totalCases.toLocaleString()} cases
          </span>
        </div>
        <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              isFailed ? "bg-red-500" : isCompleted ? "bg-green-500" : "bg-blue-500"
            }`}
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
        <div className="flex items-center justify-between mt-2">
          <div className="flex gap-4">
            <span className="text-xs text-gray-500">
              <span className="font-medium text-green-600">{passedCases}</span> passed
            </span>
            <span className="text-xs text-gray-500">
              <span className="font-medium text-red-600">{failedCases}</span> failed
            </span>
            {isRunning && (
              <span className="text-xs text-blue-500 animate-pulse">Running...</span>
            )}
          </div>
          <span className="text-sm font-semibold text-gray-900">
            {progress.toFixed(1)}%
          </span>
        </div>
      </div>

      {/* Error breakdown by stage */}
      {errorsByStage.size > 0 && (
        <div className="bg-white rounded-xl border border-red-200 shadow-sm p-5 mb-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Error Breakdown</h3>
          <div className="flex flex-wrap gap-2">
            {[...errorsByStage.entries()].map(([stage, count]) => (
              <span key={stage} className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium ${stageColor(stage)}`}>
                {stageLabel(stage)}
                <span className="bg-white/50 px-1.5 py-0.5 rounded font-bold">{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Per-backend stats */}
      {backendStats.size > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {[...backendStats.entries()].map(([backend, stats]) => {
            const passRate = stats.count > 0 ? ((stats.passed / stats.count) * 100).toFixed(0) : "--";
            return (
              <div key={backend} className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
                <p className="text-xs font-medium text-gray-500 mb-1 truncate">{backend}</p>
                <div className="flex items-baseline gap-2">
                  <p className="text-lg font-semibold text-gray-900">{stats.count}</p>
                  <p className="text-xs text-gray-400">completed</p>
                </div>
                <div className="flex items-center gap-3 mt-1.5 text-xs">
                  <span className="text-green-600">{passRate}% pass</span>
                  {stats.errors > 0 && <span className="text-red-500">{stats.errors} errors</span>}
                  {stats.count - stats.errors > 0 && (
                    <span className="text-gray-400">
                      avg {(stats.totalLatency / (stats.count - stats.errors)).toFixed(0)}ms
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Info messages from WebSocket */}
      {infoLogs.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm mb-6">
          <div className="px-6 py-3 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-700">System Messages</h3>
          </div>
          <div className="max-h-32 overflow-y-auto divide-y divide-gray-50">
            {infoLogs.map((log, i) => (
              <div key={i} className={`px-5 py-2 text-xs ${log.type === "error" ? "text-red-600 bg-red-50/50" : "text-blue-600 bg-blue-50/30"}`}>
                {log.type === "error" ? `Error: ${log.error}` : log.message}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Results log (from polling) */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-700">Results</h3>
          <div className="flex gap-3 text-xs text-gray-400">
            <span>{results.length} results</span>
            {results.filter(r => r.error).length > 0 && (
              <span className="text-red-500">{results.filter(r => r.error).length} errors</span>
            )}
          </div>
        </div>
        <div className="max-h-[32rem] overflow-y-auto divide-y divide-gray-50">
          {results.length === 0 && (
            <p className="px-6 py-8 text-center text-gray-400 text-sm">
              {isRunning ? "Waiting for results..." : "No results yet."}
            </p>
          )}
          {results.map((r, i) => (
            <div key={r.test_case_id + i}>
              <div
                className={`px-5 py-2.5 flex items-center gap-3 text-sm ${
                  r.error ? "bg-red-50/30 cursor-pointer hover:bg-red-50" : "hover:bg-gray-50/50"
                }`}
                onClick={() => r.error ? setExpandedError(expandedError === i ? null : i) : undefined}
              >
                <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                  r.error ? "bg-red-500" : r.eval_passed ? "bg-green-500" : "bg-yellow-500"
                }`} />
                <span className="text-gray-400 font-mono text-[11px] w-28 shrink-0 truncate">
                  {r.llm_backend || "--"}
                </span>
                <span className="text-gray-500 font-mono text-xs w-16 shrink-0">
                  {r.test_case_id?.slice(0, 8)}
                </span>
                <span className="text-[10px] text-gray-400 w-10 shrink-0">
                  {r.snr_db != null ? `${r.snr_db}dB` : ""}
                </span>

                {r.error ? (
                  <>
                    {r.error_stage && (
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${stageColor(r.error_stage)}`}>
                        {stageLabel(r.error_stage)}
                      </span>
                    )}
                    <span className="text-xs text-red-600 truncate flex-1 min-w-0">
                      {r.error.length > 100 ? r.error.slice(0, 100) + "..." : r.error}
                    </span>
                  </>
                ) : (
                  <>
                    {r.eval_score != null && (
                      <span className="text-xs text-gray-500">
                        score: {(r.eval_score * 100).toFixed(0)}%
                      </span>
                    )}
                    {r.asr_transcript && (
                      <span className="text-[10px] text-gray-400 truncate max-w-[200px]" title={r.asr_transcript}>
                        "{r.asr_transcript.slice(0, 40)}{r.asr_transcript.length > 40 ? "..." : ""}"
                      </span>
                    )}
                    {r.total_latency_ms != null && (
                      <span className="ml-auto text-xs text-gray-400 tabular-nums shrink-0">
                        {r.total_latency_ms.toFixed(0)}ms
                      </span>
                    )}
                  </>
                )}
              </div>

              {/* Expanded error detail */}
              {r.error && expandedError === i && (
                <div className="px-5 py-3 bg-red-50 border-t border-red-100">
                  <p className="text-xs text-red-800 font-mono whitespace-pre-wrap break-all">{r.error}</p>
                  {r.original_text && (
                    <p className="text-xs text-gray-600 mt-2">Original: "{r.original_text}"</p>
                  )}
                </div>
              )}
            </div>
          ))}
          <div ref={logsEndRef} />
        </div>
      </div>
    </div>
  );
}
