import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listTestSuites, listRuns } from "../api/client";
import StatsCard from "../components/StatsCard";

const statusBadge: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  running: "bg-blue-100 text-blue-800",
  completed: "bg-green-100 text-green-800",
  cancelled: "bg-gray-100 text-gray-600",
  failed: "bg-red-100 text-red-800",
};

export default function Dashboard() {
  const suites = useQuery({ queryKey: ["suites"], queryFn: listTestSuites });
  const runs = useQuery({ queryKey: ["runs"], queryFn: listRuns });

  const totalSuites = suites.data?.length ?? 0;
  const totalRuns = runs.data?.length ?? 0;

  const latestCompleted = runs.data?.find((r) => r.status === "completed");
  const passRate = latestCompleted
    ? (
        ((latestCompleted.completed_cases - latestCompleted.failed_cases) /
          Math.max(latestCompleted.total_cases, 1)) *
        100
      ).toFixed(1) + "%"
    : "--";

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Dashboard</h2>

      {/* Stats cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatsCard title="Total Suites" value={totalSuites} trend="neutral" />
        <StatsCard title="Total Runs" value={totalRuns} trend="neutral" />
        <StatsCard
          title="Latest Pass Rate"
          value={passRate}
          subtitle="Most recent completed run"
          trend={passRate !== "--" ? "up" : "neutral"}
        />
        <StatsCard
          title="Avg Latency"
          value="--"
          subtitle="ms across all runs"
          trend="neutral"
        />
      </div>

      {/* Recent runs */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm mb-8">
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-700">Recent Runs</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100">
                <th className="px-6 py-3 font-medium">ID</th>
                <th className="px-6 py-3 font-medium">Suite</th>
                <th className="px-6 py-3 font-medium">Status</th>
                <th className="px-6 py-3 font-medium">Progress</th>
                <th className="px-6 py-3 font-medium">Started</th>
                <th className="px-6 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {runs.data?.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-400">
                    No runs yet. Create a test suite to get started.
                  </td>
                </tr>
              )}
              {runs.data?.slice(0, 10).map((run) => (
                <tr key={run.id} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-6 py-3 font-mono text-xs text-gray-600">
                    {run.id.slice(0, 8)}
                  </td>
                  <td className="px-6 py-3 text-gray-700">
                    {run.test_suite_id.slice(0, 8)}
                  </td>
                  <td className="px-6 py-3">
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                        statusBadge[run.status] ?? "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {run.status}
                    </span>
                  </td>
                  <td className="px-6 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500 rounded-full"
                          style={{ width: `${run.progress_pct}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-500">
                        {run.progress_pct.toFixed(0)}%
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-3 text-xs text-gray-500">
                    {run.started_at ?? "--"}
                  </td>
                  <td className="px-6 py-3">
                    <Link
                      to={
                        run.status === "running"
                          ? `/runs/${run.id}`
                          : `/results/${run.id}`
                      }
                      className="text-blue-600 hover:text-blue-800 text-xs font-medium"
                    >
                      {run.status === "running" ? "Monitor" : "View"}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Quick actions */}
      <div className="flex gap-3">
        <Link
          to="/tests"
          className="px-5 py-2.5 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 transition-colors"
        >
          New Test Suite
        </Link>
        <Link
          to="/tests"
          className="px-5 py-2.5 bg-white text-gray-700 text-sm font-medium rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors"
        >
          View Results
        </Link>
      </div>
    </div>
  );
}
