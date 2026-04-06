// ---------------------------------------------------------------------------
// API Types — aligned with backend Pydantic schemas
// ---------------------------------------------------------------------------

export interface VoiceResponse {
  provider: string;
  voice_id: string;
  name: string;
  gender: string;
  age_group: string;
  accent: string;
  language: string;
}

export interface CorpusEntryResponse {
  id: string;
  text: string;
  category: string;
  expected_intent: string;
  expected_action: string | null;
  language: string;
}

export interface TestSuiteResponse {
  id: string;
  name: string;
  description: string;
  status: string;
  total_cases: number;
  created_at: string;
}

export interface SweepPreview {
  total_cases: number;
  breakdown: Record<string, number>;
  estimated_duration_minutes: number | null;
}

export interface RunResponse {
  id: string;
  test_suite_id: string;
  status: string;
  total_cases: number;
  completed_cases: number;
  failed_cases: number;
  progress_pct: number;
  started_at: string | null;
  completed_at: string | null;
}

export interface StatsResponse {
  total_tests: number;
  completed: number;
  errors: number;
  overall_pass_rate: number | null;
  overall_mean_score: number | null;
  mean_latency_ms: number | null;
  accuracy_by_snr: Array<Record<string, unknown>> | null;
  accuracy_by_backend: Array<Record<string, unknown>> | null;
  backend_comparison: Array<Record<string, unknown>> | null;
  parameter_effects: Record<string, unknown> | null;
}

export interface HeatmapResponse {
  row_labels: number[];
  col_labels: number[];
  values: Array<Array<number | null>>;
  row_name: string;
  col_name: string;
}

export interface ResultResponse {
  test_case_id: string;
  pipeline_type: string;
  llm_backend: string;
  snr_db: number;
  delay_ms: number;
  gain_db: number;
  noise_type: string;
  llm_response_text: string | null;
  asr_transcript: string | null;
  eval_score: number | null;
  eval_passed: boolean | null;
  total_latency_ms: number | null;
  error: string | null;
}

export interface SweepConfigRequest {
  name: string;
  description?: string;
  snr_db_values: number[];
  noise_types: string[];
  echo: {
    delay_ms_values: number[];
    gain_db_values: number[];
    eq_chains?: unknown[];
  };
  pipelines: string[];
  llm_backends: string[];
  voice_ids?: string[];
  corpus_categories?: string[];
  corpus_entry_ids?: string[];
  system_prompt?: string;
}

export interface SynthesizeRequest {
  corpus_entry_ids?: string[];
  voice_ids?: string[];
  categories?: string[];
  languages?: string[];
}

export interface SynthesizeResponse {
  task_id: string;
  total_combinations: number;
  status: string;
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Speech / Corpus
// ---------------------------------------------------------------------------

export function fetchVoices(filters?: {
  provider?: string;
  gender?: string;
  language?: string;
  accent?: string;
}): Promise<VoiceResponse[]> {
  const params = new URLSearchParams();
  if (filters) {
    Object.entries(filters).forEach(([k, v]) => {
      if (v) params.set(k, v);
    });
  }
  const qs = params.toString();
  return request(`/speech/voices${qs ? `?${qs}` : ""}`);
}

export interface SyncVoicesResponse {
  synced: number;
  providers: string[];
  errors: string[];
}

export function syncVoices(): Promise<SyncVoicesResponse> {
  return request("/speech/voices/sync", { method: "POST" });
}

export function seedCorpus(): Promise<{ status: string; entries_created: number }> {
  return request("/speech/corpus/seed", { method: "POST" });
}

export function fetchCorpus(filters?: {
  category?: string;
  language?: string;
  limit?: number;
  offset?: number;
}): Promise<CorpusEntryResponse[]> {
  const params = new URLSearchParams();
  if (filters) {
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined) params.set(k, String(v));
    });
  }
  const qs = params.toString();
  return request(`/speech/corpus${qs ? `?${qs}` : ""}`);
}

export function synthesizeSpeech(
  req: SynthesizeRequest
): Promise<SynthesizeResponse> {
  return request("/speech/synthesize", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ---------------------------------------------------------------------------
// Test Suites
// ---------------------------------------------------------------------------

export function createTestSuite(
  config: SweepConfigRequest
): Promise<TestSuiteResponse> {
  return request("/tests/suites", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export function previewSweep(
  config: SweepConfigRequest
): Promise<SweepPreview> {
  return request("/tests/suites/preview", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export function listTestSuites(): Promise<TestSuiteResponse[]> {
  return request("/tests/suites");
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

export function launchRun(
  suiteId: string,
  resume = false
): Promise<RunResponse> {
  return request("/runs", {
    method: "POST",
    body: JSON.stringify({ test_suite_id: suiteId, resume }),
  });
}

export function listRuns(): Promise<RunResponse[]> {
  return request("/runs");
}

export function getRun(runId: string): Promise<RunResponse> {
  return request(`/runs/${runId}`);
}

export function cancelRun(runId: string): Promise<void> {
  return request(`/runs/${runId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Results
// ---------------------------------------------------------------------------

export function getRunStats(runId: string): Promise<StatsResponse> {
  return request(`/results/${runId}/stats`);
}

export function getHeatmap(
  runId: string,
  rowParam: string,
  colParam: string
): Promise<HeatmapResponse> {
  return request(
    `/results/${runId}/heatmap?row_param=${rowParam}&col_param=${colParam}`
  );
}

export function queryResults(
  runId: string,
  filters?: {
    llm_backend?: string;
    pipeline?: string;
    snr_db?: number;
    passed?: boolean;
    limit?: number;
    offset?: number;
  }
): Promise<ResultResponse[]> {
  const params = new URLSearchParams({ run_id: runId });
  if (filters) {
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined) params.set(k, String(v));
    });
  }
  return request(`/results?${params.toString()}`);
}

export function getExportUrl(
  runId: string,
  format: "csv" | "json" | "parquet"
): string {
  return `/api/results/${runId}/export?format=${format}`;
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export interface SettingsResponse {
  openai_api_key: string | null;
  google_api_key: string | null;
  anthropic_api_key: string | null;
  elevenlabs_api_key: string | null;
  ollama_base_url: string;
  default_sample_rate: number;
  max_concurrent_workers: number;
}

export interface UpdateSettingsResponse {
  status: string;
  keys_changed: string[];
}

export function fetchSettings(): Promise<SettingsResponse> {
  return request("/settings");
}

export function updateSettings(
  updates: Record<string, string>
): Promise<UpdateSettingsResponse> {
  return request("/settings", {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}
