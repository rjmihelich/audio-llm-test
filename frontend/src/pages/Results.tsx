import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import {
  getRunStats,
  queryResults,
  getExportUrl,
  getRun,
  launchRun,
  getAudioUrl,
  type StatsResponse,
  type ResultResponse,
} from "../api/client";
import StatsCard from "../components/StatsCard";

type Tab = "results" | "charts" | "export";

const CHART_COLORS = [
  "#3b82f6",
  "#ef4444",
  "#10b981",
  "#f59e0b",
  "#8b5cf6",
  "#ec4899",
];

export default function Results() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("results");

  const run = useQuery({
    queryKey: ["run", id],
    queryFn: () => getRun(id!),
    enabled: !!id,
  });

  const rerun = useMutation({
    mutationFn: () => launchRun(run.data!.test_suite_id),
    onSuccess: (data) => navigate(`/runs/${data.id}`),
  });

  const rerunQuick = useMutation({
    mutationFn: () => launchRun(run.data!.test_suite_id, false, 5),
    onSuccess: (data) => navigate(`/runs/${data.id}`),
  });

  const stats = useQuery({
    queryKey: ["stats", id],
    queryFn: () => getRunStats(id!),
    enabled: !!id,
  });

  const results = useQuery({
    queryKey: ["results", id],
    queryFn: () => queryResults(id!, { limit: 500 }),
    enabled: !!id,
  });

  const s = stats.data;
  const r = run.data;

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <h2 className="text-2xl font-bold text-gray-900">Test Results</h2>
          {r && (
            <span
              className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                r.status === "completed"
                  ? "bg-green-100 text-green-700"
                  : r.status === "failed"
                    ? "bg-red-100 text-red-700"
                    : "bg-gray-100 text-gray-600"
              }`}
            >
              {r.status}
            </span>
          )}
        </div>
        <p className="text-sm text-gray-500 font-mono">{id?.slice(0, 12)}...</p>
        {r && (r.status === "completed" || r.status === "failed") && (
          <div className="flex gap-2 mt-2">
            <button
              onClick={() => rerunQuick.mutate()}
              disabled={rerunQuick.isPending}
              className="px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-100 rounded-lg hover:bg-amber-200 disabled:opacity-50"
            >
              {rerunQuick.isPending ? "..." : "Re-test (5 cases)"}
            </button>
            <button
              onClick={() => rerun.mutate()}
              disabled={rerun.isPending}
              className="px-3 py-1.5 text-xs font-medium text-green-700 bg-green-100 rounded-lg hover:bg-green-200 disabled:opacity-50"
            >
              {rerun.isPending ? "..." : "Re-run Full Suite"}
            </button>
          </div>
        )}
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
        <StatsCard
          title="Total Tests"
          value={s?.total_tests ?? "--"}
          trend="neutral"
        />
        <StatsCard
          title="Passed"
          value={
            s && s.completed > 0
              ? `${s.completed - s.errors}`
              : "--"
          }
          subtitle={`${s?.errors ?? 0} failed`}
          trend="neutral"
        />
        <StatsCard
          title="Pass Rate"
          value={
            s?.overall_pass_rate != null
              ? `${(s.overall_pass_rate * 100).toFixed(0)}%`
              : "--"
          }
          trend={
            s?.overall_pass_rate != null
              ? s.overall_pass_rate >= 0.8
                ? "up"
                : s.overall_pass_rate >= 0.5
                  ? "neutral"
                  : "down"
              : "neutral"
          }
        />
        <StatsCard
          title="Mean Score"
          value={
            s?.overall_mean_score != null
              ? s.overall_mean_score.toFixed(2)
              : "--"
          }
          trend="neutral"
        />
        <StatsCard
          title="Mean WER"
          value={
            s?.mean_wer != null
              ? `${(s.mean_wer * 100).toFixed(1)}%`
              : "--"
          }
          subtitle={s?.wer_sample_size ? `n=${s.wer_sample_size}` : "Pipeline B only"}
          trend={
            s?.mean_wer != null
              ? s.mean_wer <= 0.1
                ? "up"
                : s.mean_wer <= 0.3
                  ? "neutral"
                  : "down"
              : "neutral"
          }
        />
        <StatsCard
          title="Avg Latency"
          value={
            s?.mean_latency_ms != null
              ? `${s.mean_latency_ms.toFixed(0)}ms`
              : "--"
          }
          trend="neutral"
        />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 rounded-lg p-1 w-fit mb-6">
        {(["results", "charts", "export"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors capitalize ${
              tab === t
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "results" && <ResultsTab results={results.data ?? []} runId={id!} />}
      {tab === "charts" && <ChartsTab stats={s} results={results.data} />}
      {tab === "export" && <ExportTab runId={id!} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Results Tab — detailed test-by-test view
// ---------------------------------------------------------------------------

function AudioButton({ label, url, color, disabled = false }: { label: string; url: string; color: string; disabled?: boolean }) {
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState(false);

  const play = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (disabled) return;
    setError(false);
    const audio = new Audio(url);
    audio.onplay = () => setPlaying(true);
    audio.onended = () => setPlaying(false);
    audio.onerror = () => { setPlaying(false); setError(true); };
    audio.play().catch(() => { setPlaying(false); setError(true); });
  };

  const isDisabled = disabled || playing;

  return (
    <button
      onClick={play}
      disabled={isDisabled}
      className={`px-2.5 py-1 text-[11px] font-medium rounded-lg border transition-colors ${
        disabled
          ? "border-gray-200 text-gray-300 cursor-not-allowed"
          : error
            ? "border-gray-200 text-gray-400 cursor-not-allowed"
            : playing
              ? `${color} text-white`
              : `border-gray-200 text-gray-600 hover:${color} hover:text-white`
      }`}
    >
      {disabled ? `${label} (n/a)` : playing ? "..." : error ? `${label} (n/a)` : label}
    </button>
  );
}

function ResultsTab({ results, runId }: { results: ResultResponse[]; runId: string }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filterPassed, setFilterPassed] = useState<"all" | "pass" | "fail">("all");

  const filtered = results.filter((r) => {
    if (filterPassed === "pass") return r.eval_passed === true;
    if (filterPassed === "fail") return r.eval_passed === false;
    return true;
  });

  // Compute STT accuracy: how many transcripts match original text
  const sttCorrect = results.filter(
    (r) =>
      r.original_text &&
      r.asr_transcript &&
      r.asr_transcript.toLowerCase().replace(/[^\w\s]/g, "").trim() ===
        r.original_text.toLowerCase().replace(/[^\w\s]/g, "").trim()
  ).length;
  const sttTotal = results.filter((r) => r.asr_transcript).length;

  // Mean WER across results that have it
  const werResults = results.filter((r) => r.wer != null);
  const meanWer = werResults.length > 0
    ? werResults.reduce((sum, r) => sum + r.wer!, 0) / werResults.length
    : null;

  return (
    <div>
      {/* Pipeline summary */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 mb-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Pipeline Summary</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div>
            <p className="text-gray-500 text-xs">Pipeline</p>
            <p className="font-medium text-gray-900">
              {[...new Set(results.map((r) => r.pipeline_type))].join(", ") || "--"}
            </p>
          </div>
          <div>
            <p className="text-gray-500 text-xs">LLM Backend</p>
            <p className="font-medium text-gray-900">
              {[...new Set(results.map((r) => r.llm_backend))].join(", ") || "--"}
            </p>
          </div>
          <div>
            <p className="text-gray-500 text-xs">STT Accuracy</p>
            <p className="font-medium text-gray-900">
              {sttTotal > 0 ? `${sttCorrect}/${sttTotal} (${((sttCorrect / sttTotal) * 100).toFixed(0)}%)` : "--"}
            </p>
          </div>
          <div>
            <p className="text-gray-500 text-xs">Mean WER</p>
            <p className={`font-medium ${meanWer != null ? (meanWer <= 0.1 ? "text-green-700" : meanWer <= 0.3 ? "text-amber-700" : "text-red-700") : "text-gray-900"}`}>
              {meanWer != null ? `${(meanWer * 100).toFixed(1)}%` : "--"}
            </p>
          </div>
          <div>
            <p className="text-gray-500 text-xs">Evaluator</p>
            <p className="font-medium text-gray-900">
              {[...new Set(results.map((r) => r.evaluator_type).filter(Boolean))].join(", ") || "--"}
            </p>
          </div>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex gap-2 mb-4">
        {(["all", "pass", "fail"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilterPassed(f)}
            className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
              filterPassed === f
                ? f === "pass"
                  ? "bg-green-600 text-white border-green-600"
                  : f === "fail"
                    ? "bg-red-600 text-white border-red-600"
                    : "bg-slate-800 text-white border-slate-800"
                : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"
            }`}
          >
            {f === "all" ? `All (${results.length})` : f === "pass" ? `Passed (${results.filter((r) => r.eval_passed).length})` : `Failed (${results.filter((r) => !r.eval_passed).length})`}
          </button>
        ))}
      </div>

      {/* Test case cards */}
      <div className="space-y-3">
        {filtered.map((r, i) => {
          const isExpanded = expandedId === r.test_case_id;
          const sttMatch =
            r.original_text &&
            r.asr_transcript &&
            r.asr_transcript.toLowerCase().replace(/[^\w\s]/g, "").trim() ===
              r.original_text.toLowerCase().replace(/[^\w\s]/g, "").trim();

          return (
            <div
              key={r.test_case_id}
              className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden"
            >
              {/* Header row — always visible */}
              <button
                onClick={() => setExpandedId(isExpanded ? null : r.test_case_id)}
                className="w-full px-5 py-4 flex items-center gap-4 text-left hover:bg-gray-50 transition-colors"
              >
                {/* Pass/fail indicator */}
                <span
                  className={`w-3 h-3 rounded-full shrink-0 ${
                    r.eval_passed ? "bg-green-500" : "bg-red-500"
                  }`}
                />

                {/* Test number and utterance */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-gray-400">#{i + 1}</span>
                    <span className="text-sm font-medium text-gray-900 truncate">
                      {r.original_text || r.asr_transcript || r.test_case_id.slice(0, 8)}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-0.5">
                    <span className="text-xs text-gray-500">
                      intent: <span className="font-medium">{r.expected_intent || "--"}</span>
                    </span>
                    <span className="text-xs text-gray-500">
                      action: <span className="font-medium">{r.expected_action || "--"}</span>
                    </span>
                  </div>
                </div>

                {/* Score */}
                <div className="text-right shrink-0">
                  <span
                    className={`text-lg font-bold ${
                      r.eval_passed ? "text-green-600" : "text-red-600"
                    }`}
                  >
                    {r.eval_score != null ? r.eval_score.toFixed(2) : "--"}
                  </span>
                  <p className="text-[10px] text-gray-400 uppercase">
                    {r.eval_passed ? "PASS" : "FAIL"}
                  </p>
                </div>

                {/* Latency */}
                <div className="text-right shrink-0 w-16">
                  <span className="text-sm tabular-nums text-gray-600">
                    {r.total_latency_ms != null ? `${r.total_latency_ms.toFixed(0)}ms` : "--"}
                  </span>
                </div>

                {/* Expand arrow */}
                <span className={`text-gray-400 transition-transform ${isExpanded ? "rotate-180" : ""}`}>
                  {"\u25BC"}
                </span>
              </button>

              {/* Expanded detail */}
              {isExpanded && (
                <div className="px-5 pb-5 border-t border-gray-100 pt-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Left: Pipeline flow */}
                    <div className="space-y-3">
                      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Pipeline Flow
                      </h4>

                      {/* Step 1: Original utterance */}
                      <div className="flex items-start gap-2">
                        <span className="w-5 h-5 rounded bg-blue-100 text-blue-600 text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">1</span>
                        <div>
                          <p className="text-[10px] text-gray-400 uppercase">Original Utterance</p>
                          <p className="text-sm text-gray-900">{r.original_text || "--"}</p>
                        </div>
                      </div>

                      {/* Step 2: STT transcript */}
                      {r.pipeline_type === "asr_text" && (
                        <div className="flex items-start gap-2">
                          <span className="w-5 h-5 rounded bg-purple-100 text-purple-600 text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">2</span>
                          <div>
                            <p className="text-[10px] text-gray-400 uppercase flex items-center gap-1">
                              STT Transcript
                              {sttMatch ? (
                                <span className="text-green-600">match</span>
                              ) : (
                                <span className="text-amber-600">mismatch</span>
                              )}
                            </p>
                            <p className={`text-sm ${sttMatch ? "text-gray-900" : "text-amber-700"}`}>
                              {r.asr_transcript || "--"}
                            </p>
                          </div>
                        </div>
                      )}

                      {/* Step 3: LLM Response */}
                      <div className="flex items-start gap-2">
                        <span className="w-5 h-5 rounded bg-green-100 text-green-600 text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">
                          {r.pipeline_type === "asr_text" ? "3" : "2"}
                        </span>
                        <div>
                          <p className="text-[10px] text-gray-400 uppercase">
                            LLM Response ({r.llm_backend})
                          </p>
                          <p className="text-sm text-gray-900 whitespace-pre-wrap">
                            {r.llm_response_text?.trim() || "--"}
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Right: Evaluation + params */}
                    <div className="space-y-3">
                      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Evaluation
                      </h4>
                      <div className="bg-gray-50 rounded-lg p-3 space-y-2">
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-500">Evaluator</span>
                          <span className="font-medium text-gray-900">{r.evaluator_type || "--"}</span>
                        </div>
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-500">Expected Action</span>
                          <span className="font-mono text-gray-900">{r.expected_action || "--"}</span>
                        </div>
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-500">Score</span>
                          <span className={`font-bold ${r.eval_passed ? "text-green-600" : "text-red-600"}`}>
                            {r.eval_score != null ? r.eval_score.toFixed(4) : "--"}
                          </span>
                        </div>
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-500">Threshold</span>
                          <span className="text-gray-700">0.60</span>
                        </div>
                        {/* Score bar */}
                        <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${r.eval_passed ? "bg-green-500" : "bg-red-500"}`}
                            style={{ width: `${Math.min((r.eval_score ?? 0) * 100, 100)}%` }}
                          />
                        </div>
                      </div>

                      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider pt-2">
                        Audio Parameters
                      </h4>
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div className="bg-gray-50 rounded-lg px-3 py-2">
                          <p className="text-[10px] text-gray-400">SNR</p>
                          <p className="font-medium text-gray-900">{r.snr_db} dB</p>
                        </div>
                        <div className="bg-gray-50 rounded-lg px-3 py-2">
                          <p className="text-[10px] text-gray-400">Noise</p>
                          <p className="font-medium text-gray-900">{r.noise_type}</p>
                        </div>
                        <div className="bg-gray-50 rounded-lg px-3 py-2">
                          <p className="text-[10px] text-gray-400">Echo Delay</p>
                          <p className="font-medium text-gray-900">{r.delay_ms}ms</p>
                        </div>
                        {r.wer != null && (
                          <div className="bg-gray-50 rounded-lg px-3 py-2">
                            <p className="text-[10px] text-gray-400">WER</p>
                            <p className={`font-medium ${r.wer <= 0.1 ? "text-green-700" : r.wer <= 0.3 ? "text-amber-700" : "text-red-700"}`}>
                              {(r.wer * 100).toFixed(1)}%
                            </p>
                          </div>
                        )}
                      </div>

                      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider pt-2">
                        Latency Breakdown
                      </h4>
                      <div className="grid grid-cols-3 gap-2 text-sm">
                        <div className="bg-gray-50 rounded-lg px-3 py-2">
                          <p className="text-[10px] text-gray-400">Total</p>
                          <p className="font-medium text-gray-900">
                            {r.total_latency_ms != null ? `${r.total_latency_ms.toFixed(0)}ms` : "--"}
                          </p>
                        </div>
                        <div className="bg-gray-50 rounded-lg px-3 py-2">
                          <p className="text-[10px] text-gray-400">LLM</p>
                          <p className="font-medium text-gray-900">
                            {r.llm_latency_ms != null ? `${r.llm_latency_ms.toFixed(0)}ms` : "--"}
                          </p>
                        </div>
                        <div className="bg-gray-50 rounded-lg px-3 py-2">
                          <p className="text-[10px] text-gray-400">ASR</p>
                          <p className="font-medium text-gray-900">
                            {r.asr_latency_ms != null ? `${r.asr_latency_ms.toFixed(0)}ms` : "--"}
                          </p>
                        </div>
                      </div>
                      {(r.input_tokens != null || r.output_tokens != null) && (
                        <div className="flex gap-3 text-xs text-gray-500 pt-1">
                          {r.input_tokens != null && <span>In: <span className="font-medium text-gray-700">{r.input_tokens.toLocaleString()} tok</span></span>}
                          {r.output_tokens != null && <span>Out: <span className="font-medium text-gray-700">{r.output_tokens.toLocaleString()} tok</span></span>}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Audio playback */}
                  <div className="mt-4 flex items-center gap-2 border-t border-gray-100 pt-3">
                    <span className="text-[10px] text-gray-400 uppercase font-semibold mr-1">Audio</span>
                    <AudioButton label="Clean" url={getAudioUrl(runId, r.test_case_id, "clean")} color="bg-blue-600" />
                    <AudioButton label="Degraded" url={getAudioUrl(runId, r.test_case_id, "degraded")} color="bg-amber-600" disabled={!r.has_degraded_audio} />
                    <AudioButton label="Echo" url={getAudioUrl(runId, r.test_case_id, "echo")} color="bg-purple-600" disabled={!r.has_degraded_audio} />
                  </div>

                  {r.error && (
                    <div className="mt-3 p-3 bg-red-50 rounded-lg text-sm text-red-700">
                      <span className="font-medium">Error:</span> {r.error}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-12 text-gray-400">No results found.</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Charts Tab
// ---------------------------------------------------------------------------

function ChartsTab({
  stats,
  results,
}: {
  stats?: StatsResponse;
  results?: ResultResponse[];
}) {
  const chartData = buildAccuracyBySNR(stats, results);
  const backends = [...new Set(results?.map((r) => r.llm_backend) ?? [])];

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">
          Accuracy vs SNR (dB)
        </h3>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={350}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="snr_db"
                label={{ value: "SNR (dB)", position: "insideBottom", offset: -5 }}
              />
              <YAxis
                domain={[0, 1]}
                tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                label={{ value: "Accuracy", angle: -90, position: "insideLeft" }}
              />
              <Tooltip formatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
              <Legend />
              {backends.map((b, i) => (
                <Line
                  key={b}
                  type="monotone"
                  dataKey={b}
                  stroke={CHART_COLORS[i % CHART_COLORS.length]}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-gray-400 text-sm text-center py-12">
            Need multiple SNR values to chart accuracy curves.
          </p>
        )}
      </div>
    </div>
  );
}

function buildAccuracyBySNR(
  stats?: StatsResponse,
  results?: ResultResponse[]
): Array<Record<string, unknown>> {
  if (stats?.accuracy_by_snr?.length) return stats.accuracy_by_snr;
  if (!results?.length) return [];

  const grouped = new Map<number, Map<string, { pass: number; total: number }>>();
  for (const r of results) {
    if (r.eval_passed == null) continue;
    if (!grouped.has(r.snr_db)) grouped.set(r.snr_db, new Map());
    const byBackend = grouped.get(r.snr_db)!;
    if (!byBackend.has(r.llm_backend))
      byBackend.set(r.llm_backend, { pass: 0, total: 0 });
    const entry = byBackend.get(r.llm_backend)!;
    entry.total++;
    if (r.eval_passed) entry.pass++;
  }

  const snrs = [...grouped.keys()].sort((a, b) => a - b);
  return snrs.map((snr) => {
    const row: Record<string, unknown> = { snr_db: snr };
    const byBackend = grouped.get(snr)!;
    for (const [backend, { pass, total }] of byBackend) {
      row[backend] = total > 0 ? pass / total : null;
    }
    return row;
  });
}

// ---------------------------------------------------------------------------
// Export Tab
// ---------------------------------------------------------------------------

function ExportTab({ runId }: { runId: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 max-w-md">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Export Results</h3>
      <div className="space-y-3">
        {(["csv", "json", "parquet"] as const).map((fmt) => (
          <a
            key={fmt}
            href={getExportUrl(runId, fmt)}
            download
            className="flex items-center justify-between px-4 py-3 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <div>
              <p className="text-sm font-medium text-gray-900 uppercase">{fmt}</p>
              <p className="text-xs text-gray-500">
                {fmt === "csv" ? "Comma-separated values" : fmt === "json" ? "JSON array" : "Apache Parquet"}
              </p>
            </div>
            <span className="text-gray-400 text-lg">{"\u2193"}</span>
          </a>
        ))}
      </div>
    </div>
  );
}
