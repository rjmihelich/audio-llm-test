import { useEffect, useRef, useState, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getRun,
  cancelRun,
  queryResults,
  fetchSystemHealth,
  getAudioUrl,
  type ResultResponse,
  type HealthResponse,
} from "../api/client";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

function formatDuration(ms: number): string {
  if (ms < 0) return "--";
  const totalSec = Math.floor(ms / 1000);
  const hours = Math.floor(totalSec / 3600);
  const mins = Math.floor((totalSec % 3600) / 60);
  const secs = totalSec % 60;
  if (hours > 0) return `${hours}h ${mins}m ${secs}s`;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

function formatTimeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return "--";
  const diff = Date.now() - new Date(dateStr).getTime();
  if (diff < 0) return "just now";
  const secs = Math.floor(diff / 1000);
  if (secs < 10) return "just now";
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ${mins % 60}m ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

/** Percent bar helper */
function MeterBar({ value, max, color, label }: { value: number; max: number; color: string; label: string }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-gray-400 w-10 shrink-0 text-right">{label}</span>
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-gray-500 w-10 tabular-nums">{pct.toFixed(0)}%</span>
    </div>
  );
}

/** Throughput history for mini sparkline */
interface ThroughputSample {
  ts: number;
  count: number;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function RunMonitor() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [expandedError, setExpandedError] = useState<number | null>(null);
  const [showWorkerLog, setShowWorkerLog] = useState(false);
  const [playingAudio, setPlayingAudio] = useState<string | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const prevCountRef = useRef(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Throughput tracking (client-side)
  const throughputRef = useRef<ThroughputSample[]>([]);
  const [throughput, setThroughput] = useState({ perMin: 0, perHour: 0 });
  const [lastActivityTs, setLastActivityTs] = useState<number>(Date.now());
  const [stalled, setStalled] = useState(false);

  // Tick every 5s to update "time ago" displays
  const [, setTick] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 5000);
    return () => clearInterval(interval);
  }, []);

  // Poll run status
  const run = useQuery({
    queryKey: ["run", id],
    queryFn: () => getRun(id!),
    refetchInterval: 3000,
    enabled: !!id,
  });

  // Poll results from DB
  const polledResults = useQuery({
    queryKey: ["run-results-poll", id],
    queryFn: () => queryResults(id!, { limit: 500 }),
    refetchInterval: 3000,
    enabled: !!id,
  });

  // Poll system health
  const health = useQuery({
    queryKey: ["system-health"],
    queryFn: fetchSystemHealth,
    refetchInterval: 5000,
  });

  const cancel = useMutation({
    mutationFn: () => cancelRun(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["run", id] }),
  });

  // Track throughput from completed_cases changes
  const completedCases = run.data?.completed_cases ?? 0;
  useEffect(() => {
    const now = Date.now();
    const samples = throughputRef.current;

    if (samples.length === 0 || samples[samples.length - 1].count !== completedCases) {
      samples.push({ ts: now, count: completedCases });
      setLastActivityTs(now);
      setStalled(false);
      if (samples.length > 200) samples.shift();
    }

    // Rate over last 2 min window
    const cutoff = now - 2 * 60 * 1000;
    const recent = samples.filter((s) => s.ts >= cutoff);
    if (recent.length >= 2) {
      const first = recent[0];
      const last = recent[recent.length - 1];
      const dtMin = (last.ts - first.ts) / 60000;
      if (dtMin > 0.1) {
        const rate = (last.count - first.count) / dtMin;
        setThroughput({ perMin: rate, perHour: rate * 60 });
      }
    }

    // Stall: 5 min no change while running
    if (now - lastActivityTs > 5 * 60 * 1000 && (run.data?.status === "running" || run.data?.status === "pending")) {
      setStalled(true);
    }
  }, [completedCases, run.data?.status]);

  // Track result count (no auto-scroll — user stays where they are)
  const resultCount = polledResults.data?.length ?? 0;
  useEffect(() => {
    prevCountRef.current = resultCount;
  }, [resultCount]);

  // Audio playback
  function playAudio(caseId: string, type: "clean" | "degraded") {
    const key = `${caseId}:${type}`;
    if (playingAudio === key) {
      audioRef.current?.pause();
      setPlayingAudio(null);
      return;
    }
    if (audioRef.current) audioRef.current.pause();
    const audio = new Audio(getAudioUrl(id!, caseId, type));
    audio.onended = () => setPlayingAudio(null);
    audio.onerror = () => setPlayingAudio(null);
    audio.play();
    audioRef.current = audio;
    setPlayingAudio(key);
  }

  const data = run.data;
  const isRunning = data?.status === "running" || data?.status === "pending";
  const isFailed = data?.status === "failed";
  const isCompleted = data?.status === "completed";
  const isCancelled = data?.status === "cancelled";
  const isDone = isCompleted || isFailed || isCancelled;

  const results = polledResults.data ?? [];
  const totalCases = data?.total_cases ?? 0;
  const failedCases = data?.failed_cases ?? 0;
  const passedCases = completedCases - failedCases;
  const progress = totalCases > 0 ? (completedCases / totalCases) * 100 : 0;

  // Elapsed
  const elapsedMs = data?.started_at
    ? ((isDone && data.completed_at ? new Date(data.completed_at).getTime() : Date.now()) - new Date(data.started_at).getTime())
    : 0;

  // ETA
  const remaining = totalCases - completedCases;
  const etaMs = throughput.perMin > 0 ? (remaining / throughput.perMin) * 60000 : -1;

  // Per-backend stats
  const backendStats = useMemo(() => {
    const stats = new Map<string, { count: number; passed: number; errors: number; totalLatency: number; lastCreatedAt: string | null }>();
    results.forEach((r) => {
      const key = r.llm_backend || "unknown";
      const ex = stats.get(key) ?? { count: 0, passed: 0, errors: 0, totalLatency: 0, lastCreatedAt: null };
      ex.count++;
      if (r.eval_passed) ex.passed++;
      if (r.error) ex.errors++;
      ex.totalLatency += r.total_latency_ms ?? 0;
      if (r.created_at && (!ex.lastCreatedAt || r.created_at > ex.lastCreatedAt)) ex.lastCreatedAt = r.created_at;
      stats.set(key, ex);
    });
    return stats;
  }, [results]);

  // Error breakdown
  const errorsByStage = useMemo(() => {
    const map = new Map<string, number>();
    results.filter((r) => r.error).forEach((r) => {
      const stage = r.error_stage || "unknown";
      map.set(stage, (map.get(stage) ?? 0) + 1);
    });
    return map;
  }, [results]);

  // Latest result timestamp
  const latestResultTime = useMemo(() => {
    let latest: string | null = null;
    for (const r of results) {
      if (r.created_at && (!latest || r.created_at > latest)) latest = r.created_at;
    }
    return latest;
  }, [results]);

  // Current case from worker activity
  const workerActivity = health.data?.worker;
  const currentCase = workerActivity?.current_case;
  const sys = health.data?.system;

  return (
    <div className="p-4 sm:p-6 max-w-[1400px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-gray-900">Run Monitor</h2>
            {data?.suite_name && (
              <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded">{data.suite_name}</span>
            )}
          </div>
          <p className="text-xs text-gray-400 font-mono mt-0.5">{id}</p>
        </div>
        <div className="flex items-center gap-3">
          {isRunning && (
            <button
              onClick={() => cancel.mutate()}
              disabled={cancel.isPending}
              className="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-50"
            >
              Cancel Run
            </button>
          )}
          {isDone && (
            <Link
              to={`/results/${id}`}
              className="px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700"
            >
              View Results
            </Link>
          )}
        </div>
      </div>

      {/* Stall Warning */}
      {stalled && isRunning && (
        <div className="bg-amber-50 border border-amber-300 rounded-lg p-4 mb-4 flex items-start gap-3">
          <span className="text-amber-500 text-lg">&#x26A0;</span>
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-amber-800">Run appears stalled</h4>
            <p className="text-xs text-amber-700 mt-1">
              No new results in {formatDuration(Date.now() - lastActivityTs)}.
              Worker may have crashed or hit a resource limit.
              {workerActivity?.last_heartbeat && (
                <span className="ml-1">Worker heartbeat: {formatTimeAgo(workerActivity.last_heartbeat)}</span>
              )}
            </p>
            <p className="text-xs text-amber-600 mt-1">
              Check: <code className="bg-amber-100 px-1 rounded text-[10px]">docker compose logs worker --tail 50</code>
            </p>
          </div>
        </div>
      )}

      {/* Run error banner */}
      {isFailed && data?.error_message && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
          <div className="flex items-start gap-3">
            <span className="text-red-500 text-lg">&#x26A0;</span>
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-semibold text-red-800">Run Failed</h4>
              <p className="text-xs text-red-700 mt-1 font-mono break-all">{data.error_message}</p>
              {data.error_details && "traceback" in data.error_details && (
                <details className="mt-2">
                  <summary className="text-xs text-red-600 cursor-pointer hover:text-red-800 font-medium">Traceback</summary>
                  <pre className="mt-1 text-[10px] text-red-700 bg-red-100 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                    {String(data.error_details.traceback)}
                  </pre>
                </details>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ====== TOP ROW: Health Dashboard + System Metrics ====== */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        {/* Health stats - 6 metrics */}
        <div className="lg:col-span-2 grid grid-cols-3 sm:grid-cols-6 gap-2">
          <MetricCard label="Status" value={stalled && isRunning ? "STALLED" : data?.status?.toUpperCase() ?? "..."} color={
            isRunning ? (stalled ? "text-amber-600" : "text-blue-600") :
            isCompleted ? "text-green-600" : isFailed ? "text-red-600" : "text-gray-500"
          } />
          <MetricCard label="Elapsed" value={formatDuration(elapsedMs)} />
          <MetricCard label="Throughput" value={throughput.perMin > 0 ? `${throughput.perMin.toFixed(1)}/min` : "--"}
            sub={throughput.perHour > 0 ? `${Math.round(throughput.perHour)}/hr` : undefined} />
          <MetricCard label="ETA" value={isDone ? "Done" : etaMs > 0 ? formatDuration(etaMs) : "--"} />
          <MetricCard label="Last Result" value={formatTimeAgo(latestResultTime || data?.updated_at)}
            color={stalled ? "text-amber-600" : undefined} />
          <MetricCard label="Pass Rate" value={completedCases > 0 ? `${((passedCases / completedCases) * 100).toFixed(1)}%` : "--"} />
        </div>

        {/* System resources */}
        <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <p className="text-[10px] font-semibold text-gray-400 uppercase">System Resources</p>
            {sys?.hostname && <p className="text-[10px] text-gray-600">{sys.hostname}</p>}
          </div>
          {sys ? (
            <div className="space-y-1.5">
              <MeterBar value={sys.cpu_percent} max={100} color={sys.cpu_percent > 90 ? "bg-red-500" : sys.cpu_percent > 70 ? "bg-amber-500" : "bg-green-500"} label="CPU" />
              <MeterBar value={sys.ram_percent} max={100} color={sys.ram_percent > 90 ? "bg-red-500" : sys.ram_percent > 70 ? "bg-amber-500" : "bg-blue-500"} label="RAM" />
              <div className="flex items-center justify-between text-[10px] text-gray-500">
                <span>{sys.ram_used_gb}GB / {sys.ram_total_gb}GB</span>
                <span>{sys.cpu_count} cores</span>
              </div>
              {sys.gpu?.map((g: Record<string, unknown>, i: number) => {
                const name = String(g.name ?? "GPU");
                const temp = g.temperature_c as number | null;
                const utilPct = g.util_percent as number | null;
                const memPct = g.mem_percent as number | null;
                const memUsed = g.mem_used_gb as number | null;
                const memTotal = g.mem_total_gb as number | null;
                const ollamaModels = g.ollama_models as string[] | undefined;
                const processor = g.processor as string | undefined;
                return (
                  <div key={i} className="mt-1">
                    <div className="flex items-center justify-between text-[10px] text-gray-500">
                      <span className="truncate">{name}</span>
                      <span className="flex items-center gap-2">
                        {processor && (
                          <span className={`font-semibold ${processor === "GPU" ? "text-green-400" : "text-amber-400"}`}>
                            {processor}
                          </span>
                        )}
                        {temp != null && (
                          <span className={temp > 85 ? "text-red-400" : temp > 70 ? "text-amber-400" : "text-green-400"}>
                            {temp}°C
                          </span>
                        )}
                      </span>
                    </div>
                    {utilPct != null && utilPct > 0 && (
                      <MeterBar value={utilPct} max={100} color={utilPct > 90 ? "bg-red-500" : "bg-purple-500"} label="GPU" />
                    )}
                    {memPct != null && (
                      <MeterBar value={memPct} max={100} color="bg-purple-400" label="VRAM" />
                    )}
                    {memUsed != null && memTotal != null && (
                      <div className="flex items-center justify-between text-[10px] text-gray-500">
                        <span>{memUsed}GB / {memTotal}GB</span>
                        {ollamaModels && ollamaModels.length > 0 && (
                          <span className="text-purple-400 truncate ml-2">{ollamaModels.join(", ")}</span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
              {sys.disk_percent != null && (
                <MeterBar value={sys.disk_percent} max={100} color={sys.disk_percent > 90 ? "bg-red-500" : "bg-gray-500"} label="Disk" />
              )}
            </div>
          ) : (
            <p className="text-xs text-gray-600">Loading...</p>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4 mb-4">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-medium text-gray-600">Progress</span>
          <span className="text-xs text-gray-500 tabular-nums">
            {completedCases.toLocaleString()} / {totalCases.toLocaleString()} cases
          </span>
        </div>
        <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              isFailed ? "bg-red-500" : isCompleted ? "bg-green-500" : stalled ? "bg-amber-500" : "bg-blue-500"
            }`}
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
        <div className="flex items-center justify-between mt-1.5">
          <div className="flex gap-4 text-xs text-gray-500">
            <span><span className="font-medium text-green-600">{passedCases.toLocaleString()}</span> passed</span>
            <span><span className="font-medium text-red-600">{failedCases.toLocaleString()}</span> failed</span>
            {isRunning && !stalled && <span className="text-blue-500 animate-pulse">Running...</span>}
            {stalled && isRunning && <span className="text-amber-600 font-medium">Stalled</span>}
          </div>
          <span className="text-sm font-semibold text-gray-900 tabular-nums">{progress.toFixed(1)}%</span>
        </div>
        {/* Timestamps row */}
        <div className="flex gap-4 mt-2 pt-2 border-t border-gray-100 text-[10px] text-gray-400">
          {data?.started_at && <span>Started: {new Date(data.started_at).toLocaleString()}</span>}
          {data?.updated_at && <span>Updated: {formatTimeAgo(data.updated_at)}</span>}
          {data?.completed_at && <span>Completed: {new Date(data.completed_at).toLocaleString()}</span>}
        </div>
      </div>

      {/* ====== MIDDLE ROW: Current Activity + Error Budget ====== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        {/* Current Activity - what's being processed RIGHT NOW */}
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-semibold text-gray-500 uppercase">Current Activity</h3>
            {workerActivity && (
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                workerActivity.status === "processing" ? "bg-green-100 text-green-700" :
                workerActivity.status === "error" ? "bg-red-100 text-red-700" :
                "bg-gray-100 text-gray-600"
              }`}>
                {workerActivity.status}
              </span>
            )}
          </div>
          {currentCase && workerActivity?.status === "processing" ? (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <p className="text-[10px] text-gray-400">Backend</p>
                  <p className="font-medium text-gray-800">{String(currentCase.backend || "--")}</p>
                </div>
                <div>
                  <p className="text-[10px] text-gray-400">Pipeline</p>
                  <p className="font-medium text-gray-800">{String(currentCase.pipeline || "--")}</p>
                </div>
                <div>
                  <p className="text-[10px] text-gray-400">Noise</p>
                  <p className="font-medium text-gray-800">{String(currentCase.noise_type || "--")} @ {String(currentCase.snr_db ?? "--")}dB</p>
                </div>
                <div>
                  <p className="text-[10px] text-gray-400">Rate</p>
                  <p className="font-medium text-gray-800">{workerActivity.cases_per_min.toFixed(1)} cases/min</p>
                </div>
              </div>
              {currentCase.original_text ? (
                <div className="bg-gray-50 rounded p-2 mt-2">
                  <p className="text-[10px] text-gray-400 mb-0.5">Utterance</p>
                  <p className="text-xs text-gray-700 italic">"{String(currentCase.original_text)}"</p>
                </div>
              ) : null}
              {currentCase.latency_ms != null ? (
                <p className="text-[10px] text-gray-400">
                  Last latency: <span className="text-gray-600 font-medium">{Number(currentCase.latency_ms).toFixed(0)}ms</span>
                  {currentCase.passed != null ? (
                    <span className={`ml-2 ${currentCase.passed ? "text-green-600" : "text-red-500"}`}>
                      {currentCase.passed ? "PASSED" : "FAILED"}
                    </span>
                  ) : null}
                </p>
              ) : null}
              {currentCase.error ? (
                <p className="text-[10px] text-red-600 bg-red-50 rounded p-1.5 mt-1">
                  {String(currentCase.error)}
                </p>
              ) : null}
              {/* Audio playback for current case */}
              {currentCase.test_case_id && id ? (
                <div className="flex gap-2 mt-2">
                  <AudioButton label="Clean" caseId={String(currentCase.test_case_id)} type="clean" runId={id} playing={playingAudio} onPlay={playAudio} />
                  <AudioButton label="Degraded" caseId={String(currentCase.test_case_id)} type="degraded" runId={id} playing={playingAudio} onPlay={playAudio} />
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-gray-400">
              {isRunning ? "Waiting for worker activity..." : isDone ? "Run complete" : "Pending..."}
            </p>
          )}
          {workerActivity?.last_heartbeat && (
            <p className="text-[10px] text-gray-400 mt-2 pt-2 border-t border-gray-100">
              Worker heartbeat: {formatTimeAgo(workerActivity.last_heartbeat)}
            </p>
          )}
        </div>

        {/* Error Budget / Backend Health */}
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-semibold text-gray-500 uppercase">Backend Health</h3>
            {errorsByStage.size > 0 && (
              <span className="text-[10px] text-red-500">{[...errorsByStage.values()].reduce((a, b) => a + b, 0)} total errors</span>
            )}
          </div>

          {/* Per-backend stats */}
          {backendStats.size > 0 ? (
            <div className="space-y-2.5">
              {[...backendStats.entries()].map(([backend, stats]) => {
                const errorRate = stats.count > 0 ? (stats.errors / stats.count) * 100 : 0;
                const passRate = stats.count > 0 ? (stats.passed / stats.count) * 100 : 0;
                const budget = workerActivity?.error_budget?.[backend];
                return (
                  <div key={backend} className="text-xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-gray-700 truncate max-w-[200px]">{backend}</span>
                      <span className="text-[10px] text-gray-400 tabular-nums">{stats.count} done</span>
                    </div>
                    <div className="flex items-center gap-1 h-2">
                      <div className="flex-1 h-full bg-gray-100 rounded-full overflow-hidden flex">
                        <div className="h-full bg-green-500" style={{ width: `${passRate}%` }} />
                        <div className="h-full bg-red-400" style={{ width: `${errorRate}%` }} />
                      </div>
                      <span className="text-[10px] text-gray-500 tabular-nums w-10 text-right">{passRate.toFixed(0)}%</span>
                    </div>
                    <div className="flex gap-3 mt-0.5 text-[10px] text-gray-400">
                      {stats.errors > 0 && <span className="text-red-500">{stats.errors} errors</span>}
                      {budget?.consecutive ? <span className="text-amber-500">{budget.consecutive} consecutive</span> : null}
                      {stats.count - stats.errors > 0 && (
                        <span>avg {(stats.totalLatency / (stats.count - stats.errors)).toFixed(0)}ms</span>
                      )}
                      {stats.lastCreatedAt && <span className="ml-auto">{formatTimeAgo(stats.lastCreatedAt)}</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-gray-400">No results yet</p>
          )}

          {/* Error breakdown by stage */}
          {errorsByStage.size > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              <p className="text-[10px] font-medium text-gray-400 mb-1.5">ERRORS BY STAGE</p>
              <div className="flex flex-wrap gap-1.5">
                {[...errorsByStage.entries()].map(([stage, count]) => (
                  <span key={stage} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${stageColor(stage)}`}>
                    {stageLabel(stage)} <span className="font-bold">{count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ====== WORKER LOG (collapsible) ====== */}
      {workerActivity?.worker_log && workerActivity.worker_log.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm mb-4">
          <button
            onClick={() => setShowWorkerLog(!showWorkerLog)}
            className="w-full px-4 py-2.5 flex items-center justify-between text-xs font-semibold text-gray-500 uppercase hover:bg-gray-50"
          >
            <span>Worker Log ({workerActivity.worker_log.length} entries)</span>
            <span className="text-gray-400">{showWorkerLog ? "Hide" : "Show"}</span>
          </button>
          {showWorkerLog && (
            <div className="max-h-48 overflow-y-auto divide-y divide-gray-50 border-t border-gray-100">
              {workerActivity.worker_log.map((entry, i) => (
                <div key={i} className={`px-4 py-1.5 flex items-start gap-2 text-[11px] ${
                  entry.level === "error" ? "bg-red-50/50 text-red-700" : "text-gray-600"
                }`}>
                  <span className="text-[10px] text-gray-400 shrink-0 tabular-nums w-16">
                    {new Date(entry.timestamp).toLocaleTimeString()}
                  </span>
                  <span className={`shrink-0 w-10 font-semibold uppercase ${
                    entry.level === "error" ? "text-red-500" : entry.level === "warn" ? "text-amber-500" : "text-gray-400"
                  }`}>
                    {entry.level}
                  </span>
                  <span className="flex-1 break-all">{entry.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ====== RESULTS LOG ====== */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-xs font-semibold text-gray-500 uppercase">Results</h3>
          <div className="flex gap-3 text-[10px] text-gray-400">
            <span>{results.length} loaded</span>
            {results.filter((r) => r.error).length > 0 && (
              <span className="text-red-500">{results.filter((r) => r.error).length} errors</span>
            )}
          </div>
        </div>
        <div className="max-h-[28rem] overflow-y-auto divide-y divide-gray-50">
          {results.length === 0 && (
            <p className="px-4 py-8 text-center text-gray-400 text-sm">
              {isRunning ? "Waiting for results..." : "No results yet."}
            </p>
          )}
          {results.map((r, i) => (
            <div key={r.test_case_id + i}>
              <div
                className={`px-4 py-2 flex items-center gap-2 text-sm ${
                  r.error ? "bg-red-50/30 cursor-pointer hover:bg-red-50" : "hover:bg-gray-50/50"
                }`}
                onClick={() => r.error ? setExpandedError(expandedError === i ? null : i) : undefined}
              >
                <span className={`w-2 h-2 rounded-full shrink-0 ${
                  r.error ? "bg-red-500" : r.eval_passed ? "bg-green-500" : "bg-yellow-500"
                }`} />
                <span className="text-gray-400 font-mono text-[10px] w-24 shrink-0 truncate">{r.llm_backend || "--"}</span>
                <span className="text-gray-500 font-mono text-[10px] w-14 shrink-0">{r.test_case_id?.slice(0, 8)}</span>
                <span className="text-[10px] text-gray-400 w-10 shrink-0">{r.snr_db != null ? `${r.snr_db}dB` : ""}</span>

                {r.error ? (
                  <>
                    {r.error_stage && (
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${stageColor(r.error_stage)}`}>
                        {stageLabel(r.error_stage)}
                      </span>
                    )}
                    <span className="text-[10px] text-red-600 truncate flex-1 min-w-0">
                      {r.error.length > 80 ? r.error.slice(0, 80) + "..." : r.error}
                    </span>
                  </>
                ) : (
                  <>
                    {r.eval_score != null && (
                      <span className="text-[10px] text-gray-500">score:{(r.eval_score * 100).toFixed(0)}%</span>
                    )}
                    {r.asr_transcript && (
                      <span className="text-[10px] text-gray-400 truncate max-w-[180px]" title={r.asr_transcript}>
                        "{r.asr_transcript.slice(0, 35)}{r.asr_transcript.length > 35 ? "..." : ""}"
                      </span>
                    )}
                    {r.total_latency_ms != null && (
                      <span className="ml-auto text-[10px] text-gray-400 tabular-nums shrink-0">{r.total_latency_ms.toFixed(0)}ms</span>
                    )}
                    {/* Audio buttons */}
                    {id && (
                      <div className="flex gap-1 ml-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                        <AudioButton label="C" caseId={r.test_case_id} type="clean" runId={id} playing={playingAudio} onPlay={playAudio} small />
                        <AudioButton label="D" caseId={r.test_case_id} type="degraded" runId={id} playing={playingAudio} onPlay={playAudio} small />
                      </div>
                    )}
                  </>
                )}
              </div>

              {r.error && expandedError === i && (
                <div className="px-4 py-2 bg-red-50 border-t border-red-100">
                  <p className="text-[10px] text-red-800 font-mono whitespace-pre-wrap break-all">{r.error}</p>
                  {r.original_text && <p className="text-[10px] text-gray-600 mt-1">Original: "{r.original_text}"</p>}
                  {r.created_at && <p className="text-[10px] text-gray-400 mt-1">{new Date(r.created_at).toLocaleString()}</p>}
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

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MetricCard({ label, value, color, sub }: { label: string; value: string; color?: string; sub?: string }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-2.5">
      <p className="text-[10px] font-medium text-gray-400 uppercase">{label}</p>
      <p className={`text-sm font-bold mt-0.5 tabular-nums ${color || "text-gray-900"}`}>{value}</p>
      {sub && <p className="text-[10px] text-gray-400 tabular-nums">{sub}</p>}
    </div>
  );
}

function AudioButton({ label, caseId, type, runId, playing, onPlay, small }: {
  label: string;
  caseId: string;
  type: "clean" | "degraded";
  runId: string;
  playing: string | null;
  onPlay: (caseId: string, type: "clean" | "degraded") => void;
  small?: boolean;
}) {
  const isPlaying = playing === `${caseId}:${type}`;
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onPlay(caseId, type); }}
      className={`${small ? "w-6 h-5 text-[9px]" : "px-2.5 py-1 text-[10px]"} rounded font-medium transition-colors ${
        isPlaying
          ? "bg-blue-600 text-white"
          : "bg-gray-100 text-gray-500 hover:bg-gray-200"
      }`}
      title={`${isPlaying ? "Stop" : "Play"} ${type} audio`}
    >
      {isPlaying ? "||" : small ? label : `Play ${label}`}
    </button>
  );
}
