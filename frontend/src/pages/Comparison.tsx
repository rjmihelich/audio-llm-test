import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { fetchDashboard, type DashboardResponse } from "../api/client";

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16"];

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

// ---------------------------------------------------------------------------
// LLM × Noise heatmap (pass rate)
// ---------------------------------------------------------------------------
function LLMNoiseHeatmap({
  data,
}: {
  data: NonNullable<DashboardResponse["llm_noise_heatmap"]>;
}) {
  return (
    <ChartCard
      title="LLM Backend × Noise Condition — Pass Rate"
      subtitle="Pass rate for each LLM backend under each noise type"
      className="col-span-full"
    >
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="px-3 py-2 text-left text-gray-500 font-medium">Backend \ Noise</th>
              {data.col_labels.map((col) => (
                <th key={col} className="px-3 py-2 text-center text-gray-500 font-medium">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.row_labels.map((backend, ri) => (
              <tr key={backend} className="border-t border-gray-100">
                <td className="px-3 py-2 font-medium text-gray-700">{backend}</td>
                {data.col_labels.map((_, ci) => {
                  const val = data.values[ri][ci];
                  const bg =
                    val !== null
                      ? val >= 0.7
                        ? `rgba(16, 185, 129, ${Math.min(val, 1) * 0.6 + 0.15})`
                        : val >= 0.4
                          ? `rgba(245, 158, 11, ${val * 0.5 + 0.2})`
                          : `rgba(239, 68, 68, ${(1 - val) * 0.4 + 0.2})`
                      : "#f9fafb";
                  return (
                    <td
                      key={ci}
                      className="px-3 py-2.5 text-center font-mono font-medium"
                      style={{ backgroundColor: bg }}
                    >
                      {val !== null ? `${(val * 100).toFixed(0)}%` : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* Legend */}
      <div className="flex items-center gap-4 mt-3 px-1 text-xs text-gray-500">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded" style={{ background: "rgba(16, 185, 129, 0.6)" }} />
          ≥ 70%
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded" style={{ background: "rgba(245, 158, 11, 0.5)" }} />
          40–70%
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded" style={{ background: "rgba(239, 68, 68, 0.5)" }} />
          &lt; 40%
        </span>
      </div>
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// WER by backend broken down by SNR — grouped bar chart
// ---------------------------------------------------------------------------
function WERByBackendSNR({ data }: { data: Array<Record<string, unknown>> }) {
  // Pivot: rows = snr_db values, cols = backends
  const backends = [...new Set(data.map((d) => String(d.backend)))];
  const snrValues = [...new Set(data.map((d) => Number(d.snr_db)))].sort((a, b) => a - b);

  const chartData = snrValues.map((snr) => {
    const row: Record<string, unknown> = { snr: `${snr} dB` };
    for (const b of backends) {
      const match = data.find((d) => Number(d.snr_db) === snr && String(d.backend) === b);
      row[b] = match ? Math.round(Number(match.mean_wer) * 1000) / 10 : null;
    }
    return row;
  });

  return (
    <ChartCard
      title="WER by Backend × SNR"
      subtitle="Mean word error rate (Pipeline B) per backend, broken down by SNR"
    >
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="snr" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(val: number, name: string) => [`${val}%`, name]} />
          <Legend verticalAlign="top" height={36} />
          {backends.map((b, i) => (
            <Bar key={b} dataKey={b} fill={COLORS[i % COLORS.length]} radius={[3, 3, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// Pass rate by accent per backend — grouped bar chart
// ---------------------------------------------------------------------------
function AccentByBackend({ data }: { data: Array<Record<string, unknown>> }) {
  const chartData = data.map((d) => ({
    accent: String(d.group),
    passRate: Math.round(Number(d.pass_rate) * 100),
    meanScore: Math.round(Number(d.mean_score) * 100),
    count: Number(d.count),
  }));

  return (
    <ChartCard
      title="Pass Rate by Voice Accent"
      subtitle="Evaluation pass rate across accent groups (all backends combined)"
    >
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="accent" tick={{ fontSize: 10 }} angle={-15} textAnchor="end" height={50} />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(val: number, name: string) => [`${val}%`, name]} />
          <Legend verticalAlign="top" height={36} />
          <Bar dataKey="passRate" name="Pass Rate" radius={[3, 3, 0, 0]}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
          <Bar dataKey="meanScore" name="Mean Score" fill="#94a3b8" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// Latency comparison bar chart
// ---------------------------------------------------------------------------
function LatencyComparison({ data }: { data: Array<Record<string, unknown>> }) {
  const chartData = data.map((d) => ({
    backend: String(d.backend),
    mean: Math.round(Number(d.mean_ms)),
    median: Math.round(Number(d.median_ms)),
    std: Math.round(Number(d.std_ms || 0)),
  }));

  return (
    <ChartCard title="Latency Comparison" subtitle="Mean, median, and ±1 std dev response latency by backend (ms)">
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="backend" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 12 }} label={{ value: "ms", angle: -90, position: "insideLeft" }} />
          <Tooltip formatter={(val: number, name: string) => [`${val} ms`, name]} />
          <Legend verticalAlign="top" height={36} />
          <Bar dataKey="mean" name="Mean" fill="#3b82f6" radius={[3, 3, 0, 0]} />
          <Bar dataKey="median" name="Median" fill="#10b981" radius={[3, 3, 0, 0]} />
          <Bar dataKey="std" name="Std Dev" fill="#f59e0b" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// McNemar pairwise statistical comparison table
// ---------------------------------------------------------------------------
function PairwiseComparisonTable({ data }: { data: Array<Record<string, unknown>> }) {
  const rows = data.map((d) => ({
    b1: String(d.backend_1),
    b2: String(d.backend_2),
    nCommon: Number(d.n_common),
    pr1: Math.round(Number(d.pass_rate_1) * 100),
    pr2: Math.round(Number(d.pass_rate_2) * 100),
    sc1: (Number(d.mean_score_1) * 100).toFixed(1),
    sc2: (Number(d.mean_score_2) * 100).toFixed(1),
    mcnemar: Number(d.mcnemar_p_adjusted ?? d.mcnemar_p),
    wilcoxon: Number(d.wilcoxon_p_adjusted ?? d.wilcoxon_p),
    significant: Boolean(d["significant_0.05"]),
  }));

  return (
    <ChartCard
      title="Pairwise Backend Comparison (McNemar + Wilcoxon)"
      subtitle="Statistical significance tests on matched test cases — p-values Holm–Bonferroni corrected"
      className="col-span-full"
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-100">
              <th className="px-3 py-2 font-medium">Backend A</th>
              <th className="px-3 py-2 font-medium">Backend B</th>
              <th className="px-3 py-2 font-medium text-right">n (matched)</th>
              <th className="px-3 py-2 font-medium text-right">Pass A</th>
              <th className="px-3 py-2 font-medium text-right">Pass B</th>
              <th className="px-3 py-2 font-medium text-right">Score A</th>
              <th className="px-3 py-2 font-medium text-right">Score B</th>
              <th className="px-3 py-2 font-medium text-right">McNemar p</th>
              <th className="px-3 py-2 font-medium text-right">Wilcoxon p</th>
              <th className="px-3 py-2 font-medium">Significant?</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/50">
                <td className="px-3 py-2 font-medium text-gray-800">{r.b1}</td>
                <td className="px-3 py-2 font-medium text-gray-800">{r.b2}</td>
                <td className="px-3 py-2 text-right font-mono text-xs text-gray-600">{r.nCommon.toLocaleString()}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{r.pr1}%</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{r.pr2}%</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{r.sc1}%</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{r.sc2}%</td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  <span className={r.mcnemar < 0.05 ? "text-red-600 font-semibold" : "text-gray-600"}>
                    {r.mcnemar < 0.001 ? "<0.001" : r.mcnemar.toFixed(3)}
                  </span>
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  <span className={r.wilcoxon < 0.05 ? "text-red-600 font-semibold" : "text-gray-600"}>
                    {r.wilcoxon < 0.001 ? "<0.001" : r.wilcoxon.toFixed(3)}
                  </span>
                </td>
                <td className="px-3 py-2">
                  {r.significant ? (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-100 text-red-700">
                      Yes (p &lt; 0.05)
                    </span>
                  ) : (
                    <span className="text-gray-400 text-xs">No</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-gray-400 mt-2 px-1">
        McNemar: binary pass/fail — Wilcoxon: continuous eval scores — only pairs with ≥10 matched cases included
      </p>
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// Parameter effects ANOVA table (duplicated here for cross-LLM context)
// ---------------------------------------------------------------------------
function ParameterEffects({ data }: { data: Record<string, unknown> }) {
  const rows = Object.entries(data)
    .map(([factor, stats]) => {
      const s = stats as Record<string, number>;
      return {
        factor,
        fStat: s.F_statistic?.toFixed(2) ?? "--",
        pValue: s.p_value,
        etaSq: s.eta_squared,
        nGroups: s.n_groups,
      };
    })
    .sort((a, b) => (b.etaSq ?? 0) - (a.etaSq ?? 0));

  return (
    <ChartCard
      title="Parameter Impact (ANOVA)"
      subtitle="Which parameters most affect evaluation scores — sorted by effect size"
      className="col-span-full"
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-100">
              <th className="px-3 py-2 font-medium">Factor</th>
              <th className="px-3 py-2 font-medium text-right">Groups</th>
              <th className="px-3 py-2 font-medium text-right">F-statistic</th>
              <th className="px-3 py-2 font-medium text-right">p-value</th>
              <th className="px-3 py-2 font-medium text-right">η² (Effect Size)</th>
              <th className="px-3 py-2 font-medium">Interpretation</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const sig = r.pValue !== undefined && r.pValue < 0.05;
              const effectLabel =
                (r.etaSq ?? 0) >= 0.14 ? "Large" : (r.etaSq ?? 0) >= 0.06 ? "Medium" : "Small";
              const effectColor =
                (r.etaSq ?? 0) >= 0.14
                  ? "text-red-600 bg-red-50"
                  : (r.etaSq ?? 0) >= 0.06
                    ? "text-amber-600 bg-amber-50"
                    : "text-gray-600 bg-gray-50";

              return (
                <tr key={r.factor} className="border-b border-gray-50 hover:bg-gray-50/50">
                  <td className="px-3 py-2 font-medium text-gray-800">{r.factor}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-gray-600">{r.nGroups}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{r.fStat}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    <span className={sig ? "text-red-600 font-semibold" : "text-gray-600"}>
                      {r.pValue !== undefined ? (r.pValue < 0.001 ? "<0.001" : r.pValue.toFixed(3)) : "--"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${effectColor}`}>
                      {effectLabel} ({((r.etaSq ?? 0) * 100).toFixed(1)}%)
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-500">
                    {sig
                      ? `Significant effect on scores (p=${r.pValue !== undefined ? r.pValue.toFixed(3) : "--"})`
                      : "No significant effect detected"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-gray-400 mt-2 px-1">
        η² interpretation: &lt;0.06 small, 0.06–0.14 medium, &gt;0.14 large effect
      </p>
    </ChartCard>
  );
}

// ---------------------------------------------------------------------------
// Placeholder card
// ---------------------------------------------------------------------------
function Placeholder({ title, message }: { title: string; message: string }) {
  return (
    <ChartCard title={title}>
      <div className="h-40 flex items-center justify-center text-gray-300 text-sm">{message}</div>
    </ChartCard>
  );
}

// ============================================================================
// Main Comparison Page
// ============================================================================

export default function Comparison() {
  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: fetchDashboard,
    refetchInterval: 30000,
  });

  const d = dashboard.data;

  if (dashboard.isLoading) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-200 rounded w-64" />
          <div className="grid grid-cols-2 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-48 bg-gray-200 rounded-xl" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  const hasData = d && d.total_cases > 0;

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Cross-LLM Comparison</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Statistical comparison across backends, noise conditions, accents, and pipeline types
        </p>
      </div>

      {!hasData ? (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-12 text-center">
          <div className="text-4xl mb-3">📊</div>
          <h3 className="text-lg font-semibold text-gray-700 mb-2">No Data Yet</h3>
          <p className="text-sm text-gray-400 max-w-md mx-auto">
            Run test sweeps with multiple LLM backends, noise conditions, and voice types to see comparison charts.
          </p>
        </div>
      ) : (
        <>
          {/* Row 1: LLM × noise heatmap — full width */}
          {d.llm_noise_heatmap ? (
            <LLMNoiseHeatmap data={d.llm_noise_heatmap} />
          ) : (
            <Placeholder
              title="LLM Backend × Noise Condition Heatmap"
              message="Run a sweep with multiple backends AND multiple noise types to see this chart"
            />
          )}

          {/* Row 2: WER by backend × SNR + Latency */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {d.wer_by_backend_snr && d.wer_by_backend_snr.length > 0 ? (
              <WERByBackendSNR data={d.wer_by_backend_snr} />
            ) : (
              <Placeholder
                title="WER by Backend × SNR"
                message="Requires Pipeline B (asr_text) runs with multiple backends and SNR values"
              />
            )}

            {d.latency_by_backend && d.latency_by_backend.length > 0 ? (
              <LatencyComparison data={d.latency_by_backend} />
            ) : (
              <Placeholder
                title="Latency Comparison"
                message="Run tests to collect latency data"
              />
            )}
          </div>

          {/* Row 3: Accent breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {d.accuracy_by_accent && d.accuracy_by_accent.length > 0 ? (
              <AccentByBackend data={d.accuracy_by_accent} />
            ) : (
              <Placeholder
                title="Pass Rate by Voice Accent"
                message="Run tests with multiple voice accents to see this chart"
              />
            )}

            {d.accuracy_by_voice_gender && d.accuracy_by_voice_gender.length > 0 ? (
              <ChartCard title="Pass Rate by Voice Gender" subtitle="Evaluation pass rate by speaker gender">
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart
                    data={d.accuracy_by_voice_gender.map((d) => ({
                      gender: String(d.group),
                      passRate: Math.round(Number(d.pass_rate) * 100),
                      meanScore: Math.round(Number(d.mean_score) * 100),
                    }))}
                    margin={{ top: 10, right: 20, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="gender" tick={{ fontSize: 12 }} />
                    <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} />
                    <Tooltip formatter={(val: number, name: string) => [`${val}%`, name]} />
                    <Legend verticalAlign="top" height={36} />
                    <Bar dataKey="passRate" name="Pass Rate" fill="#3b82f6" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="meanScore" name="Mean Score" fill="#10b981" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
            ) : (
              <Placeholder
                title="Pass Rate by Voice Gender"
                message="Run tests with multiple voice genders to see this chart"
              />
            )}
          </div>

          {/* Row 4: McNemar pairwise comparison table — full width */}
          {d.backend_comparison && d.backend_comparison.length > 0 ? (
            <PairwiseComparisonTable data={d.backend_comparison} />
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-8 text-center">
              <p className="text-sm text-gray-400">
                Pairwise McNemar comparison requires ≥10 matched test cases between at least 2 backends.
              </p>
            </div>
          )}

          {/* Row 5: ANOVA parameter effects — full width */}
          {d.parameter_effects ? (
            <ParameterEffects data={d.parameter_effects} />
          ) : (
            <Placeholder
              title="Parameter Impact (ANOVA)"
              message="Run sweeps with varied parameters to see statistical effect sizes"
            />
          )}
        </>
      )}
    </div>
  );
}
