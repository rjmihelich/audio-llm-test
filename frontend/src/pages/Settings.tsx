import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchSettings, updateSettings, type SettingsResponse } from "../api/client";

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

export default function Settings() {
  const queryClient = useQueryClient();
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [ollamaUrl, setOllamaUrl] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  const { data: settings, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
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
    <div className="p-8 max-w-3xl">
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
              <div className="flex items-center justify-between mb-2">
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
          <div className="flex items-center justify-between mb-2">
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
        <div className="px-6 py-4 grid grid-cols-2 gap-4">
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
