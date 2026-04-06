import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchVoices,
  fetchCorpus,
  synthesizeSpeech,
  syncVoices,
  seedCorpus,
  type VoiceResponse,
  type CorpusEntryResponse,
} from "../api/client";

type Tab = "voices" | "corpus" | "generate";

const CATEGORIES = [
  "harvard_sentence",
  "navigation",
  "media",
  "climate",
  "phone",
  "general",
];

export default function SpeechCorpus() {
  const [tab, setTab] = useState<Tab>("voices");

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Speech Corpus</h2>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 rounded-lg p-1 w-fit mb-6">
        {(["voices", "corpus", "generate"] as Tab[]).map((t) => (
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

      {tab === "voices" && <VoicesTab />}
      {tab === "corpus" && <CorpusTab />}
      {tab === "generate" && <GenerateTab />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Voices Tab
// ---------------------------------------------------------------------------

function VoicesTab() {
  const [provider, setProvider] = useState("");
  const [gender, setGender] = useState("");
  const [language, setLanguage] = useState("");
  const queryClient = useQueryClient();

  const voices = useQuery({
    queryKey: ["voices", provider, gender, language],
    queryFn: () =>
      fetchVoices({
        provider: provider || undefined,
        gender: gender || undefined,
        language: language || undefined,
      }),
  });

  const syncMutation = useMutation({
    mutationFn: syncVoices,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["voices"] }),
  });

  return (
    <div>
      {/* Sync + Filters */}
      <div className="flex gap-3 mb-4">
        <button
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
          className="px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors"
        >
          {syncMutation.isPending ? "Syncing..." : "Sync Voices from Providers"}
        </button>
        {syncMutation.isSuccess && (
          <span className="self-center text-sm text-green-600">
            +{syncMutation.data.synced} voices ({syncMutation.data.providers.join(", ") || "no new voices"})
            {syncMutation.data.errors.length > 0 && ` | Errors: ${syncMutation.data.errors.join(", ")}`}
          </span>
        )}
      </div>
      <div className="flex gap-3 mb-4">
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">All Providers</option>
          <option value="openai">OpenAI</option>
          <option value="google">Google</option>
          <option value="elevenlabs">ElevenLabs</option>
        </select>
        <select
          value={gender}
          onChange={(e) => setGender(e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">All Genders</option>
          <option value="male">Male</option>
          <option value="female">Female</option>
          <option value="neutral">Neutral</option>
        </select>
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">All Languages</option>
          <option value="en">English</option>
          <option value="es">Spanish</option>
          <option value="fr">French</option>
        </select>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-100">
              <th className="px-6 py-3 font-medium">Name</th>
              <th className="px-6 py-3 font-medium">Provider</th>
              <th className="px-6 py-3 font-medium">Gender</th>
              <th className="px-6 py-3 font-medium">Age Group</th>
              <th className="px-6 py-3 font-medium">Language</th>
              <th className="px-6 py-3 font-medium">Accent</th>
            </tr>
          </thead>
          <tbody>
            {voices.data?.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-gray-400">
                  No voices found. Seed the catalog to get started.
                </td>
              </tr>
            )}
            {voices.data?.map((v: VoiceResponse) => (
              <tr key={v.voice_id} className="border-b border-gray-50 hover:bg-gray-50">
                <td className="px-6 py-3 font-medium text-gray-900">{v.name}</td>
                <td className="px-6 py-3 text-gray-600 capitalize">{v.provider}</td>
                <td className="px-6 py-3 text-gray-600 capitalize">{v.gender}</td>
                <td className="px-6 py-3 text-gray-600 capitalize">
                  {v.age_group.replace("_", " ")}
                </td>
                <td className="px-6 py-3 text-gray-600">{v.language}</td>
                <td className="px-6 py-3 text-gray-600">{v.accent || "--"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Corpus Tab
// ---------------------------------------------------------------------------

function CorpusTab() {
  const [category, setCategory] = useState("");
  const [language, setLanguage] = useState("");
  const queryClient = useQueryClient();

  const corpus = useQuery({
    queryKey: ["corpus", category, language],
    queryFn: () =>
      fetchCorpus({
        category: category || undefined,
        language: language || undefined,
      }),
  });

  const seedMutation = useMutation({
    mutationFn: seedCorpus,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["corpus"] }),
  });

  return (
    <div>
      <div className="flex gap-3 mb-4">
        <button
          onClick={() => seedMutation.mutate()}
          disabled={seedMutation.isPending}
          className="px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors"
        >
          {seedMutation.isPending ? "Seeding..." : "Seed Corpus"}
        </button>
        {seedMutation.isSuccess && (
          <span className="self-center text-sm text-green-600">
            +{seedMutation.data.entries_created} entries created
          </span>
        )}
        {seedMutation.isError && (
          <span className="self-center text-sm text-red-600">
            {(seedMutation.error as Error).message}
          </span>
        )}
      </div>
      <div className="flex gap-3 mb-4">
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c.replace("_", " ")}
            </option>
          ))}
        </select>
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">All Languages</option>
          <option value="en">English</option>
          <option value="es">Spanish</option>
        </select>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-100">
              <th className="px-6 py-3 font-medium">Text</th>
              <th className="px-6 py-3 font-medium">Category</th>
              <th className="px-6 py-3 font-medium">Intent</th>
              <th className="px-6 py-3 font-medium">Language</th>
            </tr>
          </thead>
          <tbody>
            {corpus.data?.length === 0 && (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-gray-400">
                  No corpus entries. Seed the corpus to populate.
                </td>
              </tr>
            )}
            {corpus.data?.map((e: CorpusEntryResponse) => (
              <tr key={e.id} className="border-b border-gray-50 hover:bg-gray-50">
                <td className="px-6 py-3 text-gray-900 max-w-md truncate">
                  {e.text}
                </td>
                <td className="px-6 py-3 text-gray-600 capitalize">
                  {e.category.replace("_", " ")}
                </td>
                <td className="px-6 py-3 text-gray-600">{e.expected_intent || "--"}</td>
                <td className="px-6 py-3 text-gray-600">{e.language}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Generate Tab
// ---------------------------------------------------------------------------

function GenerateTab() {
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [selectedLanguages, setSelectedLanguages] = useState<string[]>(["en"]);

  const mutation = useMutation({
    mutationFn: () =>
      synthesizeSpeech({
        categories: selectedCategories.length ? selectedCategories : undefined,
        languages: selectedLanguages.length ? selectedLanguages : undefined,
      }),
  });

  function toggleCategory(c: string) {
    setSelectedCategories((prev) =>
      prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]
    );
  }

  return (
    <div className="max-w-xl">
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">
          Batch Speech Synthesis
        </h3>

        <div className="mb-5">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Categories
          </label>
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map((c) => (
              <button
                key={c}
                onClick={() => toggleCategory(c)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                  selectedCategories.includes(c)
                    ? "bg-slate-800 text-white border-slate-800"
                    : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"
                }`}
              >
                {c.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>

        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Languages
          </label>
          <div className="flex gap-2">
            {["en", "es", "fr"].map((l) => (
              <button
                key={l}
                onClick={() =>
                  setSelectedLanguages((prev) =>
                    prev.includes(l) ? prev.filter((x) => x !== l) : [...prev, l]
                  )
                }
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                  selectedLanguages.includes(l)
                    ? "bg-slate-800 text-white border-slate-800"
                    : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"
                }`}
              >
                {l.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="w-full px-4 py-2.5 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors"
        >
          {mutation.isPending ? "Generating..." : "Generate Samples"}
        </button>

        {mutation.isSuccess && (
          <p className="mt-3 text-sm text-green-600">
            Queued {mutation.data.total_combinations} combinations (task:{" "}
            {mutation.data.task_id})
          </p>
        )}
        {mutation.isError && (
          <p className="mt-3 text-sm text-red-600">
            {(mutation.error as Error).message}
          </p>
        )}
      </div>
    </div>
  );
}
