import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  BarChart, Bar, ResponsiveContainer, Cell,
  AreaChart, Area,
} from "recharts";
import { listRuns, fetchDashboard, fetchInsights, type DashboardResponse, type InsightsResponse } from "../api/client";
import StatsCard from "../components/StatsCard";

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"];

function EmptyState() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-12 text-center">
      <div className="text-4xl mb-3">📊</div>
      <h3 className="text-lg font-semibold text-gray-700 mb-2">No Results Yet</h3>
      <p className="text-sm text-gray-400 max-w-md mx-auto mb-4">
        Run a test suite to see performance dashboards here. Results from all
        completed runs will be aggregated automatically.
      </p>
      <Link
        to="/tests"
        className="inline-block px-5 py-2.5 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700"
      >
        Create Test Suite
      </Link>
    </div>
  );
}

function ChartCard({
  title,
  subtitle,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`bg-white rounded-xl border border-gray-200 shadow-sm ${className}`}>
      <div className="px-5 pt-5 pb-2">
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
        {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
      </div>
      <div className="px-4 pb-4">{children}</div>
    </div>
  );
}

// -- Accuracy vs SNR line chart with CI band --
function AccuracyBySNR({ data }: { data: Array<Record<string, unknown>> }) {
  const chartData = data
    .map((d) => ({
      snr: Number(d.group),
      passRate: Math.round(Number(d.pass_rate) * 100),
      meanScore: Math.round(Number(d.mean_score) * 100),
      ciLow: Math.round(Number(d.pass_ci_low) * 100),
      ciHigh: Math.round(Number(d.pass_ci_high) * 100),
      count: Number(d.count),
    }))
    .sort((a, b) => a.snr - b.snr);

  return (
    <ChartCard title="Accuracy vs SNR (dB)" subtitle="Pass rate and mean score by signal-to-noise ratio">
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="snr" label={{ value: "SNR (dB)", position: "bottom", offset: -5 }} tick={{ fontSize: 12 }} />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
          <Tooltip
            formatter={(val: number, name: string) => [`${val}%`, name]}
            labelFormatter={(label) => `SNR: ${label} dB`}
          />
          <Legend verticalAlign="top" height={36} />
          <Area type="monotone" dataKey="ciHigh" stackId="ci" stroke="none" fill="#3b82f6" fillOpacity={0.08} name="CI Upper" />
          <Area type="monotone" dataKey="ciLow" stackId="ci2" stroke="none" fill="#ffffff" fillOpacity={0} name="CI Lower" />
          <Line type="monotone" dataKey="passRate" stroke="#3b82f6" strokeWidth={2.5} dot={{ r: 4, fill: "#3b82f6" }} name="Pass Rate" />
          <Line type="monotone" dataKey="meanScore" stroke="#10b981" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 3 }} name="Mean Score" />
        </AreaChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// -- Noise type comparison bar chart --
function NoiseComparison({ data }: { data: Array<Record<string, unknown>> }) {
  const chartData = data.map((d) => ({
    noise: String(d.group),
    passRate: Math.round(Number(d.pass_rate) * 100),
    meanScore: Math.round(Number(d.mean_score) * 100),
    count: Number(d.count),
  }));

  return (
    <ChartCard title="Performance by Noise Type" subtitle="Pass rate comparison across noise conditions">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="noise" tick={{ fontSize: 11 }} />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(val: number, name: string) => [`${val}%`, name]} />
          <Legend verticalAlign="top" height={36} />
          <Bar dataKey="passRate" name="Pass Rate" radius={[4, 4, 0, 0]}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
          <Bar dataKey="meanScore" name="Mean Score" fill="#94a3b8" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// -- Echo tolerance heatmap --
function EchoHeatmap({ data }: { data: NonNullable<DashboardResponse["echo_heatmap"]> }) {
  // Flatten to scatter points for recharts
  const points: { delay: number; gain: number; score: number | null }[] = [];
  data.row_labels.forEach((delay, ri) => {
    data.col_labels.forEach((gain, ci) => {
      points.push({ delay, gain, score: data.values[ri][ci] });
    });
  });

  const validPoints = points.filter((p) => p.score !== null);
  const maxScore = Math.max(...validPoints.map((p) => p.score!), 1);

  // Build a grid-based heatmap display
  const cells = points.map((p) => ({
    ...p,
    scorePct: p.score !== null ? Math.round((p.score / maxScore) * 100) : null,
  }));

  return (
    <ChartCard title="Echo Tolerance Heatmap" subtitle="Eval score by echo delay (ms) vs gain (dB)">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="px-2 py-1 text-gray-500 font-medium text-left">Delay \ Gain</th>
              {data.col_labels.map((g) => (
                <th key={g} className="px-2 py-1 text-center text-gray-500 font-medium">{g} dB</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.row_labels.map((delay, ri) => (
              <tr key={delay}>
                <td className="px-2 py-1 font-medium text-gray-600">{delay} ms</td>
                {data.col_labels.map((_, ci) => {
                  const val = data.values[ri][ci];
                  const pct = val !== null ? val : null;
                  // Color from red (0) to green (1)
                  const bg = pct !== null
                    ? pct >= 0.7
                      ? `rgba(16, 185, 129, ${Math.min(pct, 1) * 0.7 + 0.15})`
                      : pct >= 0.4
                        ? `rgba(245, 158, 11, ${pct * 0.6 + 0.2})`
                        : `rgba(239, 68, 68, ${(1 - pct) * 0.5 + 0.2})`
                    : "#f9fafb";

                  return (
                    <td
                      key={ci}
                      className="px-2 py-2 text-center font-mono"
                      style={{ backgroundColor: bg }}
                    >
                      {pct !== null ? (pct * 100).toFixed(0) + "%" : "--"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ChartCard>
  );
}

// -- Backend comparison --
function BackendComparison({ data }: { data: Array<Record<string, unknown>> }) {
  const chartData = data.map((d) => ({
    backend: String(d.group),
    passRate: Math.round(Number(d.pass_rate) * 100),
    meanScore: Math.round(Number(d.mean_score) * 100),
    count: Number(d.count),
  }));

  return (
    <ChartCard title="LLM Backend Comparison" subtitle="Pass rate and score by LLM backend">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chartData} layout="vertical" margin={{ top: 10, right: 20, left: 40, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
          <YAxis type="category" dataKey="backend" tick={{ fontSize: 11 }} width={75} />
          <Tooltip formatter={(val: number, name: string) => [`${val}%`, name]} />
          <Legend verticalAlign="top" height={36} />
          <Bar dataKey="passRate" name="Pass Rate" fill="#3b82f6" radius={[0, 4, 4, 0]} barSize={18} />
          <Bar dataKey="meanScore" name="Mean Score" fill="#10b981" radius={[0, 4, 4, 0]} barSize={18} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// -- Latency distribution --
function LatencyChart({ data }: { data: Array<Record<string, unknown>> }) {
  const chartData = data.map((d) => ({
    backend: String(d.backend),
    mean: Math.round(Number(d.mean_ms)),
    median: Math.round(Number(d.median_ms)),
    std: Math.round(Number(d.std_ms || 0)),
    count: Number(d.count),
  }));

  return (
    <ChartCard title="Latency by Backend" subtitle="Mean and median response latency (ms)">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="backend" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 12 }} label={{ value: "ms", angle: -90, position: "insideLeft" }} />
          <Tooltip formatter={(val: number, name: string) => [`${val} ms`, name]} />
          <Legend verticalAlign="top" height={36} />
          <Bar dataKey="mean" name="Mean" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          <Bar dataKey="median" name="Median" fill="#10b981" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// -- Parameter effects ANOVA table --
function ParameterEffects({ data }: { data: Record<string, unknown> }) {
  const rows = Object.entries(data).map(([factor, stats]) => {
    const s = stats as Record<string, number>;
    return {
      factor,
      fStat: s.F_statistic?.toFixed(2) ?? "--",
      pValue: s.p_value,
      etaSq: s.eta_squared,
      nGroups: s.n_groups,
    };
  });

  rows.sort((a, b) => (b.etaSq ?? 0) - (a.etaSq ?? 0));

  return (
    <ChartCard title="Parameter Impact (ANOVA)" subtitle="Which parameters most affect evaluation scores">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-100">
              <th className="px-3 py-2 font-medium">Factor</th>
              <th className="px-3 py-2 font-medium text-right">F-statistic</th>
              <th className="px-3 py-2 font-medium text-right">p-value</th>
              <th className="px-3 py-2 font-medium text-right">Effect Size</th>
              <th className="px-3 py-2 font-medium">Significance</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const significant = r.pValue !== undefined && r.pValue < 0.05;
              const effectLabel =
                (r.etaSq ?? 0) >= 0.14 ? "Large" : (r.etaSq ?? 0) >= 0.06 ? "Medium" : "Small";
              const effectColor =
                (r.etaSq ?? 0) >= 0.14
                  ? "text-red-600 bg-red-50"
                  : (r.etaSq ?? 0) >= 0.06
                    ? "text-amber-600 bg-amber-50"
                    : "text-gray-600 bg-gray-50";

              return (
                <tr key={r.factor} className="border-b border-gray-50">
                  <td className="px-3 py-2 font-medium text-gray-800">{r.factor}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{r.fStat}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {r.pValue !== undefined ? (r.pValue < 0.001 ? "<0.001" : r.pValue.toFixed(3)) : "--"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${effectColor}`}>
                      {effectLabel} ({((r.etaSq ?? 0) * 100).toFixed(1)}%)
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {significant ? (
                      <span className="text-green-600 font-medium text-xs">Significant</span>
                    ) : (
                      <span className="text-gray-400 text-xs">Not significant</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ChartCard>
  );
}

// -- WER vs SNR line chart --
function WERBySNR({ data }: { data: Array<Record<string, unknown>> }) {
  const chartData = data
    .map((d) => ({
      snr: Number(d.group),
      wer: Math.round(Number(d.mean_wer) * 1000) / 10, // to percent, 1 dp
      count: Number(d.count),
    }))
    .sort((a, b) => a.snr - b.snr);

  return (
    <ChartCard title="Word Error Rate vs SNR" subtitle="Mean WER (Pipeline B) by signal-to-noise ratio">
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="snr" label={{ value: "SNR (dB)", position: "bottom", offset: -5 }} tick={{ fontSize: 12 }} />
          <YAxis tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(val: number) => [`${val}%`, "Mean WER"]} labelFormatter={(l) => `SNR: ${l} dB`} />
          <Line type="monotone" dataKey="wer" stroke="#ef4444" strokeWidth={2.5} dot={{ r: 4, fill: "#ef4444" }} name="Mean WER" />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// -- WER by backend bar chart --
function WERByBackend({ data }: { data: Array<Record<string, unknown>> }) {
  const chartData = data.map((d) => ({
    backend: String(d.group),
    wer: Math.round(Number(d.mean_wer) * 1000) / 10,
    count: Number(d.count),
  }));

  return (
    <ChartCard title="Word Error Rate by Backend" subtitle="Mean WER (Pipeline B) per LLM backend">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chartData} layout="vertical" margin={{ top: 10, right: 20, left: 40, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis type="number" tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
          <YAxis type="category" dataKey="backend" tick={{ fontSize: 11 }} width={75} />
          <Tooltip formatter={(val: number) => [`${val}%`, "Mean WER"]} />
          <Bar dataKey="wer" name="Mean WER" fill="#ef4444" radius={[0, 4, 4, 0]} barSize={18} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// -- Task completion rate over time --
function TaskCompletionHistory({ data }: { data: Array<Record<string, unknown>> }) {
  const chartData = data.map((d) => ({
    run: String(d.run_id),
    passRate: Math.round(Number(d.pass_rate) * 100),
    meanScore: d.mean_score ? Math.round(Number(d.mean_score) * 100) : null,
    cases: Number(d.total_cases),
  }));

  return (
    <ChartCard title="Task Completion Rate Over Time" subtitle="Pass rate trend across completed runs">
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="run" tick={{ fontSize: 10 }} />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(val: number, name: string) => [`${val}%`, name]} />
          <Legend verticalAlign="top" height={36} />
          <Line type="monotone" dataKey="passRate" stroke="#3b82f6" strokeWidth={2.5} dot={{ r: 4, fill: "#3b82f6" }} name="Task Completion" />
          {chartData.some((d) => d.meanScore !== null) && (
            <Line type="monotone" dataKey="meanScore" stroke="#10b981" strokeWidth={2} strokeDasharray="4 4" dot={{ r: 3 }} name="Mean Score" />
          )}
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// -- Run history trend --
function RunHistory({ data }: { data: Array<Record<string, unknown>> }) {
  const chartData = data.map((d, i) => ({
    run: String(d.run_id),
    passRate: Math.round(Number(d.pass_rate) * 100),
    cases: Number(d.total_cases),
    meanScore: d.mean_score ? Math.round(Number(d.mean_score) * 100) : null,
  }));

  return (
    <ChartCard title="Run History" subtitle="Pass rate trend across completed runs" className="col-span-full">
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="run" tick={{ fontSize: 10 }} />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(val: number, name: string) => [`${val}%`, name]} />
          <Line type="monotone" dataKey="passRate" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4, fill: "#3b82f6" }} name="Pass Rate" />
          {chartData.some((d) => d.meanScore !== null) && (
            <Line type="monotone" dataKey="meanScore" stroke="#10b981" strokeWidth={2} strokeDasharray="4 4" dot={{ r: 3 }} name="Mean Score" />
          )}
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// -- Voice Provider comparison bar chart --
function VoiceProviderComparison({ data }: { data: Array<Record<string, unknown>> }) {
  const chartData = data.map((d) => ({
    provider: String(d.group),
    passRate: Math.round(Number(d.pass_rate) * 100),
    meanScore: Math.round(Number(d.mean_score) * 100),
    count: Number(d.count),
  }));

  return (
    <ChartCard title="Voice Provider Comparison" subtitle="Pass rate across voice providers (natural vs synthetic)">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="provider" tick={{ fontSize: 11 }} />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(val: number, name: string) => [`${val}%`, name]} />
          <Legend verticalAlign="top" height={36} />
          <Bar dataKey="passRate" name="Pass Rate" radius={[4, 4, 0, 0]}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
          <Bar dataKey="meanScore" name="Mean Score" fill="#94a3b8" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// -- Corpus Category breakdown bar chart --
function CorpusCategoryChart({ data }: { data: Array<Record<string, unknown>> }) {
  const chartData = data.map((d) => ({
    category: String(d.group),
    passRate: Math.round(Number(d.pass_rate) * 100),
    meanScore: Math.round(Number(d.mean_score) * 100),
    count: Number(d.count),
  }));

  return (
    <ChartCard title="Performance by Corpus Category" subtitle="Pass rate across corpus categories">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="category" tick={{ fontSize: 11 }} />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(val: number, name: string) => [`${val}%`, name]} />
          <Legend verticalAlign="top" height={36} />
          <Bar dataKey="passRate" name="Pass Rate" radius={[4, 4, 0, 0]}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
          <Bar dataKey="meanScore" name="Mean Score" fill="#94a3b8" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// -- AI Insights Panel --
function AIInsightsPanel() {
  const [insights, setInsights] = useState<InsightsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchInsights();
      setInsights(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate insights");
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
      <div className="px-5 pt-5 pb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-700">AI Performance Analysis</h3>
          <p className="text-xs text-gray-400 mt-0.5">
            Generate AI-powered insights from your test results
          </p>
        </div>
        <button
          onClick={handleGenerate}
          disabled={loading}
          className="px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {loading && (
            <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          {loading ? "Generating..." : insights ? "Regenerate Insights" : "Generate Insights"}
        </button>
      </div>
      <div className="px-5 pb-5">
        {error && (
          <div className="mt-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {error}
          </div>
        )}
        {insights && (
          <div className="mt-2">
            <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
              <div
                className="text-sm text-gray-800 leading-relaxed"
                style={{ whiteSpace: "pre-wrap" }}
              >
                {insights.analysis}
              </div>
            </div>
            <p className="text-[10px] text-gray-400 mt-2 text-right">
              Generated at {new Date(insights.generated_at).toLocaleString()}
            </p>
          </div>
        )}
        {!insights && !error && !loading && (
          <p className="text-xs text-gray-400 mt-2">
            Click the button above to generate an AI analysis of your test results.
          </p>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Main Dashboard
// ============================================================================

export default function Dashboard() {
  const runs = useQuery({ queryKey: ["runs"], queryFn: listRuns, refetchInterval: 10000 });
  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: fetchDashboard,
    refetchInterval: 15000,
  });

  const d = dashboard.data;
  const totalRuns = runs.data?.length ?? 0;
  const activeRuns = runs.data?.filter((r) => r.status === "running").length ?? 0;

  const isLoading = dashboard.isLoading || runs.isLoading;

  if (isLoading) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-200 rounded w-48" />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-gray-200 rounded-xl" />)}
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="h-72 bg-gray-200 rounded-xl" />
            <div className="h-72 bg-gray-200 rounded-xl" />
          </div>
        </div>
      </div>
    );
  }

  const hasData = d && d.total_cases > 0;

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Performance Dashboard</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Aggregated results across {d?.total_runs ?? 0} completed run{d?.total_runs !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex gap-3">
          {activeRuns > 0 && (
            <span className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-700 text-xs font-medium rounded-full">
              <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
              {activeRuns} running
            </span>
          )}
          <Link
            to="/tests"
            className="px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700"
          >
            New Test Suite
          </Link>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4">
        <StatsCard title="Completed Runs" value={d?.total_runs ?? 0} trend="neutral" />
        <StatsCard title="Total Cases" value={d?.total_cases ?? 0} trend="neutral" />
        <StatsCard
          title="Overall Pass Rate"
          value={d?.overall_pass_rate != null ? `${(d.overall_pass_rate * 100).toFixed(1)}%` : "--"}
          trend={d?.overall_pass_rate != null ? (d.overall_pass_rate >= 0.5 ? "up" : "down") : "neutral"}
        />
        <StatsCard
          title="Mean Score"
          value={d?.overall_mean_score != null ? `${(d.overall_mean_score * 100).toFixed(1)}%` : "--"}
          trend="neutral"
        />
        <StatsCard
          title="Mean WER"
          value={d?.mean_wer != null ? `${(d.mean_wer * 100).toFixed(1)}%` : "--"}
          subtitle="Pipeline B only"
          trend={d?.mean_wer != null ? (d.mean_wer <= 0.1 ? "up" : d.mean_wer <= 0.3 ? "neutral" : "down") : "neutral"}
        />
        <StatsCard
          title="Mean Latency"
          value={d?.mean_latency_ms != null ? `${Math.round(d.mean_latency_ms)}ms` : "--"}
          subtitle="End-to-end"
          trend="neutral"
        />
      </div>

      {/* AI Insights Panel */}
      {hasData && <AIInsightsPanel />}

      {!hasData ? (
        <EmptyState />
      ) : (
        <>
          {/* Row 1: SNR curve + Noise comparison */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {d.accuracy_by_snr ? (
              <AccuracyBySNR data={d.accuracy_by_snr} />
            ) : (
              <ChartCard title="Accuracy vs SNR" subtitle="Run a sweep with multiple SNR values to see this chart">
                <div className="h-64 flex items-center justify-center text-gray-300 text-sm">
                  Need multiple SNR values in sweep
                </div>
              </ChartCard>
            )}

            {d.accuracy_by_noise ? (
              <NoiseComparison data={d.accuracy_by_noise} />
            ) : (
              <ChartCard title="Performance by Noise Type" subtitle="Run a sweep with multiple noise types to see this chart">
                <div className="h-64 flex items-center justify-center text-gray-300 text-sm">
                  Need multiple noise types in sweep
                </div>
              </ChartCard>
            )}
          </div>

          {/* Row 2: Echo heatmap + Latency */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {d.echo_heatmap ? (
              <EchoHeatmap data={d.echo_heatmap} />
            ) : (
              <ChartCard title="Echo Tolerance Heatmap" subtitle="Run a sweep with multiple echo parameters to see this chart">
                <div className="h-48 flex items-center justify-center text-gray-300 text-sm">
                  Need multiple delay/gain values in sweep
                </div>
              </ChartCard>
            )}

            {d.latency_by_backend ? (
              <LatencyChart data={d.latency_by_backend} />
            ) : (
              <ChartCard title="Latency by Backend" subtitle="Latency data not yet available">
                <div className="h-48 flex items-center justify-center text-gray-300 text-sm">
                  Run tests to collect latency data
                </div>
              </ChartCard>
            )}
          </div>

          {/* Row 3: Backend comparison + Parameter effects */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {d.accuracy_by_backend ? (
              <BackendComparison data={d.accuracy_by_backend} />
            ) : (
              <ChartCard title="LLM Backend Comparison" subtitle="Run a sweep with multiple backends to see this chart">
                <div className="h-64 flex items-center justify-center text-gray-300 text-sm">
                  Need multiple LLM backends in sweep
                </div>
              </ChartCard>
            )}

            {d.parameter_effects ? (
              <ParameterEffects data={d.parameter_effects} />
            ) : (
              <ChartCard title="Parameter Impact (ANOVA)" subtitle="Statistical analysis of parameter effects">
                <div className="h-64 flex items-center justify-center text-gray-300 text-sm">
                  Need varied parameters for ANOVA
                </div>
              </ChartCard>
            )}
          </div>

          {/* Row 4: WER charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {d.wer_by_snr && d.wer_by_snr.length > 1 ? (
              <WERBySNR data={d.wer_by_snr} />
            ) : (
              <ChartCard title="Word Error Rate vs SNR" subtitle="Run Pipeline B (ASR) tests with multiple SNR values">
                <div className="h-64 flex items-center justify-center text-gray-300 text-sm">
                  Requires Pipeline B (asr_text) with multiple SNR values
                </div>
              </ChartCard>
            )}

            {d.wer_by_backend && d.wer_by_backend.length > 0 ? (
              <WERByBackend data={d.wer_by_backend} />
            ) : (
              <ChartCard title="Word Error Rate by Backend" subtitle="Run Pipeline B (ASR) tests to see WER per backend">
                <div className="h-64 flex items-center justify-center text-gray-300 text-sm">
                  Requires Pipeline B (asr_text) tests
                </div>
              </ChartCard>
            )}
          </div>

          {/* Row 5: Task completion rate history */}
          {d.run_history && d.run_history.length > 1 && (
            <TaskCompletionHistory data={d.run_history} />
          )}

          {/* Row 6: Voice provider + Corpus category */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {d.accuracy_by_voice_provider && d.accuracy_by_voice_provider.length > 0 ? (
              <VoiceProviderComparison data={d.accuracy_by_voice_provider} />
            ) : (
              <ChartCard title="Voice Provider Comparison" subtitle="Run tests with multiple voice providers to see this chart">
                <div className="h-64 flex items-center justify-center text-gray-300 text-sm">
                  Need multiple voice providers in sweep
                </div>
              </ChartCard>
            )}

            {d.accuracy_by_corpus_category && d.accuracy_by_corpus_category.length > 0 ? (
              <CorpusCategoryChart data={d.accuracy_by_corpus_category} />
            ) : (
              <ChartCard title="Performance by Corpus Category" subtitle="Run tests with multiple corpus categories to see this chart">
                <div className="h-64 flex items-center justify-center text-gray-300 text-sm">
                  Need multiple corpus categories in sweep
                </div>
              </ChartCard>
            )}
          </div>

          {/* Recent runs table */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-700">Recent Runs</h3>
              <Link to="/runs" className="text-xs text-blue-600 hover:text-blue-800 font-medium">
                View all
              </Link>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[600px]">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-100">
                    <th className="px-5 py-2.5 font-medium">Run</th>
                    <th className="px-5 py-2.5 font-medium">Status</th>
                    <th className="px-5 py-2.5 font-medium">Progress</th>
                    <th className="px-5 py-2.5 font-medium">Pass Rate</th>
                    <th className="px-5 py-2.5 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {(!runs.data || runs.data.length === 0) ? (
                    <tr>
                      <td colSpan={5} className="px-5 py-8 text-center text-gray-400 text-xs">
                        No runs yet
                      </td>
                    </tr>
                  ) : (
                    runs.data.slice(0, 8).map((run) => {
                      const passRate =
                        run.total_cases > 0
                          ? ((run.completed_cases - run.failed_cases) / run.total_cases * 100).toFixed(0)
                          : "--";
                      return (
                        <tr key={run.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                          <td className="px-5 py-2.5 font-mono text-xs text-gray-600">
                            {run.id.slice(0, 8)}
                          </td>
                          <td className="px-5 py-2.5">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${
                                run.status === "completed"
                                  ? "bg-green-100 text-green-700"
                                  : run.status === "running"
                                    ? "bg-blue-100 text-blue-700"
                                    : run.status === "failed"
                                      ? "bg-red-100 text-red-700"
                                      : "bg-gray-100 text-gray-500"
                              }`}
                            >
                              {run.status}
                            </span>
                          </td>
                          <td className="px-5 py-2.5">
                            <div className="flex items-center gap-2">
                              <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${
                                    run.status === "completed" ? "bg-green-500" : "bg-blue-500"
                                  }`}
                                  style={{ width: `${run.progress_pct}%` }}
                                />
                              </div>
                              <span className="text-xs text-gray-400">{run.progress_pct.toFixed(0)}%</span>
                            </div>
                          </td>
                          <td className="px-5 py-2.5 text-xs font-medium">
                            {passRate !== "--" ? `${passRate}%` : "--"}
                          </td>
                          <td className="px-5 py-2.5">
                            <Link
                              to={run.status === "running" ? `/runs/${run.id}` : `/results/${run.id}`}
                              className="text-blue-600 hover:text-blue-800 text-xs font-medium"
                            >
                              {run.status === "running" ? "Monitor" : "View"}
                            </Link>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
