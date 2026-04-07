import { useState, useCallback, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchVoices,
  fetchCorpus,
  synthesizePreview,
  syncVoices,
  seedCorpus,
  fetchSpeechStats,
  fetchCorpusStats,
  retryFailedSamples,
  type VoiceResponse,
  type CorpusEntryResponse,
} from "../api/client";

// ---------------------------------------------------------------------------
// SSE Generation progress state
// ---------------------------------------------------------------------------
interface GenProgress {
  status: "idle" | "planning" | "loading" | "running" | "complete" | "error";
  total: number;
  generated: number;
  failed: number;
  pct: number;
  current: string;
  errors: string[];
}

const CATEGORIES = [
  "harvard_sentence",
  "navigation",
  "media",
  "climate",
  "phone",
  "general",
];

const LANGUAGES = ["en", "es", "fr", "de", "it", "pt-BR", "ja", "ko", "zh"];
const PROVIDERS = ["edge", "gtts", "espeak", "piper", "coqui", "bark", "openai", "elevenlabs", "google", "azure", "slurp"];
const GENDERS = ["male", "female", "neutral"];

function toggle<T extends string>(
  setter: React.Dispatch<React.SetStateAction<T[]>>,
  value: T
) {
  setter((prev) =>
    prev.includes(value) ? prev.filter((x) => x !== value) : [...prev, value]
  );
}

function Pill({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
        active
          ? "bg-slate-800 text-white border-slate-800"
          : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"
      }`}
    >
      {label}
    </button>
  );
}

function SectionHeader({
  step,
  title,
  count,
  countLabel,
}: {
  step: number;
  title: string;
  count?: number;
  countLabel?: string;
}) {
  return (
    <div className="flex items-center gap-3 mb-3">
      <span className="flex items-center justify-center w-6 h-6 rounded-full bg-slate-800 text-white text-xs font-bold">
        {step}
      </span>
      <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
      {count !== undefined && (
        <span className="text-sm text-gray-400">
          {count.toLocaleString()} {countLabel}
        </span>
      )}
    </div>
  );
}

export default function SpeechCorpus() {
  const queryClient = useQueryClient();

  // --- Step 1: Voices ---
  const [voiceProvider, setVoiceProvider] = useState("");
  const [voiceGender, setVoiceGender] = useState("");
  const [voiceLang, setVoiceLang] = useState("");

  const voices = useQuery({
    queryKey: ["voices", voiceProvider, voiceGender, voiceLang],
    queryFn: () =>
      fetchVoices({
        provider: voiceProvider || undefined,
        gender: voiceGender || undefined,
        language: voiceLang || undefined,
      }),
  });

  const syncMutation = useMutation({
    mutationFn: syncVoices,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["voices"] }),
  });

  // --- Corpus Stats ---
  const corpusStats = useQuery({
    queryKey: ["corpus-stats"],
    queryFn: () => fetchCorpusStats(),
  });

  // --- Speech Stats (Sample Inventory) ---
  const speechStats = useQuery({
    queryKey: ["speech-stats"],
    queryFn: () => fetchSpeechStats(),
  });

  const retryMutation = useMutation({
    mutationFn: () => retryFailedSamples(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["speech-stats"] }),
  });

  // --- Step 2: Corpus ---
  const [seedLanguages, setSeedLanguages] = useState<string[]>(["en"]);
  const [corpusFilterCat, setCorpusFilterCat] = useState("");
  const [corpusFilterLang, setCorpusFilterLang] = useState("");

  const corpus = useQuery({
    queryKey: ["corpus", corpusFilterCat, corpusFilterLang],
    queryFn: () =>
      fetchCorpus({
        category: corpusFilterCat || undefined,
        language: corpusFilterLang || undefined,
      }),
  });

  const seedMutation = useMutation({
    mutationFn: () => seedCorpus(seedLanguages),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["corpus"] }),
  });

  // --- Step 3: Generate ---
  const [genCategories, setGenCategories] = useState<string[]>([]);
  const [genLanguages, setGenLanguages] = useState<string[]>(["en"]);
  const [genProviders, setGenProviders] = useState<string[]>(["edge"]);
  const [genGenders, setGenGenders] = useState<string[]>([]);
  const [genVoiceLangs, setGenVoiceLangs] = useState<string[]>([]);
  const [maxCorpus, setMaxCorpus] = useState<number | null>(50);
  const [maxVoices, setMaxVoices] = useState<number | null>(5);

  const genParams = {
    categories: genCategories.length ? genCategories : undefined,
    languages: genLanguages.length ? genLanguages : undefined,
    providers: genProviders.length ? genProviders : undefined,
    genders: genGenders.length ? genGenders : undefined,
    voice_languages: genVoiceLangs.length ? genVoiceLangs : undefined,
    max_corpus: maxCorpus || undefined,
    max_voices: maxVoices || undefined,
  };

  const preview = useQuery({
    queryKey: [
      "synthesize-preview",
      genCategories,
      genLanguages,
      genProviders,
      genGenders,
      genVoiceLangs,
      maxCorpus,
      maxVoices,
    ],
    queryFn: () => synthesizePreview(genParams),
  });

  // --- SSE-based generation with progress ---
  const [genProgress, setGenProgress] = useState<GenProgress>({
    status: "idle",
    total: 0,
    generated: 0,
    failed: 0,
    pct: 0,
    current: "",
    errors: [],
  });
  const abortRef = useRef<AbortController | null>(null);

  const startGeneration = useCallback(async () => {
    // Reset state
    setGenProgress({
      status: "planning",
      total: 0,
      generated: 0,
      failed: 0,
      pct: 0,
      current: "Connecting...",
      errors: [],
    });

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch("/api/speech/generate-wavs/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(genParams),
        signal: controller.signal,
      });

      if (!res.ok) {
        const body = await res.text();
        setGenProgress((prev) => ({
          ...prev,
          status: "error",
          current: `API ${res.status}: ${body}`,
        }));
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        setGenProgress((prev) => ({
          ...prev,
          status: "error",
          current: "No response stream",
        }));
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            switch (evt.type) {
              case "planning":
                setGenProgress((prev) => ({
                  ...prev,
                  status: "planning",
                  current: evt.message || "Building generation plan...",
                }));
                break;
              case "loading":
                setGenProgress((prev) => ({
                  ...prev,
                  status: "loading",
                  current: evt.message || `Loading ${evt.provider} model...`,
                }));
                break;
              case "start":
                setGenProgress((prev) => ({
                  ...prev,
                  status: "running",
                  total: evt.total,
                  current: `0 / ${evt.total}`,
                }));
                break;
              case "progress":
                setGenProgress((prev) => ({
                  ...prev,
                  generated: evt.generated,
                  failed: evt.failed,
                  total: evt.total,
                  pct: evt.pct,
                  current: evt.current || "",
                }));
                break;
              case "error":
                setGenProgress((prev) => ({
                  ...prev,
                  generated: evt.generated,
                  failed: evt.failed,
                  total: evt.total,
                  errors: [...prev.errors, evt.message],
                }));
                break;
              case "complete":
                setGenProgress((prev) => ({
                  ...prev,
                  status: "complete",
                  generated: evt.generated,
                  failed: evt.failed,
                  total: evt.total,
                  pct: 100,
                  current: "",
                  errors: evt.errors || prev.errors,
                }));
                break;
            }
          } catch {
            // skip malformed JSON lines
          }
        }
      }

      // If stream ended without a complete event, mark complete
      setGenProgress((prev) =>
        prev.status === "running" ? { ...prev, status: "complete", pct: 100 } : prev
      );
    } catch (err: unknown) {
      if ((err as Error).name === "AbortError") {
        setGenProgress((prev) => ({
          ...prev,
          status: "error",
          current: "Generation cancelled",
        }));
      } else {
        setGenProgress((prev) => ({
          ...prev,
          status: "error",
          current: (err as Error).message,
        }));
      }
    } finally {
      abortRef.current = null;
    }
  }, [genParams]);

  const cancelGeneration = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const p = preview.data;

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-8">Speech Corpus</h2>

      {/* ================================================================= */}
      {/* STEP 1 — Voices                                                   */}
      {/* ================================================================= */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 mb-6">
        <SectionHeader
          step={1}
          title="Voices"
          count={voices.data?.length}
          countLabel="available"
        />

        <div className="flex items-center gap-3 mb-4">
          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors"
          >
            {syncMutation.isPending ? "Syncing..." : "Sync from Providers"}
          </button>
          {syncMutation.isSuccess && (
            <span className="text-sm text-green-600">
              +{syncMutation.data.synced} voices
              {syncMutation.data.errors.length > 0 &&
                ` | ${syncMutation.data.errors.length} errors`}
            </span>
          )}
          {syncMutation.isError && (
            <span className="text-sm text-red-600">
              {(syncMutation.error as Error).message}
            </span>
          )}
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-3 mb-3">
          <select
            value={voiceProvider}
            onChange={(e) => setVoiceProvider(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white"
          >
            <option value="">All Providers</option>
            {PROVIDERS.map((pr) => (
              <option key={pr} value={pr}>
                {pr}
              </option>
            ))}
          </select>
          <select
            value={voiceGender}
            onChange={(e) => setVoiceGender(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white"
          >
            <option value="">All Genders</option>
            {GENDERS.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
          <select
            value={voiceLang}
            onChange={(e) => setVoiceLang(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white"
          >
            <option value="">All Languages</option>
            {LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>

        {/* Collapsible voice table */}
        <details>
          <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-700 mb-2">
            Show voice list
          </summary>
          <div className="max-h-64 overflow-y-auto rounded-lg border border-gray-100">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-gray-50">
                <tr className="text-left text-gray-500 border-b border-gray-100">
                  <th className="px-3 py-2 font-medium">Name</th>
                  <th className="px-3 py-2 font-medium">Provider</th>
                  <th className="px-3 py-2 font-medium">Gender</th>
                  <th className="px-3 py-2 font-medium">Language</th>
                </tr>
              </thead>
              <tbody>
                {voices.data?.map((v: VoiceResponse) => (
                  <tr
                    key={v.voice_id}
                    className="border-b border-gray-50 hover:bg-gray-50"
                  >
                    <td className="px-3 py-1.5 text-gray-900">{v.name}</td>
                    <td className="px-3 py-1.5 text-gray-600">{v.provider}</td>
                    <td className="px-3 py-1.5 text-gray-600 capitalize">
                      {v.gender}
                    </td>
                    <td className="px-3 py-1.5 text-gray-600">{v.language}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </div>

      {/* ================================================================= */}
      {/* STEP 2 — Corpus                                                   */}
      {/* ================================================================= */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 mb-6">
        <SectionHeader
          step={2}
          title="Utterances"
          count={corpus.data?.length}
          countLabel="entries"
        />

        {/* Corpus category badges */}
        {corpusStats.data && Object.keys(corpusStats.data.by_category).length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 mb-3 text-xs text-gray-500">
            {Object.entries(corpusStats.data.by_category).map(([cat, count], i) => (
              <span key={cat} className="flex items-center gap-1">
                {i > 0 && <span className="text-gray-300 mx-0.5">|</span>}
                <span className="text-gray-700 font-medium">{cat.replace("_", " ")}</span>
                <span className="text-gray-400">({count})</span>
              </span>
            ))}
          </div>
        )}

        <div className="flex items-center gap-3 mb-4">
          <button
            onClick={() => seedMutation.mutate()}
            disabled={seedMutation.isPending || seedLanguages.length === 0}
            className="px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors"
          >
            {seedMutation.isPending ? "Seeding..." : "Seed Corpus"}
          </button>

          <div className="flex items-center gap-1.5">
            {LANGUAGES.map((l) => (
              <Pill
                key={l}
                label={l.toUpperCase()}
                active={seedLanguages.includes(l)}
                onClick={() => toggle(setSeedLanguages, l)}
              />
            ))}
          </div>

          {seedMutation.isSuccess && (
            <span className="text-sm text-green-600">
              +{seedMutation.data.entries_created.toLocaleString()} entries
            </span>
          )}
          {seedMutation.isError && (
            <span className="text-sm text-red-600">
              {(seedMutation.error as Error).message}
            </span>
          )}
        </div>

        {/* Browse filters */}
        <div className="flex flex-wrap gap-3 mb-3">
          <select
            value={corpusFilterCat}
            onChange={(e) => setCorpusFilterCat(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white"
          >
            <option value="">All Categories</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c.replace("_", " ")}
              </option>
            ))}
          </select>
          <select
            value={corpusFilterLang}
            onChange={(e) => setCorpusFilterLang(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white"
          >
            <option value="">All Languages</option>
            {LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>

        <details>
          <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-700 mb-2">
            Show utterances
          </summary>
          <div className="max-h-64 overflow-y-auto rounded-lg border border-gray-100">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-gray-50">
                <tr className="text-left text-gray-500 border-b border-gray-100">
                  <th className="px-3 py-2 font-medium w-8"></th>
                  <th className="px-3 py-2 font-medium">Text</th>
                  <th className="px-3 py-2 font-medium">Category</th>
                  <th className="px-3 py-2 font-medium">Intent</th>
                  <th className="px-3 py-2 font-medium">Lang</th>
                </tr>
              </thead>
              <tbody>
                {corpus.data?.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-3 py-6 text-center text-gray-400"
                    >
                      No entries. Seed the corpus above.
                    </td>
                  </tr>
                )}
                {corpus.data?.map((e: CorpusEntryResponse) => (
                  <tr
                    key={e.id}
                    className="border-b border-gray-50 hover:bg-gray-50"
                  >
                    <td className="px-3 py-1.5">
                      <button
                        title="Preview with speech synthesis"
                        onClick={() => {
                          window.speechSynthesis.cancel();
                          const utterance = new SpeechSynthesisUtterance(e.text);
                          utterance.lang = e.language;
                          window.speechSynthesis.speak(utterance);
                        }}
                        className="text-gray-400 hover:text-slate-700 transition-colors"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                          <path d="M6.3 2.84A1.5 1.5 0 004 4.11v11.78a1.5 1.5 0 002.3 1.27l9.344-5.891a1.5 1.5 0 000-2.538L6.3 2.84z" />
                        </svg>
                      </button>
                    </td>
                    <td className="px-3 py-1.5 text-gray-900 max-w-sm truncate">
                      {e.text}
                    </td>
                    <td className="px-3 py-1.5 text-gray-600 capitalize">
                      {e.category.replace("_", " ")}
                    </td>
                    <td className="px-3 py-1.5 text-gray-600">
                      {e.expected_intent || "--"}
                    </td>
                    <td className="px-3 py-1.5 text-gray-600">{e.language}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </div>

      {/* ================================================================= */}
      {/* STEP 3 — Generate WAV Files                                       */}
      {/* ================================================================= */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <SectionHeader step={3} title="Generate WAV Files" />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-5">
          {/* Left: Corpus scope */}
          <div>
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
              Corpus scope
            </h4>

            <div className="mb-3">
              <label className="block text-xs font-medium text-gray-500 mb-1.5">
                Categories
                <span className="ml-1 text-gray-400">
                  {genCategories.length === 0
                    ? "(all)"
                    : `(${genCategories.length})`}
                </span>
              </label>
              <div className="flex flex-wrap gap-1.5">
                {CATEGORIES.map((c) => (
                  <Pill
                    key={c}
                    label={c.replace("_", " ")}
                    active={genCategories.includes(c)}
                    onClick={() => toggle(setGenCategories, c)}
                  />
                ))}
              </div>
            </div>

            <div className="mb-3">
              <label className="block text-xs font-medium text-gray-500 mb-1.5">
                Languages
                <span className="ml-1 text-gray-400">
                  {genLanguages.length === 0
                    ? "(all)"
                    : `(${genLanguages.length})`}
                </span>
              </label>
              <div className="flex flex-wrap gap-1.5">
                {LANGUAGES.map((l) => (
                  <Pill
                    key={l}
                    label={l.toUpperCase()}
                    active={genLanguages.includes(l)}
                    onClick={() => toggle(setGenLanguages, l)}
                  />
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">
                Max entries
              </label>
              <select
                value={maxCorpus ?? ""}
                onChange={(e) =>
                  setMaxCorpus(e.target.value ? Number(e.target.value) : null)
                }
                className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white w-full"
              >
                <option value="">No limit</option>
                <option value="10">10</option>
                <option value="25">25</option>
                <option value="50">50</option>
                <option value="100">100</option>
                <option value="250">250</option>
                <option value="500">500</option>
              </select>
            </div>
          </div>

          {/* Right: Voice scope */}
          <div>
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
              Voice scope
            </h4>

            <div className="mb-3">
              <label className="block text-xs font-medium text-gray-500 mb-1.5">
                Providers
                <span className="ml-1 text-gray-400">
                  {genProviders.length === 0
                    ? "(all)"
                    : `(${genProviders.length})`}
                </span>
              </label>
              <div className="flex flex-wrap gap-1.5">
                {PROVIDERS.map((pr) => (
                  <Pill
                    key={pr}
                    label={pr}
                    active={genProviders.includes(pr)}
                    onClick={() => toggle(setGenProviders, pr)}
                  />
                ))}
              </div>
            </div>

            <div className="mb-3">
              <label className="block text-xs font-medium text-gray-500 mb-1.5">
                Gender
                <span className="ml-1 text-gray-400">
                  {genGenders.length === 0
                    ? "(all)"
                    : `(${genGenders.length})`}
                </span>
              </label>
              <div className="flex flex-wrap gap-1.5">
                {GENDERS.map((g) => (
                  <Pill
                    key={g}
                    label={g}
                    active={genGenders.includes(g)}
                    onClick={() => toggle(setGenGenders, g)}
                  />
                ))}
              </div>
            </div>

            <div className="mb-3">
              <label className="block text-xs font-medium text-gray-500 mb-1.5">
                Voice language
                <span className="ml-1 text-gray-400">
                  {genVoiceLangs.length === 0
                    ? "(all)"
                    : `(${genVoiceLangs.length})`}
                </span>
              </label>
              <div className="flex flex-wrap gap-1.5">
                {LANGUAGES.map((l) => (
                  <Pill
                    key={l}
                    label={l.toUpperCase()}
                    active={genVoiceLangs.includes(l)}
                    onClick={() => toggle(setGenVoiceLangs, l)}
                  />
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">
                Max voices
              </label>
              <select
                value={maxVoices ?? ""}
                onChange={(e) =>
                  setMaxVoices(e.target.value ? Number(e.target.value) : null)
                }
                className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white w-full"
              >
                <option value="">No limit</option>
                <option value="1">1</option>
                <option value="3">3</option>
                <option value="5">5</option>
                <option value="10">10</option>
                <option value="25">25</option>
                <option value="50">50</option>
              </select>
            </div>
          </div>
        </div>

        {/* Preview */}
        {p && (
          <div className="mb-5 rounded-lg bg-gray-50 border border-gray-100 px-4 py-3">
            <div className="flex items-center text-sm gap-6">
              <div>
                <span className="text-gray-500">Corpus</span>{" "}
                <span className="font-semibold text-gray-900">
                  {p.corpus_entries.toLocaleString()}
                </span>
              </div>
              <span className="text-gray-400">&times;</span>
              <div>
                <span className="text-gray-500">Voices</span>{" "}
                <span className="font-semibold text-gray-900">
                  {p.voices.toLocaleString()}
                </span>
              </div>
              <span className="text-gray-400">=</span>
              <div>
                <span className="font-bold text-gray-900">
                  {p.total_combinations.toLocaleString()}
                </span>{" "}
                <span className="text-gray-500">WAV files</span>
              </div>
              <span className="text-gray-300">|</span>
              <span className="font-medium text-gray-700">
                {p.estimated_size_mb >= 1024
                  ? `${(p.estimated_size_mb / 1024).toFixed(1)} GB`
                  : `${Math.round(p.estimated_size_mb)} MB`}
              </span>
              <span className="text-xs text-gray-400">
                (~{p.avg_duration_s}s avg)
              </span>
            </div>
          </div>
        )}

        {/* Generate button */}
        {["planning", "loading", "running"].includes(genProgress.status) ? (
          <button
            onClick={cancelGeneration}
            className="w-full px-4 py-2.5 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-500 transition-colors"
          >
            Cancel Generation
          </button>
        ) : (
          <button
            onClick={startGeneration}
            disabled={!p || p.total_combinations === 0}
            className="w-full px-4 py-2.5 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors"
          >
            {p && p.total_combinations > 0
              ? `Generate ${p.total_combinations.toLocaleString()} WAV Files`
              : "Generate WAV Files"}
          </button>
        )}

        {/* Planning / Loading phase (before progress starts) */}
        {(genProgress.status === "planning" || genProgress.status === "loading") && (
          <div className="mt-4 space-y-2">
            <div className="flex items-center gap-3 text-sm text-gray-600">
              <svg className="animate-spin h-4 w-4 text-slate-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span>{genProgress.current}</span>
            </div>
            <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full bg-slate-400 rounded-full animate-pulse" style={{ width: "100%" }} />
            </div>
          </div>
        )}

        {/* Progress bar */}
        {genProgress.status === "running" && (
          <div className="mt-4 space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600 font-medium">
                {genProgress.generated + genProgress.failed} / {genProgress.total}
              </span>
              <span className="text-gray-500">{genProgress.pct.toFixed(1)}%</span>
            </div>
            <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full flex transition-all duration-300">
                <div
                  className="bg-green-500 transition-all duration-300"
                  style={{
                    width: genProgress.total > 0
                      ? `${(genProgress.generated / genProgress.total) * 100}%`
                      : "0%",
                  }}
                />
                <div
                  className="bg-red-400 transition-all duration-300"
                  style={{
                    width: genProgress.total > 0
                      ? `${(genProgress.failed / genProgress.total) * 100}%`
                      : "0%",
                  }}
                />
              </div>
            </div>
            <div className="flex items-center gap-4 text-xs text-gray-500">
              <span className="flex items-center gap-1">
                <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
                {genProgress.generated} generated
              </span>
              {genProgress.failed > 0 && (
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-red-400" />
                  {genProgress.failed} failed
                </span>
              )}
            </div>
            {genProgress.current && (
              <div className="text-xs text-gray-400 truncate">
                {genProgress.current}
              </div>
            )}
            {/* Live errors during generation */}
            {genProgress.errors.length > 0 && (
              <details className="mt-1">
                <summary className="text-xs text-amber-600 cursor-pointer">
                  {genProgress.errors.length} error{genProgress.errors.length > 1 ? "s" : ""}
                </summary>
                <ul className="mt-1 text-xs text-gray-500 space-y-0.5 max-h-32 overflow-y-auto">
                  {genProgress.errors.map((err, i) => (
                    <li key={i} className="truncate">{err}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}

        {/* Completed summary */}
        {genProgress.status === "complete" && (
          <div className="mt-3 space-y-2">
            <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-700">
              <strong>{genProgress.generated.toLocaleString()}</strong> generated
              {genProgress.failed > 0 && (
                <span className="text-amber-600 ml-3">
                  {genProgress.failed} failed
                </span>
              )}
              <span className="text-gray-400 ml-3">
                / {genProgress.total} total
              </span>
            </div>
            {genProgress.errors.length > 0 && (
              <details>
                <summary className="text-xs text-amber-600 cursor-pointer">
                  {genProgress.errors.length} error{genProgress.errors.length > 1 ? "s" : ""}
                </summary>
                <ul className="mt-1 text-xs text-gray-500 space-y-0.5 max-h-40 overflow-y-auto">
                  {genProgress.errors.map((err, i) => (
                    <li key={i} className="truncate">{err}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}

        {/* Error state */}
        {genProgress.status === "error" && (
          <div className="mt-3 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {genProgress.current}
            {genProgress.generated > 0 && (
              <span className="text-green-600 ml-3">
                ({genProgress.generated} generated before error)
              </span>
            )}
          </div>
        )}
      </div>

      {/* ================================================================= */}
      {/* STEP 4 — Sample Inventory                                         */}
      {/* ================================================================= */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 mt-6">
        <SectionHeader step={4} title="Sample Inventory" />

        {speechStats.isLoading && (
          <p className="text-sm text-gray-400">Loading stats...</p>
        )}
        {speechStats.isError && (
          <p className="text-sm text-red-600">
            {(speechStats.error as Error).message}
          </p>
        )}

        {speechStats.data && (
          <>
            <div className="overflow-x-auto rounded-lg border border-gray-100 mb-4">
              <table className="w-full text-xs">
                <thead className="bg-gray-50">
                  <tr className="text-left text-gray-500 border-b border-gray-100">
                    <th className="px-3 py-2 font-medium">Provider</th>
                    <th className="px-3 py-2 font-medium text-right">Ready</th>
                    <th className="px-3 py-2 font-medium text-right">Failed</th>
                    <th className="px-3 py-2 font-medium text-right">Pending</th>
                    <th className="px-3 py-2 font-medium text-right">Generating</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(speechStats.data.by_provider).map(
                    ([provider, counts]) => (
                      <tr
                        key={provider}
                        className="border-b border-gray-50 hover:bg-gray-50"
                      >
                        <td className="px-3 py-1.5 text-gray-900 font-medium">
                          {provider}
                        </td>
                        <td className="px-3 py-1.5 text-right">
                          <span className="text-green-600 font-medium">
                            {counts.ready}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 text-right">
                          <span className={counts.failed > 0 ? "text-red-600 font-medium" : "text-gray-400"}>
                            {counts.failed}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 text-right">
                          <span className={counts.pending > 0 ? "text-gray-600" : "text-gray-400"}>
                            {counts.pending}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 text-right">
                          <span className={counts.generating > 0 ? "text-blue-600 font-medium" : "text-gray-400"}>
                            {counts.generating}
                          </span>
                        </td>
                      </tr>
                    )
                  )}
                  {/* Totals row */}
                  <tr className="bg-gray-50 border-t border-gray-200 font-semibold">
                    <td className="px-3 py-2 text-gray-800">Total</td>
                    <td className="px-3 py-2 text-right text-green-600">
                      {speechStats.data.totals.ready}
                    </td>
                    <td className="px-3 py-2 text-right text-red-600">
                      {speechStats.data.totals.failed}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-600">
                      {speechStats.data.totals.pending}
                    </td>
                    <td className="px-3 py-2 text-right text-blue-600">
                      {speechStats.data.totals.generating}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {speechStats.data.totals.failed > 0 && (
              <button
                onClick={() => retryMutation.mutate()}
                disabled={retryMutation.isPending}
                className="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-500 disabled:opacity-50 transition-colors"
              >
                {retryMutation.isPending
                  ? "Retrying..."
                  : `Retry ${speechStats.data.totals.failed} Failed`}
              </button>
            )}
            {retryMutation.isSuccess && (
              <span className="ml-3 text-sm text-green-600">
                Retried: {retryMutation.data.generated} generated, {retryMutation.data.failed} still failed
              </span>
            )}
            {retryMutation.isError && (
              <span className="ml-3 text-sm text-red-600">
                {(retryMutation.error as Error).message}
              </span>
            )}
          </>
        )}
      </div>
    </div>
  );
}
