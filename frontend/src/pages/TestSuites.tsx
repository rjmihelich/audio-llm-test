import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  listTestSuites,
  createTestSuite,
  previewSweep,
  launchRun,
  type SweepConfigRequest,
  type SweepPreview,
} from "../api/client";

const SNR_OPTIONS = [-10, -5, 0, 5, 10, 15, 20, 30];
const NOISE_TYPES = ["white", "pink", "pink_lpf", "babble", "traffic", "silence"];
const PIPELINES = ["direct_audio", "asr_text"];
const BACKENDS = [
  "openai_gpt4o_audio",
  "gemini_2.0_flash",
  "anthropic_claude",
  "ollama_local",
];

export default function TestSuites() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const suites = useQuery({ queryKey: ["suites"], queryFn: listTestSuites });

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Test Suites</h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 transition-colors"
        >
          {showForm ? "Cancel" : "New Suite"}
        </button>
      </div>

      {showForm && (
        <NewSuiteForm
          onCreated={() => {
            setShowForm(false);
            queryClient.invalidateQueries({ queryKey: ["suites"] });
          }}
        />
      )}

      {/* Existing suites */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-100">
              <th className="px-6 py-3 font-medium">Name</th>
              <th className="px-6 py-3 font-medium">Status</th>
              <th className="px-6 py-3 font-medium">Cases</th>
              <th className="px-6 py-3 font-medium">Created</th>
              <th className="px-6 py-3 font-medium" />
            </tr>
          </thead>
          <tbody>
            {suites.data?.length === 0 && (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-gray-400">
                  No test suites yet.
                </td>
              </tr>
            )}
            {suites.data?.map((s) => (
              <SuiteRow key={s.id} suite={s} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Suite Row
// ---------------------------------------------------------------------------

function SuiteRow({ suite }: { suite: { id: string; name: string; status: string; total_cases: number; created_at: string } }) {
  const launch = useMutation({ mutationFn: () => launchRun(suite.id) });

  return (
    <tr className="border-b border-gray-50 hover:bg-gray-50">
      <td className="px-6 py-3 font-medium text-gray-900">{suite.name}</td>
      <td className="px-6 py-3">
        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
          {suite.status}
        </span>
      </td>
      <td className="px-6 py-3 text-gray-600">{suite.total_cases}</td>
      <td className="px-6 py-3 text-xs text-gray-500">{suite.created_at}</td>
      <td className="px-6 py-3 flex gap-2">
        <button
          onClick={() => launch.mutate()}
          disabled={launch.isPending}
          className="text-xs font-medium text-blue-600 hover:text-blue-800 disabled:opacity-50"
        >
          Run
        </button>
        {launch.isSuccess && (
          <Link
            to={`/runs/${launch.data.id}`}
            className="text-xs font-medium text-green-600"
          >
            Monitor
          </Link>
        )}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// New Suite Form
// ---------------------------------------------------------------------------

function NewSuiteForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [snrValues, setSnrValues] = useState<number[]>([-5, 0, 5, 10, 20]);
  const [noiseTypes, setNoiseTypes] = useState<string[]>(["pink_lpf"]);
  const [delayRange, setDelayRange] = useState<number[]>([0, 50, 100, 200]);
  const [gainRange, setGainRange] = useState<number[]>([-60, -40, -20]);
  const [pipelines, setPipelines] = useState<string[]>(["direct_audio", "asr_text"]);
  const [backends, setBackends] = useState<string[]>([]);
  const [preview, setPreview] = useState<SweepPreview | null>(null);

  function buildConfig(): SweepConfigRequest {
    return {
      name,
      description,
      snr_db_values: snrValues,
      noise_types: noiseTypes,
      echo: {
        delay_ms_values: delayRange,
        gain_db_values: gainRange,
      },
      pipelines,
      llm_backends: backends,
    };
  }

  const previewMutation = useMutation({
    mutationFn: () => previewSweep(buildConfig()),
    onSuccess: (data) => setPreview(data),
  });

  const createMutation = useMutation({
    mutationFn: () => createTestSuite(buildConfig()),
    onSuccess: () => onCreated(),
  });

  function toggleItem<T>(arr: T[], item: T, setter: (v: T[]) => void) {
    setter(arr.includes(item) ? arr.filter((x) => x !== item) : [...arr, item]);
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-5">
        New Test Suite
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Name & description */}
        <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Name
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
              placeholder="e.g. Baseline SNR Sweep"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
              placeholder="Optional description"
            />
          </div>
        </div>

        {/* SNR Values */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            SNR (dB)
          </label>
          <div className="flex flex-wrap gap-2">
            {SNR_OPTIONS.map((v) => (
              <button
                key={v}
                onClick={() => toggleItem(snrValues, v, setSnrValues)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                  snrValues.includes(v)
                    ? "bg-slate-800 text-white border-slate-800"
                    : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"
                }`}
              >
                {v} dB
              </button>
            ))}
          </div>
        </div>

        {/* Noise types */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Noise Types
          </label>
          <div className="space-y-1.5">
            {NOISE_TYPES.map((n) => (
              <label key={n} className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={noiseTypes.includes(n)}
                  onChange={() => toggleItem(noiseTypes, n, setNoiseTypes)}
                  className="rounded border-gray-300"
                />
                {n.replace("_", " ")}
              </label>
            ))}
          </div>
        </div>

        {/* Echo config */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Echo Delay (ms)
          </label>
          <div className="flex flex-wrap gap-2">
            {[0, 25, 50, 100, 150, 200, 300].map((v) => (
              <button
                key={v}
                onClick={() => toggleItem(delayRange, v, setDelayRange)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                  delayRange.includes(v)
                    ? "bg-slate-800 text-white border-slate-800"
                    : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"
                }`}
              >
                {v}ms
              </button>
            ))}
          </div>

          <label className="block text-sm font-medium text-gray-700 mt-4 mb-2">
            Echo Gain (dB)
          </label>
          <div className="flex flex-wrap gap-2">
            {[-60, -40, -20, -10, -6, -3].map((v) => (
              <button
                key={v}
                onClick={() => toggleItem(gainRange, v, setGainRange)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                  gainRange.includes(v)
                    ? "bg-slate-800 text-white border-slate-800"
                    : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"
                }`}
              >
                {v} dB
              </button>
            ))}
          </div>
        </div>

        {/* Pipelines */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Pipelines
          </label>
          <div className="space-y-1.5">
            {PIPELINES.map((p) => (
              <label key={p} className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={pipelines.includes(p)}
                  onChange={() => toggleItem(pipelines, p, setPipelines)}
                  className="rounded border-gray-300"
                />
                {p.replace("_", " ")}
              </label>
            ))}
          </div>

          <label className="block text-sm font-medium text-gray-700 mt-4 mb-2">
            LLM Backends
          </label>
          <div className="space-y-1.5">
            {BACKENDS.map((b) => (
              <label key={b} className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={backends.includes(b)}
                  onChange={() => toggleItem(backends, b, setBackends)}
                  className="rounded border-gray-300"
                />
                {b.replace(/_/g, " ")}
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* Preview & Create */}
      <div className="mt-6 flex items-center gap-3 border-t border-gray-100 pt-5">
        <button
          onClick={() => previewMutation.mutate()}
          disabled={!name || previewMutation.isPending}
          className="px-4 py-2 bg-white text-gray-700 text-sm font-medium rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          Preview
        </button>
        <button
          onClick={() => createMutation.mutate()}
          disabled={!name || createMutation.isPending}
          className="px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors"
        >
          {createMutation.isPending ? "Creating..." : "Create Suite"}
        </button>

        {preview && (
          <div className="ml-4 text-sm text-gray-600">
            <span className="font-semibold text-gray-900">
              {preview.total_cases.toLocaleString()}
            </span>{" "}
            total cases
            {preview.estimated_duration_minutes != null && (
              <span className="ml-2 text-gray-500">
                (~{preview.estimated_duration_minutes.toFixed(0)} min)
              </span>
            )}
          </div>
        )}
      </div>

      {createMutation.isError && (
        <p className="mt-3 text-sm text-red-600">
          {(createMutation.error as Error).message}
        </p>
      )}
    </div>
  );
}
