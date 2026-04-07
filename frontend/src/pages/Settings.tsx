import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchSettings,
  updateSettings,
  fetchKeyStatus,
  importSlurp,
  type SettingsResponse,
  type KeyStatusResponse,
  type SlurpImportResponse,
} from "../api/client";

interface KeyField {
  key: keyof SettingsResponse;
  label: string;
  placeholder: string;
  description: string;
}

const KEY_FIELDS: KeyField[] = [
  {
    key: "openai_api_key",
    label: "OpenAI",
    placeholder: "sk-...",
    description: "GPT-4o audio model, Whisper ASR, TTS",
  },
  {
    key: "anthropic_api_key",
    label: "Anthropic",
    placeholder: "sk-ant-...",
    description: "Claude models (text pipeline only)",
  },
  {
    key: "google_api_key",
    label: "Google Cloud",
    placeholder: "AI...",
    description: "Gemini multimodal + Google Cloud TTS",
  },
  {
    key: "elevenlabs_api_key",
    label: "ElevenLabs",
    placeholder: "xi-...",
    description: "Premium TTS voice generation",
  },
  {
    key: "deepgram_api_key",
    label: "Deepgram",
    placeholder: "dg-...",
    description: "Deepgram STT/ASR engine",
  },
  {
    key: "azure_speech_key",
    label: "Azure Speech",
    placeholder: "your-azure-key",
    description: "Azure Cognitive Services Speech (key)",
  },
  {
    key: "azure_speech_region",
    label: "Azure Region",
    placeholder: "eastus",
    description: "Azure Speech region (e.g. eastus, westus2)",
  },
];

interface TTSProviderInfo {
  name: string;
  description: string;
  install: string;
  free: boolean;
  offline: boolean;
  quality: "low" | "medium" | "high" | "premium";
}

const TTS_PROVIDERS: TTSProviderInfo[] = [
  {
    name: "Edge TTS",
    description: "Microsoft Edge neural voices, 30+ languages, excellent quality",
    install: "pip install edge-tts",
    free: true,
    offline: false,
    quality: "high",
  },
  {
    name: "gTTS",
    description: "Google Translate TTS, 20+ languages, basic quality",
    install: "pip install gTTS",
    free: true,
    offline: false,
    quality: "medium",
  },
  {
    name: "Piper",
    description: "Fast local neural TTS, many ONNX voice models",
    install: "pip install piper-tts",
    free: true,
    offline: true,
    quality: "high",
  },
  {
    name: "Coqui TTS",
    description: "Open-source multi-model TTS (Tacotron2, VITS, XTTS v2)",
    install: "pip install TTS",
    free: true,
    offline: true,
    quality: "high",
  },
  {
    name: "Bark",
    description: "Suno's expressive text-to-audio, supports emotions & music",
    install: "pip install suno-bark",
    free: true,
    offline: true,
    quality: "high",
  },
  {
    name: "eSpeak",
    description: "System-level speech engine, works everywhere, robotic quality",
    install: "pip install pyttsx3",
    free: true,
    offline: true,
    quality: "low",
  },
  {
    name: "OpenAI TTS",
    description: "OpenAI's tts-1 model, 6 voices (requires API key above)",
    install: "included",
    free: false,
    offline: false,
    quality: "premium",
  },
  {
    name: "Google Cloud TTS",
    description: "WaveNet & Neural2 voices (requires API key above)",
    install: "pip install google-cloud-texttospeech",
    free: false,
    offline: false,
    quality: "premium",
  },
  {
    name: "ElevenLabs",
    description: "Voice cloning & premium generation (requires API key above)",
    install: "included",
    free: false,
    offline: false,
    quality: "premium",
  },
];

function StatusDot({ configured }: { configured: boolean }) {
  return (
    <span
      className={`inline-block w-2.5 h-2.5 rounded-full ${
        configured ? "bg-green-500" : "bg-gray-300"
      }`}
      title={configured ? "Configured" : "Not configured"}
    />
  );
}

function QualityBadge({ quality }: { quality: string }) {
  const colors: Record<string, string> = {
    low: "bg-gray-100 text-gray-600",
    medium: "bg-yellow-100 text-yellow-700",
    high: "bg-blue-100 text-blue-700",
    premium: "bg-purple-100 text-purple-700",
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${
        colors[quality] || colors.medium
      }`}
    >
      {quality}
    </span>
  );
}

function SlurpImportButton() {
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<SlurpImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleImport = async () => {
    setImporting(true);
    setResult(null);
    setError(null);
    try {
      const res = await importSlurp(100);
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  };

  return (
    <div>
      <button
        onClick={handleImport}
        disabled={importing}
        className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
          importing
            ? "bg-gray-200 text-gray-400 cursor-not-allowed"
            : "bg-emerald-600 text-white hover:bg-emerald-700"
        }`}
      >
        {importing ? "Importing..." : "Scan & Import SLURP Files"}
      </button>
      {result && (
        <div className="mt-3 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-sm">
          <p className="font-medium text-emerald-800">
            Import complete: {result.imported} samples imported
          </p>
          <p className="text-emerald-700 mt-1">
            Found {result.total_audio_files_found} files &middot;{" "}
            {result.converted} converted &middot;{" "}
            {result.skipped} skipped &middot;{" "}
            {result.failed} failed
            {result.has_annotations && ` \u00b7 ${result.annotation_count} annotations matched`}
          </p>
          {Object.keys(result.by_scenario).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(result.by_scenario).sort((a, b) => b[1] - a[1]).map(([sc, cnt]) => (
                <span key={sc} className="px-2 py-0.5 bg-emerald-100 text-emerald-800 rounded text-xs">
                  {sc}: {cnt}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      {error && (
        <p className="mt-3 text-sm text-red-600">{error}</p>
      )}
    </div>
  );
}

export default function Settings() {
  const queryClient = useQueryClient();
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [ollamaUrl, setOllamaUrl] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  const { data: settings, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
  });

  const { data: keyStatus } = useQuery<KeyStatusResponse>({
    queryKey: ["key-status"],
    queryFn: fetchKeyStatus,
  });

  const mutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setFormValues({});
      setSaveMessage(
        `Saved ${data.keys_changed.length} key${data.keys_changed.length !== 1 ? "s" : ""}`
      );
      setTimeout(() => setSaveMessage(null), 3000);
    },
    onError: (err: Error) => {
      setSaveMessage(`Error: ${err.message}`);
      setTimeout(() => setSaveMessage(null), 5000);
    },
  });

  const handleSave = () => {
    const payload: Record<string, string> = {};
    for (const [k, v] of Object.entries(formValues)) {
      if (v.trim()) payload[k] = v.trim();
    }
    if (ollamaUrl !== null && ollamaUrl.trim()) {
      payload["ollama_base_url"] = ollamaUrl.trim();
    }
    if (Object.keys(payload).length === 0) return;
    mutation.mutate(payload);
  };

  const hasChanges =
    Object.values(formValues).some((v) => v.trim() !== "") ||
    (ollamaUrl !== null && ollamaUrl.trim() !== "");

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
    <div className="p-4 sm:p-6 lg:p-8 max-w-3xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-sm text-gray-500 mt-1">
          Configure API keys, TTS providers, and service connections. Keys are
          saved to your .env file and persist across restarts.
        </p>
      </div>

      {/* API Keys */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm divide-y divide-gray-100">
        <div className="px-6 py-4">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">
            API Keys
          </h2>
        </div>

        {KEY_FIELDS.map((field) => {
          const currentValue = settings?.[field.key] as string | null;
          const isConfigured = currentValue !== null && currentValue !== "";
          const editValue = formValues[field.key] ?? "";

          return (
            <div key={field.key} className="px-6 py-5">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-2">
                <div className="flex items-center gap-2.5">
                  <StatusDot configured={isConfigured} />
                  <label className="text-sm font-medium text-gray-900">
                    {field.label}
                  </label>
                </div>
                <span className="text-xs text-gray-400">
                  {field.description}
                </span>
              </div>
              <div className="flex gap-3">
                <input
                  type="password"
                  className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg
                             focus:ring-2 focus:ring-slate-500 focus:border-slate-500
                             placeholder:text-gray-400 font-mono"
                  placeholder={
                    isConfigured
                      ? currentValue ?? field.placeholder
                      : field.placeholder
                  }
                  value={editValue}
                  onChange={(e) =>
                    setFormValues((prev) => ({
                      ...prev,
                      [field.key]: e.target.value,
                    }))
                  }
                  autoComplete="off"
                />
                {editValue && (
                  <button
                    onClick={() =>
                      setFormValues((prev) => {
                        const next = { ...prev };
                        delete next[field.key];
                        return next;
                      })
                    }
                    className="px-3 py-2 text-xs text-gray-500 hover:text-gray-700
                               border border-gray-200 rounded-lg hover:bg-gray-50"
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Local Services */}
      <div className="mt-6 bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">
            Local Services
          </h2>
        </div>
        <div className="px-6 py-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-2">
            <div className="flex items-center gap-2.5">
              <StatusDot configured={true} />
              <label className="text-sm font-medium text-gray-900">
                Ollama
              </label>
            </div>
            <span className="text-xs text-gray-400">
              Local LLM inference (no API key required)
            </span>
          </div>
          <input
            type="text"
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg
                       focus:ring-2 focus:ring-slate-500 focus:border-slate-500
                       placeholder:text-gray-400 font-mono"
            placeholder={settings?.ollama_base_url || "http://localhost:11434"}
            value={ollamaUrl ?? ""}
            onChange={(e) => setOllamaUrl(e.target.value)}
          />
        </div>
      </div>

      {/* Default Backends */}
      <div className="mt-6 bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">
            Default Backends
          </h2>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-1">
              Default LLM Backend
            </label>
            <select
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg
                         focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
              value={formValues["default_llm_backend"] ?? settings?.default_llm_backend ?? ""}
              onChange={(e) =>
                setFormValues((prev) => ({ ...prev, default_llm_backend: e.target.value }))
              }
            >
              <option value="">-- select --</option>
              <option value="openai">OpenAI (GPT-4o)</option>
              <option value="anthropic">Anthropic (Claude)</option>
              <option value="google">Google (Gemini)</option>
              <option value="ollama">Ollama (local)</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-1">
              Default STT Backend
            </label>
            <select
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg
                         focus:ring-2 focus:ring-slate-500 focus:border-slate-500"
              value={formValues["default_stt_backend"] ?? settings?.default_stt_backend ?? ""}
              onChange={(e) =>
                setFormValues((prev) => ({ ...prev, default_stt_backend: e.target.value }))
              }
            >
              <option value="">-- select --</option>
              <option value="openai">OpenAI Whisper</option>
              <option value="deepgram">Deepgram</option>
              <option value="azure">Azure Speech</option>
            </select>
          </div>
        </div>
      </div>

      {/* Provider Status */}
      <div className="mt-6 bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">
            Provider Status
          </h2>
          <p className="text-xs text-gray-400 mt-1">
            API key configuration status from the backend.
          </p>
        </div>
        <div className="px-6 py-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
          {(
            [
              ["OpenAI", keyStatus?.openai],
              ["Anthropic", keyStatus?.anthropic],
              ["Google", keyStatus?.google],
              ["ElevenLabs", keyStatus?.elevenlabs],
              ["Deepgram", keyStatus?.deepgram],
              ["Azure Speech", keyStatus?.azure],
              ["Ollama", keyStatus?.ollama],
            ] as [string, boolean | undefined][]
          ).map(([name, ok]) => (
            <div key={name} className="flex items-center gap-2">
              <StatusDot configured={!!ok} />
              <span className="text-sm text-gray-700">{name}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Local / Free Providers */}
      <div className="mt-6 bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">
            Local / Free Providers
          </h2>
        </div>
        <div className="divide-y divide-gray-50">
          {([
            { name: "Piper TTS", note: "Installed", badge: "bg-green-100 text-green-700" },
            { name: "Edge TTS", note: "Available (free)", badge: "bg-blue-100 text-blue-700" },
            { name: "gTTS", note: "Available (free)", badge: "bg-blue-100 text-blue-700" },
            { name: "eSpeak / System", note: "Available (built-in)", badge: "bg-gray-100 text-gray-600" },
            { name: "SLURP Dataset", note: "Data source", badge: "bg-purple-100 text-purple-700" },
          ]).map((p) => (
            <div key={p.name} className="px-6 py-3 flex items-center justify-between">
              <span className="text-sm font-medium text-gray-900">{p.name}</span>
              <span
                className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${p.badge}`}
              >
                {p.note}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* TTS Providers */}
      <div className="mt-6 bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">
            Speech Generation (TTS) Providers
          </h2>
          <p className="text-xs text-gray-400 mt-1">
            Free providers work without API keys. Install via pip to enable.
          </p>
        </div>

        <div className="divide-y divide-gray-50">
          {TTS_PROVIDERS.map((p) => (
            <div key={p.name} className="px-6 py-4 flex items-start gap-4">
              <div className="pt-0.5">
                {p.free ? (
                  <span className="inline-block w-5 h-5 rounded bg-green-100 text-green-600 text-[10px] font-bold leading-5 text-center">
                    F
                  </span>
                ) : (
                  <span className="inline-block w-5 h-5 rounded bg-amber-100 text-amber-600 text-[10px] font-bold leading-5 text-center">
                    $
                  </span>
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-900">
                    {p.name}
                  </span>
                  <QualityBadge quality={p.quality} />
                  {p.offline && (
                    <span className="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase bg-green-50 text-green-700">
                      offline
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 mt-0.5">
                  {p.description}
                </p>
              </div>
              {p.install !== "included" && (
                <code className="text-[11px] text-gray-400 bg-gray-50 px-2 py-1 rounded font-mono whitespace-nowrap">
                  {p.install}
                </code>
              )}
            </div>
          ))}
        </div>

        <div className="px-6 py-3 bg-gray-50 rounded-b-xl">
          <p className="text-xs text-gray-400">
            Install all free providers:{" "}
            <code className="bg-white px-1.5 py-0.5 rounded text-gray-600">
              pip install audio-llm-test[tts-free]
            </code>
            {" "}or all:{" "}
            <code className="bg-white px-1.5 py-0.5 rounded text-gray-600">
              pip install audio-llm-test[tts-all]
            </code>
          </p>
        </div>
      </div>

      {/* Platform Config (read-only) */}
      <div className="mt-6 bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">
            Platform Config
          </h2>
        </div>
        <div className="px-6 py-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-gray-500">Sample Rate</p>
            <p className="text-sm font-medium text-gray-900">
              {settings?.default_sample_rate?.toLocaleString()} Hz
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Max Concurrent Workers</p>
            <p className="text-sm font-medium text-gray-900">
              {settings?.max_concurrent_workers}
            </p>
          </div>
        </div>
      </div>

      {/* SLURP Dataset Import */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 sm:p-6 mt-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-1">SLURP Dataset Import</h2>
        <p className="text-sm text-gray-500 mb-4">
          Import SLURP natural speech recordings from storage into the database.
          Scans for WAV/FLAC files and creates corpus entries with metadata.
        </p>
        <SlurpImportButton />
      </div>

      {/* Save bar */}
      <div className="mt-6 flex items-center gap-4">
        <button
          onClick={handleSave}
          disabled={!hasChanges || mutation.isPending}
          className={`px-5 py-2.5 text-sm font-medium rounded-lg transition-colors ${
            hasChanges && !mutation.isPending
              ? "bg-slate-800 text-white hover:bg-slate-700"
              : "bg-gray-200 text-gray-400 cursor-not-allowed"
          }`}
        >
          {mutation.isPending ? "Saving..." : "Save Changes"}
        </button>
        {saveMessage && (
          <span
            className={`text-sm ${
              saveMessage.startsWith("Error")
                ? "text-red-600"
                : "text-green-600"
            }`}
          >
            {saveMessage}
          </span>
        )}
      </div>
    </div>
  );
}
