import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
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
  type StatsResponse,
  type ResultResponse,
} from "../api/client";
import StatsCard from "../components/StatsCard";

type Tab = "charts" | "table" | "export";

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
  const [tab, setTab] = useState<Tab>("charts");

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

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">
        Results{" "}
        <span className="text-sm font-normal text-gray-400 font-mono">
          {id?.slice(0, 12)}
        </span>
      </h2>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatsCard
          title="Total Tests"
          value={s?.total_tests ?? "--"}
          trend="neutral"
        />
        <StatsCard
          title="Completed"
          value={s?.completed ?? "--"}
          subtitle={`${s?.errors ?? 0} errors`}
          trend="neutral"
        />
        <StatsCard
          title="Pass Rate"
          value={
            s?.overall_pass_rate != null
              ? `${(s.overall_pass_rate * 100).toFixed(1)}%`
              : "--"
          }
          trend={
            s?.overall_pass_rate != null
              ? s.overall_pass_rate >= 0.8
                ? "up"
                : "down"
              : "neutral"
          }
        />
        <StatsCard
          title="Mean Latency"
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
        {(["charts", "table", "export"] as Tab[]).map((t) => (
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

      {tab === "charts" && <ChartsTab stats={s} results={results.data} />}
      {tab === "table" && <TableTab results={results.data ?? []} runId={id!} />}
      {tab === "export" && <ExportTab runId={id!} />}
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
  // Build accuracy-by-SNR chart data from stats or results
  const chartData = buildAccuracyBySNR(stats, results);
  const backends = [
    ...new Set(results?.map((r) => r.llm_backend) ?? []),
  ];

  return (
    <div className="space-y-6">
      {/* Accuracy vs SNR */}
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
                label={{
                  value: "Accuracy",
                  angle: -90,
                  position: "insideLeft",
                }}
              />
              <Tooltip
                formatter={(v: number) => `${(v * 100).toFixed(1)}%`}
              />
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
            No data available for charting.
          </p>
        )}
      </div>

      {/* Heatmap placeholder */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">
          Parameter Heatmap
        </h3>
        <div className="flex items-center justify-center h-48 bg-gray-50 rounded-lg border border-dashed border-gray-200">
          <span className="text-sm text-gray-400">
            Heatmap visualization -- select row/col parameters to render
          </span>
        </div>
      </div>
    </div>
  );
}

function buildAccuracyBySNR(
  stats?: StatsResponse,
  results?: ResultResponse[]
): Array<Record<string, unknown>> {
  // If stats.accuracy_by_snr is populated, use that
  if (stats?.accuracy_by_snr?.length) {
    return stats.accuracy_by_snr;
  }
  // Otherwise, compute from raw results
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
// Table Tab
// ---------------------------------------------------------------------------

function TableTab({
  results,
  runId,
}: {
  results: ResultResponse[];
  runId: string;
}) {
  const [page, setPage] = useState(0);
  const [backendFilter, setBackendFilter] = useState("");
  const pageSize = 25;

  const backends = [...new Set(results.map((r) => r.llm_backend))];
  const filtered = backendFilter
    ? results.filter((r) => r.llm_backend === backendFilter)
    : results;
  const paged = filtered.slice(page * pageSize, (page + 1) * pageSize);
  const totalPages = Math.ceil(filtered.length / pageSize);

  return (
    <div>
      <div className="flex gap-3 mb-4">
        <select
          value={backendFilter}
          onChange={(e) => {
            setBackendFilter(e.target.value);
            setPage(0);
          }}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">All Backends</option>
          {backends.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-100">
              <th className="px-4 py-3 font-medium">Case</th>
              <th className="px-4 py-3 font-medium">Backend</th>
              <th className="px-4 py-3 font-medium">Pipeline</th>
              <th className="px-4 py-3 font-medium">SNR</th>
              <th className="px-4 py-3 font-medium">Delay</th>
              <th className="px-4 py-3 font-medium">Score</th>
              <th className="px-4 py-3 font-medium">Passed</th>
              <th className="px-4 py-3 font-medium">Latency</th>
            </tr>
          </thead>
          <tbody>
            {paged.map((r, i) => (
              <tr
                key={`${r.test_case_id}-${i}`}
                className="border-b border-gray-50 hover:bg-gray-50"
              >
                <td className="px-4 py-2 font-mono text-xs text-gray-600">
                  {r.test_case_id.slice(0, 8)}
                </td>
                <td className="px-4 py-2 text-gray-700">{r.llm_backend}</td>
                <td className="px-4 py-2 text-gray-600">{r.pipeline_type}</td>
                <td className="px-4 py-2 text-gray-600">{r.snr_db} dB</td>
                <td className="px-4 py-2 text-gray-600">{r.delay_ms}ms</td>
                <td className="px-4 py-2 text-gray-600">
                  {r.eval_score != null ? r.eval_score.toFixed(2) : "--"}
                </td>
                <td className="px-4 py-2">
                  {r.eval_passed == null ? (
                    <span className="text-gray-400">--</span>
                  ) : r.eval_passed ? (
                    <span className="text-green-600 font-medium">pass</span>
                  ) : (
                    <span className="text-red-600 font-medium">fail</span>
                  )}
                </td>
                <td className="px-4 py-2 text-gray-600 tabular-nums">
                  {r.total_latency_ms != null
                    ? `${r.total_latency_ms.toFixed(0)}ms`
                    : "--"}
                </td>
              </tr>
            ))}
            {paged.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                  No results found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <span className="text-sm text-gray-500">
            Page {page + 1} of {totalPages} ({filtered.length} results)
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg disabled:opacity-50 hover:bg-gray-50"
            >
              Previous
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg disabled:opacity-50 hover:bg-gray-50"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Export Tab
// ---------------------------------------------------------------------------

function ExportTab({ runId }: { runId: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 max-w-md">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">
        Export Results
      </h3>
      <div className="space-y-3">
        {(["csv", "json", "parquet"] as const).map((fmt) => (
          <a
            key={fmt}
            href={getExportUrl(runId, fmt)}
            download
            className="flex items-center justify-between px-4 py-3 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <div>
              <p className="text-sm font-medium text-gray-900 uppercase">
                {fmt}
              </p>
              <p className="text-xs text-gray-500">
                {fmt === "csv"
                  ? "Comma-separated values"
                  : fmt === "json"
                    ? "JSON array"
                    : "Apache Parquet"}
              </p>
            </div>
            <span className="text-gray-400 text-lg">{"\u2193"}</span>
          </a>
        ))}
      </div>
    </div>
  );
}
