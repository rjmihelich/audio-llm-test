import { useState, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  browseSamples,
  fetchSampleFilters,
  getSampleAudioUrl,
  type SampleBrowseItem,
} from "../api/client";

// ---------------------------------------------------------------------------
// Audio Player Component
// ---------------------------------------------------------------------------

function MiniPlayer({
  sample,
  isPlaying,
  onPlay,
  onStop,
}: {
  sample: SampleBrowseItem;
  isPlaying: boolean;
  onPlay: () => void;
  onStop: () => void;
}) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        isPlaying ? onStop() : onPlay();
      }}
      className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors shrink-0 ${
        isPlaying
          ? "bg-blue-500 text-white"
          : "bg-gray-100 text-gray-500 hover:bg-blue-100 hover:text-blue-600"
      }`}
      title={isPlaying ? "Stop" : "Play"}
    >
      {isPlaying ? (
        <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
          <rect x="6" y="4" width="4" height="16" />
          <rect x="14" y="4" width="4" height="16" />
        </svg>
      ) : (
        <svg className="w-3.5 h-3.5 ml-0.5" fill="currentColor" viewBox="0 0 24 24">
          <path d="M8 5v14l11-7z" />
        </svg>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Waveform-style duration bar
// ---------------------------------------------------------------------------

function DurationBar({ durationS }: { durationS: number }) {
  const maxDur = 10;
  const pct = Math.min((durationS / maxDur) * 100, 100);
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-blue-300 rounded-full"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-400 tabular-nums">{durationS.toFixed(1)}s</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Filter dropdown
// ---------------------------------------------------------------------------

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="min-w-0">
      <label className="block text-[10px] font-medium text-gray-400 uppercase tracking-wider mb-1">
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border border-gray-200 rounded-lg px-2.5 py-1.5 text-sm bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
      >
        <option value="">All</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    ready: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
    pending: "bg-yellow-100 text-yellow-700",
    generating: "bg-blue-100 text-blue-700",
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${
        colors[status] || "bg-gray-100 text-gray-500"
      }`}
    >
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Provider badge
// ---------------------------------------------------------------------------

function ProviderBadge({ provider }: { provider: string }) {
  const colors: Record<string, string> = {
    edge: "bg-blue-50 text-blue-700",
    piper: "bg-emerald-50 text-emerald-700",
    slurp: "bg-purple-50 text-purple-700",
    gtts: "bg-amber-50 text-amber-700",
    espeak: "bg-gray-100 text-gray-600",
    openai: "bg-slate-100 text-slate-700",
    azure: "bg-cyan-50 text-cyan-700",
    coqui: "bg-orange-50 text-orange-700",
    bark: "bg-rose-50 text-rose-700",
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold ${
        colors[provider] || "bg-gray-100 text-gray-600"
      }`}
    >
      {provider}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Now Playing bar
// ---------------------------------------------------------------------------

function NowPlaying({
  sample,
  audioRef,
  onStop,
}: {
  sample: SampleBrowseItem;
  audioRef: React.RefObject<HTMLAudioElement>;
  onStop: () => void;
}) {
  const [progress, setProgress] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);

  return (
    <div className="fixed bottom-0 left-0 right-0 md:left-64 z-30 bg-white border-t border-gray-200 shadow-lg">
      <audio
        ref={audioRef}
        src={getSampleAudioUrl(sample.id)}
        autoPlay
        onTimeUpdate={() => {
          const a = audioRef.current;
          if (a && a.duration) {
            setProgress((a.currentTime / a.duration) * 100);
            setCurrentTime(a.currentTime);
          }
        }}
        onEnded={onStop}
      />
      {/* Progress bar */}
      <div className="h-1 bg-gray-100">
        <div
          className="h-full bg-blue-500 transition-all duration-200"
          style={{ width: `${progress}%` }}
        />
      </div>
      <div className="px-4 py-2.5 flex items-center gap-4">
        {/* Stop button */}
        <button
          onClick={onStop}
          className="w-9 h-9 rounded-full bg-blue-500 text-white flex items-center justify-center hover:bg-blue-600 shrink-0"
        >
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <rect x="6" y="4" width="4" height="16" />
            <rect x="14" y="4" width="4" height="16" />
          </svg>
        </button>
        {/* Info */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900 truncate">{sample.text}</p>
          <p className="text-xs text-gray-400 truncate">
            {sample.voice_name} ({sample.provider}) &middot; {sample.category} &middot; {sample.voice_language}
          </p>
        </div>
        {/* Time */}
        <div className="text-xs text-gray-400 tabular-nums shrink-0">
          {currentTime.toFixed(1)}s / {sample.duration_s.toFixed(1)}s
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function AudioBrowser() {
  // Filters
  const [status, setStatus] = useState("");
  const [provider, setProvider] = useState("");
  const [gender, setGender] = useState("");
  const [language, setLanguage] = useState("");
  const [category, setCategory] = useState("");
  const [accent, setAccent] = useState("");
  const [textSearch, setTextSearch] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortDir, setSortDir] = useState("desc");
  const [page, setPage] = useState(0);
  const pageSize = 50;

  // Audio
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [playingSample, setPlayingSample] = useState<SampleBrowseItem | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  // Queries
  const filters = useQuery({
    queryKey: ["sample-filters"],
    queryFn: fetchSampleFilters,
  });

  const samples = useQuery({
    queryKey: [
      "browse-samples",
      status, provider, gender, language, category, accent, textSearch,
      sortBy, sortDir, page,
    ],
    queryFn: () =>
      browseSamples({
        status: status || undefined,
        provider: provider || undefined,
        gender: gender || undefined,
        language: language || undefined,
        category: category || undefined,
        accent: accent || undefined,
        text_search: textSearch || undefined,
        sort_by: sortBy,
        sort_dir: sortDir,
        limit: pageSize,
        offset: page * pageSize,
      }),
    placeholderData: (prev) => prev,
  });

  const totalPages = Math.ceil((samples.data?.total ?? 0) / pageSize);

  const playSample = useCallback((sample: SampleBrowseItem) => {
    if (audioRef.current) {
      audioRef.current.pause();
    }
    setPlayingId(sample.id);
    setPlayingSample(sample);
  }, []);

  const stopPlaying = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
    }
    setPlayingId(null);
    setPlayingSample(null);
  }, []);

  const resetFilters = () => {
    setStatus("");
    setProvider("");
    setGender("");
    setLanguage("");
    setCategory("");
    setAccent("");
    setTextSearch("");
    setPage(0);
  };

  const hasActiveFilters =
    status || provider || gender || language || category || accent || textSearch;

  const f = filters.data;

  return (
    <div className={`p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto ${playingSample ? "pb-24" : ""}`}>
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Audio Browser</h2>
        <p className="text-sm text-gray-500 mt-1">
          Browse, filter, and play {samples.data?.total?.toLocaleString() ?? "..."} speech samples
        </p>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 sm:p-5 mb-6">
        <div className="flex flex-col sm:flex-row sm:items-end gap-4 mb-4">
          {/* Text search */}
          <div className="flex-1">
            <label className="block text-[10px] font-medium text-gray-400 uppercase tracking-wider mb-1">
              Search text
            </label>
            <input
              type="text"
              value={textSearch}
              onChange={(e) => {
                setTextSearch(e.target.value);
                setPage(0);
              }}
              placeholder="Search utterance text..."
              className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          {hasActiveFilters && (
            <button
              onClick={resetFilters}
              className="px-3 py-1.5 text-xs font-medium text-gray-500 hover:text-gray-700 border border-gray-200 rounded-lg hover:bg-gray-50 shrink-0"
            >
              Clear filters
            </button>
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
          <FilterSelect
            label="Status"
            value={status}
            options={f?.statuses ?? ["ready", "failed", "pending"]}
            onChange={(v) => { setStatus(v); setPage(0); }}
          />
          <FilterSelect
            label="Provider"
            value={provider}
            options={f?.providers ?? []}
            onChange={(v) => { setProvider(v); setPage(0); }}
          />
          <FilterSelect
            label="Gender"
            value={gender}
            options={f?.genders ?? []}
            onChange={(v) => { setGender(v); setPage(0); }}
          />
          <FilterSelect
            label="Language"
            value={language}
            options={f?.languages ?? []}
            onChange={(v) => { setLanguage(v); setPage(0); }}
          />
          <FilterSelect
            label="Category"
            value={category}
            options={f?.categories ?? []}
            onChange={(v) => { setCategory(v); setPage(0); }}
          />
          <FilterSelect
            label="Accent"
            value={accent}
            options={f?.accents ?? []}
            onChange={(v) => { setAccent(v); setPage(0); }}
          />
        </div>
      </div>

      {/* Results header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-3">
        <div className="text-sm text-gray-500">
          {samples.data ? (
            <>
              <span className="font-semibold text-gray-900">{samples.data.total.toLocaleString()}</span>{" "}
              samples
              {hasActiveFilters && <span className="text-blue-500 ml-1">(filtered)</span>}
            </>
          ) : (
            "Loading..."
          )}
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-400">Sort:</label>
          <select
            value={`${sortBy}:${sortDir}`}
            onChange={(e) => {
              const [sb, sd] = e.target.value.split(":");
              setSortBy(sb);
              setSortDir(sd);
              setPage(0);
            }}
            className="border border-gray-200 rounded-lg px-2 py-1 text-xs bg-white"
          >
            <option value="created_at:desc">Newest first</option>
            <option value="created_at:asc">Oldest first</option>
            <option value="duration_s:desc">Longest first</option>
            <option value="duration_s:asc">Shortest first</option>
            <option value="provider:asc">Provider A-Z</option>
            <option value="category:asc">Category A-Z</option>
          </select>
        </div>
      </div>

      {/* Results table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[700px]">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100 bg-gray-50/50">
                <th className="px-3 py-2.5 font-medium w-10" />
                <th className="px-3 py-2.5 font-medium">Text</th>
                <th className="px-3 py-2.5 font-medium">Voice</th>
                <th className="px-3 py-2.5 font-medium">Provider</th>
                <th className="px-3 py-2.5 font-medium">Category</th>
                <th className="px-3 py-2.5 font-medium">Lang</th>
                <th className="px-3 py-2.5 font-medium">Duration</th>
                <th className="px-3 py-2.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {samples.isLoading && (
                <tr>
                  <td colSpan={8} className="px-3 py-12 text-center text-gray-400">
                    <div className="flex items-center justify-center gap-2">
                      <svg className="animate-spin h-4 w-4 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      Loading samples...
                    </div>
                  </td>
                </tr>
              )}
              {samples.data?.items.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-3 py-12 text-center text-gray-400">
                    No samples match your filters.
                    {hasActiveFilters && (
                      <button
                        onClick={resetFilters}
                        className="ml-2 text-blue-500 hover:text-blue-700 underline"
                      >
                        Clear filters
                      </button>
                    )}
                  </td>
                </tr>
              )}
              {samples.data?.items.map((s) => (
                <tr
                  key={s.id}
                  className={`border-b border-gray-50 hover:bg-blue-50/30 transition-colors cursor-pointer ${
                    playingId === s.id ? "bg-blue-50" : ""
                  }`}
                  onClick={() =>
                    s.status === "ready"
                      ? playingId === s.id
                        ? stopPlaying()
                        : playSample(s)
                      : undefined
                  }
                >
                  <td className="px-3 py-2">
                    {s.status === "ready" ? (
                      <MiniPlayer
                        sample={s}
                        isPlaying={playingId === s.id}
                        onPlay={() => playSample(s)}
                        onStop={stopPlaying}
                      />
                    ) : (
                      <div className="w-8 h-8" />
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <p className="text-gray-900 truncate max-w-xs" title={s.text}>
                      {s.text}
                    </p>
                    {s.expected_intent && (
                      <p className="text-[10px] text-gray-400 mt-0.5">
                        intent: {s.expected_intent}
                      </p>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <p className="text-gray-700 text-xs font-medium">{s.voice_name}</p>
                    <p className="text-[10px] text-gray-400">
                      {s.gender}{s.accent ? ` / ${s.accent}` : ""}
                    </p>
                  </td>
                  <td className="px-3 py-2">
                    <ProviderBadge provider={s.provider} />
                  </td>
                  <td className="px-3 py-2">
                    <span className="text-xs text-gray-600 capitalize">
                      {s.category.replace("_", " ")}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span className="text-xs text-gray-500">{s.voice_language}</span>
                  </td>
                  <td className="px-3 py-2">
                    <DurationBar durationS={s.duration_s} />
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge status={s.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 bg-gray-50/30">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1.5 text-xs font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <span className="text-xs text-gray-500">
              Page {page + 1} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1.5 text-xs font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        )}
      </div>

      {/* Now Playing bar */}
      {playingSample && (
        <NowPlaying
          sample={playingSample}
          audioRef={audioRef}
          onStop={stopPlaying}
        />
      )}
    </div>
  );
}
