import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  listTelephonySuites,
  createTestSuite,
  deleteTestSuite,
  previewSweep,
  launchRun,
  fetchKeyStatus,
  fetchOllamaModels,
  fetchAudioSources,
  listCars,
  getCarNoiseTypes,
  type SweepConfigRequest,
  type SweepPreview,
  type KeyStatusResponse,
} from "../api/client";

const NOISE_LEVEL_OPTIONS = [-40, -30, -20, -10, -6, 0, 6, 10];
const SPEECH_LEVEL_OPTIONS = [-60, -50, -40, -30, -20, -10, 0, 10, 20];
const NOISE_SOURCES = [
  { key: "road_noise", label: "Road Noise", desc: "LPF pink — engine, tires, wind" },
  { key: "hvac_fan", label: "HVAC Fan", desc: "Blade hum + airflow turbulence" },
  { key: "secondary_voice", label: "Secondary Voice", desc: "Random competing talker" },
  { key: "babble", label: "Babble", desc: "6 overlapping talkers" },
] as const;
const INTERFERER_NOISE_TYPES = new Set(["secondary_voice", "babble"]);

const BT_CODECS = [
  { key: "cvsd", label: "CVSD (8 kHz)" },
  { key: "msbc", label: "mSBC (16 kHz)" },
  { key: "none", label: "None" },
];
const AGC_PRESETS = [
  { key: "off", label: "Off" },
  { key: "mild", label: "Mild" },
  { key: "aggressive", label: "Aggressive" },
];

interface BackendDef {
  key: string;
  label: string;
  paid: boolean;
  keyField: keyof KeyStatusResponse | null;
  pipeline: "direct_audio" | "asr_text" | "both";
}

const CLOUD_BACKENDS: BackendDef[] = [
  { key: "openai:gpt-4o-audio-preview", label: "OpenAI · GPT-4o Audio", paid: true, keyField: "openai", pipeline: "both" },
  { key: "openai-realtime:gpt-4o-realtime-preview", label: "OpenAI · Realtime API", paid: true, keyField: "openai", pipeline: "both" },
  { key: "openai:gpt-4o-mini", label: "OpenAI · GPT-4o Mini", paid: true, keyField: "openai", pipeline: "asr_text" },
  { key: "gemini:gemini-2.0-flash", label: "Google · Gemini 2.0 Flash", paid: true, keyField: "google", pipeline: "both" },
  { key: "anthropic:claude-haiku-4-5-20251001", label: "Anthropic · Claude Haiku", paid: true, keyField: "anthropic", pipeline: "asr_text" },
];

// ---------------------------------------------------------------------------
// Shared UI components
// ---------------------------------------------------------------------------

function PillSelect({ options, selected, onToggle, format }: {
  options: (number | string)[];
  selected: (number | string)[];
  onToggle: (v: number | string) => void;
  format?: (v: number | string) => string;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((v) => (
        <button
          key={v}
          onClick={() => onToggle(v)}
          className={`px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors ${
            selected.includes(v)
              ? "bg-slate-800 text-white border-slate-800"
              : "bg-white text-gray-500 border-gray-200 hover:border-gray-400"
          }`}
        >
          {format ? format(v) : String(v)}
        </button>
      ))}
    </div>
  );
}

function SectionHeader({ title, count }: { title: string; count?: number }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{title}</h4>
      {count !== undefined && (
        <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-full">{count} selected</span>
      )}
    </div>
  );
}

function FilterColumn({ label, items, selected, onToggle, onClear, formatLabel }: {
  label: string;
  items: Record<string, number>;
  selected: string[];
  onToggle: (v: string) => void;
  onClear: () => void;
  formatLabel?: (v: string) => string;
}) {
  const sorted = Object.entries(items).sort(([, a], [, b]) => b - a);
  return (
    <div>
      <p className="text-[10px] font-medium text-gray-500 mb-1.5">{label}</p>
      <div className="space-y-1 max-h-48 overflow-y-auto">
        {sorted.map(([key, count]) => (
          <label key={key} className="flex items-center gap-2 text-xs text-gray-700 cursor-pointer">
            <input
              type="checkbox"
              checked={selected.includes(key)}
              onChange={() => onToggle(key)}
              className="rounded border-gray-300 h-3.5 w-3.5 shrink-0"
            />
            <span className="flex-1 min-w-0">{formatLabel ? formatLabel(key) : key}</span>
            <span className="text-[10px] text-gray-400 tabular-nums shrink-0">{count.toLocaleString()}</span>
          </label>
        ))}
      </div>
      {selected.length > 0 && (
        <button onClick={onClear} className="mt-1 text-[10px] text-blue-500 hover:text-blue-700">clear</button>
      )}
    </div>
  );
}

function CostBadge({ paid, hasKey }: { paid: boolean; hasKey: boolean }) {
  if (!paid) {
    return (
      <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-green-100 text-green-700">
        FREE
      </span>
    );
  }
  return (
    <span
      className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-bold ${
        hasKey ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-600"
      }`}
    >
      [$]
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function TelephonySuites() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [expandedSuiteId, setExpandedSuiteId] = useState<string | null>(null);

  const suites = useQuery({ queryKey: ["telephonySuites"], queryFn: listTelephonySuites });

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Telephony Test Suites</h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 transition-colors"
        >
          {showForm ? "Cancel" : "New Suite"}
        </button>
      </div>

      {showForm && (
        <NewTelephonyForm
          onCreated={() => {
            setShowForm(false);
            queryClient.invalidateQueries({ queryKey: ["telephonySuites"] });
          }}
        />
      )}

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
                  No telephony test suites yet.
                </td>
              </tr>
            )}
            {suites.data?.map((s) => (
              <SuiteRow
                key={s.id}
                suite={s}
                expanded={expandedSuiteId === s.id}
                onToggle={() => setExpandedSuiteId(expandedSuiteId === s.id ? null : s.id)}
              />
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

function SuiteRow({
  suite,
  expanded,
  onToggle,
}: {
  suite: { id: string; name: string; description: string; status: string; total_cases: number; created_at: string };
  expanded: boolean;
  onToggle: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const launch = useMutation({
    mutationFn: (sampleSize?: number) => launchRun(suite.id, false, sampleSize),
    onSuccess: (data) => navigate(`/runs/${data.id}`),
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteTestSuite(suite.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["telephonySuites"] }),
  });

  return (
    <>
      <tr className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer" onClick={onToggle}>
        <td className="px-6 py-3 font-medium text-gray-900">
          <span className="mr-2 text-gray-400 text-xs">{expanded ? "▼" : "▶"}</span>
          {suite.name}
        </td>
        <td className="px-6 py-3">
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
            suite.status === "ready" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
          }`}>
            {suite.status}
          </span>
        </td>
        <td className="px-6 py-3 text-gray-600">{suite.total_cases}</td>
        <td className="px-6 py-3 text-xs text-gray-500">{suite.created_at}</td>
        <td className="px-6 py-3">
          <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
            {suite.status === "ready" && (
              <>
                <button
                  onClick={() => launch.mutate(5)}
                  disabled={launch.isPending}
                  className="px-2.5 py-1 text-xs font-medium text-amber-700 bg-amber-100 rounded hover:bg-amber-200 disabled:opacity-50 transition-colors"
                  title="Run 5 random cases to verify setup"
                >
                  {launch.isPending ? "..." : "Quick Test"}
                </button>
                <button
                  onClick={() => launch.mutate(undefined)}
                  disabled={launch.isPending}
                  className="px-2.5 py-1 text-xs font-medium text-white bg-green-600 rounded hover:bg-green-700 disabled:opacity-50 transition-colors"
                >
                  {launch.isPending ? "..." : "Run All"}
                </button>
              </>
            )}
            <button
              onClick={() => {
                if (window.confirm(`Delete suite "${suite.name}" and all its test cases?`)) {
                  deleteMut.mutate();
                }
              }}
              disabled={deleteMut.isPending}
              className="px-1.5 py-0.5 text-xs font-medium text-red-500 hover:text-red-700 hover:bg-red-50 rounded disabled:opacity-50 transition-colors"
              title="Delete suite"
            >
              ✕
            </button>
          </div>
        </td>
      </tr>

      {expanded && (
        <tr className="border-b border-gray-50 bg-gray-50/50">
          <td colSpan={5} className="px-6 py-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1">Total Cases</p>
                <p className="text-gray-900 font-semibold">{suite.total_cases}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1">Status</p>
                <p className="text-gray-900">{suite.status}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1">Created</p>
                <p className="text-gray-900">{suite.created_at}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1">Description</p>
                <p className="text-gray-900">{suite.description || "—"}</p>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                onClick={() => launch.mutate(5)}
                disabled={launch.isPending || suite.status !== "ready"}
                className="px-4 py-2 text-sm font-medium text-amber-700 bg-amber-100 rounded-lg hover:bg-amber-200 disabled:opacity-50 transition-colors"
              >
                {launch.isPending ? "..." : "Quick Test (5 cases)"}
              </button>
              <button
                onClick={() => launch.mutate(undefined)}
                disabled={launch.isPending || suite.status !== "ready"}
                className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
              >
                {launch.isPending ? "Launching..." : "Launch Full Run"}
              </button>
              {launch.isError && (
                <span className="text-xs text-red-600">{(launch.error as Error).message}</span>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// New Telephony Suite Form
// ---------------------------------------------------------------------------

function NewTelephonyForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  // Audio source filters
  const [selectedProviders, setSelectedProviders] = useState<string[]>([]);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [selectedLanguages, setSelectedLanguages] = useState<string[]>([]);
  const [selectedGenders, setSelectedGenders] = useState<string[]>([]);

  // LLM backends
  const [backends, setBackends] = useState<string[]>([]);
  const [maxSamples, setMaxSamples] = useState<number | null>(null);
  const [selectedCar, setSelectedCar] = useState<string>("");
  const [carNoiseTypes, setCarNoiseTypes] = useState<string[]>([]);

  // Audio degradation (shared with LLM suites)
  const [noiseLevels, setNoiseLevels] = useState<number[]>([-20, -10, 0]);
  const [speechLevels, setSpeechLevels] = useState<number[]>([0]);
  const [noiseTypes, setNoiseTypes] = useState<string[]>(["road_noise"]);
  const [interfererLevels, setInterfererLevels] = useState<number[]>([0]);
  const [delayRange, setDelayRange] = useState<number[]>([0]);
  const [gainRange, setGainRange] = useState<number[]>([-60]);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Telephony-specific params
  const [btCodecs, setBtCodecs] = useState<string[]>(["cvsd"]);
  const [agcPresets, setAgcPresets] = useState<string[]>(["off"]);
  const [aecEnabled, setAecEnabled] = useState(false);
  const [aecSuppression, setAecSuppression] = useState(-25);
  const [aecNld, setAecNld] = useState(0.3);
  const [networkEnabled, setNetworkEnabled] = useState(false);
  const [packetLoss, setPacketLoss] = useState(2);
  const [packetLossPattern, setPacketLossPattern] = useState("random");
  const [jitterMs, setJitterMs] = useState(0);
  const [codecSwitching, setCodecSwitching] = useState(false);

  // Far-end / 2-way conversation params
  const [farEndEnabled, setFarEndEnabled] = useState(false);
  const [farEndLevels, setFarEndLevels] = useState<number[]>([0]);
  const [farEndOffsets, setFarEndOffsets] = useState<number[]>([0]);

  const [preview, setPreview] = useState<SweepPreview | null>(null);

  const keyStatus = useQuery({ queryKey: ["keyStatus"], queryFn: fetchKeyStatus });
  const ollamaStatus = useQuery({ queryKey: ["ollamaModels"], queryFn: fetchOllamaModels, refetchInterval: 30000 });
  const audioSources = useQuery({ queryKey: ["audioSources"], queryFn: fetchAudioSources });
  const keys = keyStatus.data;

  const ollamaBackends: BackendDef[] = (ollamaStatus.data?.models ?? []).map((m) => ({
    key: `ollama:${m.name}`,
    label: `Ollama · ${m.name}${m.parameter_size ? ` (${m.parameter_size})` : ""}`,
    paid: false,
    keyField: "ollama" as keyof KeyStatusResponse,
    pipeline: "asr_text" as const,
  }));

  const carsQuery = useQuery({ queryKey: ["cars"], queryFn: listCars });

  const hasInterferer = noiseTypes.some((n) => INTERFERER_NOISE_TYPES.has(n));

  async function handleCarChange(carId: string) {
    setSelectedCar(carId);
    if (carId) {
      const types = await getCarNoiseTypes(carId);
      setCarNoiseTypes(types);
    } else {
      setCarNoiseTypes([]);
    }
  }

  function hasKey(field: keyof KeyStatusResponse | null): boolean {
    if (!field || !keys) return true;
    return keys[field] ?? false;
  }

  function toggleItem<T>(arr: T[], item: T, setter: (v: T[]) => void) {
    setter(arr.includes(item) ? arr.filter((x) => x !== item) : [...arr, item]);
  }

  function buildConfig(): SweepConfigRequest {
    const aecConfigs = aecEnabled
      ? [{ suppression_db: aecSuppression, residual_type: "mixed", nonlinear_distortion: aecNld }]
      : [];
    const networkConfigs = networkEnabled
      ? [{ packet_loss_pct: packetLoss, packet_loss_pattern: packetLossPattern, burst_length_ms: 80, jitter_ms: jitterMs, codec_switching: codecSwitching }]
      : [];

    const allNoiseTypes = [...noiseTypes, ...carNoiseTypes];
    return {
      name,
      description,
      noise_level_db_values: noiseLevels,
      speech_level_db_values: speechLevels,
      noise_types: allNoiseTypes.length > 0 ? allNoiseTypes : ["silence"],
      ...(hasInterferer ? { interferer_level_db_values: interfererLevels } : {}),
      echo: { delay_ms_values: delayRange, gain_db_values: gainRange },
      pipelines: ["telephony"],
      llm_backends: backends,
      ...(selectedProviders.length > 0 ? { voice_providers: selectedProviders } : {}),
      ...(selectedCategories.length > 0 ? { corpus_categories: selectedCategories } : {}),
      ...(selectedLanguages.length > 0 ? { voice_languages: selectedLanguages } : {}),
      ...(selectedGenders.length > 0 ? { voice_genders: selectedGenders } : {}),
      ...(maxSamples ? { max_samples: maxSamples } : {}),
      telephony: {
        bt_codec_types: btCodecs,
        agc_presets: agcPresets,
        aec_configs: aecConfigs,
        network_configs: networkConfigs,
        far_end: {
          enabled: farEndEnabled,
          speech_level_db_values: farEndLevels,
          offset_ms_values: farEndOffsets,
        },
      },
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

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 mb-6 space-y-5">
      {/* Row 1: Name + Description */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="sm:col-span-1">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            placeholder="Suite name"
          />
        </div>
        <div className="sm:col-span-2">
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            placeholder="Optional description"
          />
        </div>
      </div>

      {/* Row 2: Audio Sources + Backends */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Audio Sources */}
        <div className="bg-blue-50/60 rounded-lg p-4 border border-blue-100">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider">Audio Sources</h4>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <label className="text-[10px] text-gray-500">Max samples</label>
                <input
                  type="number"
                  min={1}
                  value={maxSamples ?? ""}
                  onChange={(e) => setMaxSamples(e.target.value ? Number(e.target.value) : null)}
                  placeholder="All"
                  className="w-20 border border-gray-200 rounded px-2 py-0.5 text-xs text-right"
                />
              </div>
              {audioSources.data && (
                <span className="text-[11px] font-medium text-blue-600">
                  {audioSources.data.total_samples.toLocaleString()} samples
                </span>
              )}
            </div>
          </div>
          {audioSources.data ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <FilterColumn label="PROVIDER" items={audioSources.data.providers}
                selected={selectedProviders} onToggle={(v) => toggleItem(selectedProviders, v, setSelectedProviders)}
                onClear={() => setSelectedProviders([])} />
              <FilterColumn label="CATEGORY" items={audioSources.data.categories}
                selected={selectedCategories} onToggle={(v) => toggleItem(selectedCategories, v, setSelectedCategories)}
                onClear={() => setSelectedCategories([])} formatLabel={(v) => v.replace(/_/g, " ")} />
              <FilterColumn label="LANGUAGE" items={audioSources.data.languages}
                selected={selectedLanguages} onToggle={(v) => toggleItem(selectedLanguages, v, setSelectedLanguages)}
                onClear={() => setSelectedLanguages([])} />
              <FilterColumn label="GENDER" items={audioSources.data.genders}
                selected={selectedGenders} onToggle={(v) => toggleItem(selectedGenders, v, setSelectedGenders)}
                onClear={() => setSelectedGenders([])} />
            </div>
          ) : (
            <p className="text-xs text-gray-400">Loading...</p>
          )}
        </div>

        {/* LLM Backends */}
        <div>
          <SectionHeader title="LLM Backends" count={backends.length} />
          {ollamaBackends.length > 0 && (
            <div className="mb-2">
              <p className="text-[10px] font-medium text-gray-400 mb-1">LOCAL (FREE)</p>
              <div className="space-y-1">
                {ollamaBackends.map((b) => (
                  <label key={b.key} className="flex items-center gap-2 text-xs text-gray-700">
                    <input
                      type="checkbox"
                      checked={backends.includes(b.key)}
                      onChange={() => toggleItem(backends, b.key, setBackends)}
                      className="rounded border-gray-300 h-3.5 w-3.5"
                    />
                    <span className="flex-1 truncate">{b.label}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
          <div>
            <p className="text-[10px] font-medium text-gray-400 mb-1">CLOUD APIs</p>
            <div className="space-y-1">
              {CLOUD_BACKENDS.map((b) => {
                const keyOk = hasKey(b.keyField);
                const disabled = b.paid && !keyOk;
                return (
                  <label key={b.key} className={`flex items-center gap-2 text-xs ${disabled ? "text-red-400" : "text-gray-700"}`}>
                    <input
                      type="checkbox"
                      checked={backends.includes(b.key)}
                      onChange={() => toggleItem(backends, b.key, setBackends)}
                      className="rounded border-gray-300 h-3.5 w-3.5"
                      disabled={disabled}
                    />
                    <CostBadge paid={b.paid} hasKey={keyOk} />
                    <span className={`flex-1 truncate ${disabled ? "line-through" : ""}`}>{b.label}</span>
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Row 3: Telephony Signal Chain */}
      <div className="bg-indigo-50/60 rounded-lg p-4 border border-indigo-100">
        <h4 className="text-xs font-semibold text-indigo-700 uppercase tracking-wider mb-3">
          Telephony Signal Chain
        </h4>

        <div className="space-y-3">
          {/* BT Codec */}
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-600 w-28 shrink-0">BT Codec</span>
            <PillSelect
              options={BT_CODECS.map((c) => c.key)}
              selected={btCodecs}
              onToggle={(v) => toggleItem(btCodecs, v as string, setBtCodecs)}
              format={(v) => BT_CODECS.find((c) => c.key === v)?.label ?? String(v)}
            />
          </div>

          {/* AGC */}
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-600 w-28 shrink-0">AGC Preset</span>
            <PillSelect
              options={AGC_PRESETS.map((p) => p.key)}
              selected={agcPresets}
              onToggle={(v) => toggleItem(agcPresets, v as string, setAgcPresets)}
              format={(v) => AGC_PRESETS.find((p) => p.key === v)?.label ?? String(v)}
            />
          </div>

          {/* AEC Residual */}
          <div>
            <label className="flex items-center gap-2 text-xs text-gray-600 cursor-pointer">
              <input
                type="checkbox"
                checked={aecEnabled}
                onChange={(e) => setAecEnabled(e.target.checked)}
                className="rounded border-gray-300 h-3.5 w-3.5"
              />
              <span className="font-medium">AEC Residual Simulation</span>
            </label>
            {aecEnabled && (
              <div className="mt-2 ml-6 space-y-2">
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-gray-500 w-24 shrink-0">Suppression</span>
                  <input
                    type="range" min={-40} max={-5} step={1} value={aecSuppression}
                    onChange={(e) => setAecSuppression(Number(e.target.value))}
                    className="flex-1 h-1.5 accent-indigo-600"
                  />
                  <span className="text-[11px] text-gray-600 w-14 text-right tabular-nums">{aecSuppression} dB</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-gray-500 w-24 shrink-0">NLD Amount</span>
                  <input
                    type="range" min={0} max={1} step={0.05} value={aecNld}
                    onChange={(e) => setAecNld(Number(e.target.value))}
                    className="flex-1 h-1.5 accent-indigo-600"
                  />
                  <span className="text-[11px] text-gray-600 w-14 text-right tabular-nums">{aecNld.toFixed(2)}</span>
                </div>
              </div>
            )}
          </div>

          {/* Network Degradation */}
          <div>
            <label className="flex items-center gap-2 text-xs text-gray-600 cursor-pointer">
              <input
                type="checkbox"
                checked={networkEnabled}
                onChange={(e) => setNetworkEnabled(e.target.checked)}
                className="rounded border-gray-300 h-3.5 w-3.5"
              />
              <span className="font-medium">Network Degradation</span>
            </label>
            {networkEnabled && (
              <div className="mt-2 ml-6 space-y-2">
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-gray-500 w-24 shrink-0">Packet Loss</span>
                  <input
                    type="range" min={0} max={20} step={0.5} value={packetLoss}
                    onChange={(e) => setPacketLoss(Number(e.target.value))}
                    className="flex-1 h-1.5 accent-indigo-600"
                  />
                  <span className="text-[11px] text-gray-600 w-14 text-right tabular-nums">{packetLoss}%</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-gray-500 w-24 shrink-0">Loss Pattern</span>
                  <PillSelect
                    options={["random", "burst"]}
                    selected={[packetLossPattern]}
                    onToggle={(v) => setPacketLossPattern(v as string)}
                    format={(v) => v === "burst" ? "Burst" : "Random"}
                  />
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-gray-500 w-24 shrink-0">Jitter</span>
                  <input
                    type="range" min={0} max={100} step={5} value={jitterMs}
                    onChange={(e) => setJitterMs(Number(e.target.value))}
                    className="flex-1 h-1.5 accent-indigo-600"
                  />
                  <span className="text-[11px] text-gray-600 w-14 text-right tabular-nums">{jitterMs} ms</span>
                </div>
                <label className="flex items-center gap-2 text-[11px] text-gray-500 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={codecSwitching}
                    onChange={(e) => setCodecSwitching(e.target.checked)}
                    className="rounded border-gray-300 h-3 w-3"
                  />
                  Mid-call codec switching (CVSD ↔ mSBC)
                </label>
              </div>
            )}
          </div>

          {/* Far-End / 2-Way Conversation */}
          <div className="border-t border-indigo-200/50 pt-3">
            <label className="flex items-center gap-2 text-xs text-gray-600 cursor-pointer">
              <input
                type="checkbox"
                checked={farEndEnabled}
                onChange={(e) => setFarEndEnabled(e.target.checked)}
                className="rounded border-gray-300 h-3.5 w-3.5"
              />
              <span className="font-medium">2-Way Conversation (Far-End Speech)</span>
            </label>
            <p className="text-[10px] text-gray-400 ml-6 mt-0.5">
              Adds uncorrelated far-end caller speech through car speakers. Enables doubletalk testing and barge-in detection.
            </p>
            {farEndEnabled && (
              <div className="mt-2 ml-6 space-y-2">
                <div className="flex items-start gap-3">
                  <span className="text-[11px] text-gray-500 w-28 shrink-0 pt-1">Far-End Level</span>
                  <div>
                    <PillSelect
                      options={[-20, -10, -6, 0, 6, 10]}
                      selected={farEndLevels}
                      onToggle={(v) => toggleItem(farEndLevels, v as number, setFarEndLevels)}
                      format={(v) => `${Number(v) > 0 ? "+" : ""}${v} dB`}
                    />
                    <p className="text-[10px] text-gray-400 mt-0.5">Gain on far-end speech through car speakers</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <span className="text-[11px] text-gray-500 w-28 shrink-0 pt-1">Timing Offset</span>
                  <div>
                    <PillSelect
                      options={[-2000, -1000, -500, 0, 500, 1000]}
                      selected={farEndOffsets}
                      onToggle={(v) => toggleItem(farEndOffsets, v as number, setFarEndOffsets)}
                      format={(v) => {
                        const n = Number(v);
                        if (n < 0) return `${n}ms (barge-in)`;
                        if (n === 0) return "0ms (simultaneous)";
                        return `+${n}ms`;
                      }}
                    />
                    <p className="text-[10px] text-gray-400 mt-0.5">Negative = far-end starts first, near-end interrupts (barge-in)</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Row 4: Cabin Audio Degradation */}
      <div>
        <div className="flex items-center gap-3 mb-3">
          <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Cabin Audio Degradation</h4>
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-[10px] text-blue-500 hover:text-blue-700 font-medium"
          >
            {showAdvanced ? "Hide advanced" : "Show advanced"}
          </button>
        </div>

        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500 w-24 shrink-0">Noise Level (dB)</span>
            <PillSelect
              options={NOISE_LEVEL_OPTIONS}
              selected={noiseLevels}
              onToggle={(v) => toggleItem(noiseLevels, v as number, setNoiseLevels)}
              format={(v) => `${Number(v) > 0 ? "+" : ""}${v}`}
            />
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500 w-24 shrink-0">Noise</span>
            <PillSelect
              options={NOISE_SOURCES.map((s) => s.key)}
              selected={noiseTypes}
              onToggle={(v) => toggleItem(noiseTypes, v as string, setNoiseTypes)}
              format={(v) => NOISE_SOURCES.find((s) => s.key === v)?.label ?? String(v)}
            />
          </div>

          {/* Car noise profile */}
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500 w-24 shrink-0">Car Profile</span>
            <select
              value={selectedCar}
              onChange={(e) => handleCarChange(e.target.value)}
              className="border border-gray-200 rounded-lg px-3 py-1.5 text-xs text-gray-700 bg-white"
            >
              <option value="">None (synthetic noise)</option>
              {carsQuery.data?.map((car) => (
                <option key={car.id} value={car.id}>
                  {car.name} ({car.noise_file_count} files)
                </option>
              ))}
            </select>
            {carNoiseTypes.length > 0 && (
              <span className="text-[10px] text-gray-400">{carNoiseTypes.length} noise files</span>
            )}
          </div>

          {hasInterferer && (
            <div className="flex items-start gap-3">
              <span className="text-xs text-gray-500 w-24 shrink-0 pt-1">Interferer Level</span>
              <div>
                <PillSelect
                  options={[-20, -10, -6, -3, 0, 3, 6, 10, 20]}
                  selected={interfererLevels}
                  onToggle={(v) => toggleItem(interfererLevels, v as number, setInterfererLevels)}
                  format={(v) => `${Number(v) > 0 ? "+" : ""}${v} dB`}
                />
                <p className="text-[10px] text-gray-400 mt-1">0 dB = same loudness as main talker.</p>
              </div>
            </div>
          )}

          {showAdvanced && (
            <>
              <div className="flex items-start gap-3">
                <span className="text-xs text-gray-500 w-24 shrink-0 pt-1">Speech Level</span>
                <div>
                  <PillSelect
                    options={SPEECH_LEVEL_OPTIONS}
                    selected={speechLevels}
                    onToggle={(v) => toggleItem(speechLevels, v as number, setSpeechLevels)}
                    format={(v) => `${Number(v) > 0 ? "+" : ""}${v} dB`}
                  />
                  <p className="text-[10px] text-gray-400 mt-1">0 = original, negative = whisper, positive = loud/clip</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-500 w-24 shrink-0">Echo Delay</span>
                <PillSelect
                  options={[0, 25, 50, 100, 150, 200, 300]}
                  selected={delayRange}
                  onToggle={(v) => toggleItem(delayRange, v as number, setDelayRange)}
                  format={(v) => `${v}ms`}
                />
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-500 w-24 shrink-0">Echo Gain</span>
                <PillSelect
                  options={[-60, -40, -20, -10, -6, -3]}
                  selected={gainRange}
                  onToggle={(v) => toggleItem(gainRange, v as number, setGainRange)}
                  format={(v) => `${v} dB`}
                />
              </div>
            </>
          )}
        </div>
      </div>

      {/* Row 5: Actions */}
      <div className="flex items-center gap-3 border-t border-gray-100 pt-4">
        <button
          onClick={() => previewMutation.mutate()}
          disabled={!name || previewMutation.isPending}
          className="px-4 py-2 bg-white text-gray-700 text-sm font-medium rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          {previewMutation.isPending ? "..." : "Preview"}
        </button>
        <button
          onClick={() => createMutation.mutate()}
          disabled={!name || backends.length === 0 || createMutation.isPending}
          className="px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors"
        >
          {createMutation.isPending ? "Creating..." : "Create Suite"}
        </button>

        {preview && (
          <div className="ml-2 text-sm text-gray-600">
            <span className="font-semibold text-gray-900">{preview.total_cases.toLocaleString()}</span> cases
            {preview.breakdown.telephony_combos != null && preview.breakdown.telephony_combos > 0 && (
              <span className="ml-1.5 text-xs text-gray-400">
                ({preview.breakdown.speech_samples} samples &times; {preview.breakdown.noise_levels} noise levels &times; {preview.breakdown.noise_types} noise &times; {preview.breakdown.backends} backends &times; {preview.breakdown.telephony_combos} telephony combos)
              </span>
            )}
          </div>
        )}

        {createMutation.isError && (
          <span className="text-xs text-red-600">{(createMutation.error as Error).message}</span>
        )}
      </div>
    </div>
  );
}
