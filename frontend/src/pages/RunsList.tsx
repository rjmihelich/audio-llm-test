import { Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { listRuns, launchRun, type RunResponse } from "../api/client";

function statusColor(status: string) {
  switch (status) {
    case "completed":
      return "bg-green-100 text-green-700";
    case "running":
      return "bg-blue-100 text-blue-700";
    case "failed":
      return "bg-red-100 text-red-700";
    case "cancelled":
      return "bg-gray-100 text-gray-500";
    default:
      return "bg-yellow-100 text-yellow-700";
  }
}

function formatDate(iso: string | null) {
  if (!iso) return "--";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function duration(run: RunResponse) {
  if (!run.started_at || !run.completed_at) return "--";
  const ms = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

export default function RunsList() {
  const navigate = useNavigate();
  const { data: runs, isLoading } = useQuery({
    queryKey: ["runs"],
    queryFn: listRuns,
    refetchInterval: 5000,
  });

  const rerun = useMutation({
    mutationFn: (suiteId: string) => launchRun(suiteId),
    onSuccess: (data) => navigate(`/runs/${data.id}`),
  });

  const rerunQuick = useMutation({
    mutationFn: (suiteId: string) => launchRun(suiteId, false, 5),
    onSuccess: (data) => navigate(`/runs/${data.id}`),
  });

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-200 rounded w-48" />
          <div className="h-64 bg-gray-200 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Runs & Results</h2>
        <p className="text-sm text-gray-500 mt-1">
          View completed test runs and their results. Click a run to see detailed analysis.
        </p>
      </div>

      {(!runs || runs.length === 0) ? (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-12 text-center">
          <p className="text-gray-400 text-sm">
            No test runs yet. Go to{" "}
            <Link to="/tests" className="text-blue-600 hover:underline">
              Test Suites
            </Link>{" "}
            to create and run a test.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => (
            <div
              key={run.id}
              className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow"
            >
              <div className="p-4 sm:p-5 space-y-3 sm:space-y-0 sm:flex sm:items-center sm:gap-4">
                {/* Status dot */}
                <span
                  className={`w-3 h-3 rounded-full shrink-0 ${
                    run.status === "completed"
                      ? "bg-green-500"
                      : run.status === "running"
                        ? "bg-blue-500 animate-pulse"
                        : run.status === "failed"
                          ? "bg-red-500"
                          : "bg-gray-400"
                  }`}
                />

                {/* Run info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-900">
                      Run {run.id.slice(0, 8)}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${statusColor(run.status)}`}
                    >
                      {run.status}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 sm:gap-4 mt-1 text-xs text-gray-500">
                    <span>Started: {formatDate(run.started_at)}</span>
                    <span>Duration: {duration(run)}</span>
                    <span>Suite: {run.test_suite_id.slice(0, 8)}</span>
                  </div>
                  {run.error_message && (
                    <p className="mt-1 text-xs text-red-500 truncate max-w-lg" title={run.error_message}>
                      {run.error_message}
                    </p>
                  )}
                </div>

                {/* Stats */}
                <div className="flex flex-wrap items-center gap-3 sm:gap-6 sm:shrink-0">
                  <div className="text-center">
                    <p className="text-lg font-bold text-gray-900">
                      {run.completed_cases}
                      <span className="text-sm font-normal text-gray-400">/{run.total_cases}</span>
                    </p>
                    <p className="text-[10px] text-gray-400 uppercase">Cases</p>
                  </div>

                  <div className="text-center">
                    <p className={`text-lg font-bold ${run.failed_cases > 0 ? "text-red-600" : "text-green-600"}`}>
                      {run.total_cases > 0
                        ? `${(((run.completed_cases - run.failed_cases) / run.total_cases) * 100).toFixed(0)}%`
                        : "--"}
                    </p>
                    <p className="text-[10px] text-gray-400 uppercase">Pass Rate</p>
                  </div>

                  {/* Progress bar */}
                  <div className="w-full sm:w-24">
                    <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          run.status === "completed" ? "bg-green-500" : "bg-blue-500"
                        }`}
                        style={{ width: `${run.progress_pct}%` }}
                      />
                    </div>
                    <p className="text-[10px] text-gray-400 mt-0.5 text-center">
                      {run.progress_pct.toFixed(0)}%
                    </p>
                  </div>

                  {/* Action buttons */}
                  <div className="flex flex-wrap gap-1.5">
                    {run.status === "running" && (
                      <Link
                        to={`/runs/${run.id}`}
                        className="px-3 py-1.5 text-xs font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                      >
                        Monitor
                      </Link>
                    )}
                    {run.status === "completed" && (
                      <Link
                        to={`/results/${run.id}`}
                        className="px-3 py-1.5 text-xs font-medium bg-slate-800 text-white rounded-lg hover:bg-slate-700"
                      >
                        Results
                      </Link>
                    )}
                    {run.status === "failed" && (
                      <Link
                        to={`/results/${run.id}`}
                        className="px-3 py-1.5 text-xs font-medium bg-red-600 text-white rounded-lg hover:bg-red-700"
                      >
                        Details
                      </Link>
                    )}
                    {(run.status === "completed" || run.status === "failed") && (
                      <>
                        <button
                          onClick={() => rerunQuick.mutate(run.test_suite_id)}
                          disabled={rerunQuick.isPending}
                          className="px-2.5 py-1.5 text-xs font-medium text-amber-700 bg-amber-100 rounded-lg hover:bg-amber-200 disabled:opacity-50"
                          title="Re-run 5 random cases"
                        >
                          Re-test
                        </button>
                        <button
                          onClick={() => rerun.mutate(run.test_suite_id)}
                          disabled={rerun.isPending}
                          className="px-2.5 py-1.5 text-xs font-medium text-green-700 bg-green-100 rounded-lg hover:bg-green-200 disabled:opacity-50"
                          title="Re-run entire suite"
                        >
                          Re-run
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
