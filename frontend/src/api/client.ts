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
  telephony_enabled: boolean;
}

export interface SweepPreview {
  total_cases: number;
  breakdown: Record<string, number>;
  estimated_duration_minutes: number | null;
}

export interface RunResponse {
  id: string;
  test_suite_id: string;
  suite_name: string | null;
  status: string;
  total_cases: number;
  completed_cases: number;
  failed_cases: number;
  skipped_cases: number;
  progress_pct: number;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string | null;
  created_at: string | null;
  error_message: string | null;
  error_details: Record<string, unknown> | null;
}

export interface StatsResponse {
  total_tests: number;
  completed: number;
  errors: number;
  overall_pass_rate: number | null;
  overall_mean_score: number | null;
  mean_latency_ms: number | null;
  mean_wer: number | null;
  median_wer: number | null;
  wer_sample_size: number | null;
  accuracy_by_noise_level: Array<Record<string, unknown>> | null;
  accuracy_by_backend: Array<Record<string, unknown>> | null;
  wer_by_noise_level: Array<Record<string, unknown>> | null;
  wer_by_backend: Array<Record<string, unknown>> | null;
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
  noise_level_db: number;
  speech_level_db: number;
  delay_ms: number;
  gain_db: number;
  noise_type: string;
  original_text: string | null;
  expected_intent: string | null;
  expected_action: string | null;
  llm_response_text: string | null;
  asr_transcript: string | null;
  wer: number | null;
  eval_score: number | null;
  eval_passed: boolean | null;
  evaluator_type: string | null;
  total_latency_ms: number | null;
  llm_latency_ms: number | null;
  asr_latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  error: string | null;
  error_stage: string | null;
  has_degraded_audio: boolean;
  has_downlink_audio?: boolean;
  created_at: string | null;
  telephony_metadata?: Record<string, unknown> | null;
  telephony_eval?: Record<string, unknown> | null;
  doubletalk_metrics?: Record<string, unknown> | null;
}

export interface AECResidualConfigRequest {
  suppression_db: number;
  residual_type: string;
  nonlinear_distortion: number;
}

export interface NetworkConfigRequest {
  packet_loss_pct: number;
  packet_loss_pattern: string;
  burst_length_ms: number;
  jitter_ms: number;
  codec_switching: boolean;
}

export interface FarEndConfig {
  enabled: boolean;
  speech_level_db_values: number[];
  offset_ms_values: number[];
}

export interface TelephonyConfig {
  bt_codec_types: string[];
  agc_presets: string[];
  aec_configs: AECResidualConfigRequest[];
  network_configs: NetworkConfigRequest[];
  far_end: FarEndConfig;
}

export interface SweepConfigRequest {
  name: string;
  description?: string;
  noise_level_db_values: number[];
  speech_level_db_values?: number[];
  noise_types: string[];
  interferer_level_db_values?: (number | null)[];
  echo: {
    delay_ms_values: number[];
    gain_db_values: number[];
    eq_chains?: unknown[];
  };
  pipelines: string[];
  llm_backends: string[];
  voice_ids?: string[];
  voice_providers?: string[];
  voice_languages?: string[];
  voice_genders?: string[];
  corpus_categories?: string[];
  corpus_entry_ids?: string[];
  system_prompt?: string;
  max_samples?: number | null;
  telephony?: TelephonyConfig;
}

export interface AudioSourcesResponse {
  providers: Record<string, number>;
  categories: Record<string, number>;
  languages: Record<string, number>;
  genders: Record<string, number>;
  total_samples: number;
}

export interface SynthesizeRequest {
  corpus_entry_ids?: string[];
  voice_ids?: string[];
  categories?: string[];
  languages?: string[];
  providers?: string[];
  genders?: string[];
  voice_languages?: string[];
  max_corpus?: number;
  max_voices?: number;
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

export function seedCorpus(
  languages?: string[],
  perCategory?: number
): Promise<{ status: string; entries_created: number; languages: string[] }> {
  return request("/speech/corpus/seed", {
    method: "POST",
    body: JSON.stringify({
      ...(languages ? { languages } : {}),
      ...(perCategory ? { per_category: perCategory } : {}),
    }),
  });
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

export interface GeneratePreview {
  corpus_entries: number;
  voices: number;
  total_combinations: number;
  estimated_size_mb: number;
  avg_duration_s: number;
}

export function synthesizePreview(
  req: SynthesizeRequest
): Promise<GeneratePreview> {
  return request("/speech/synthesize/preview", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function synthesizeSpeech(
  req: SynthesizeRequest
): Promise<SynthesizeResponse> {
  return request("/speech/synthesize", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export interface GenerateWavsRequest {
  categories?: string[];
  languages?: string[];
  providers?: string[];
  genders?: string[];
  voice_languages?: string[];
  max_corpus?: number;
  max_voices?: number;
  max_total?: number;
}

export interface GenerateWavsResponse {
  total_queued: number;
  generated: number;
  failed: number;
  errors: string[];
}

export interface SpeechStatsResponse {
  by_provider: Record<string, { ready: number; failed: number; pending: number; generating: number }>;
  totals: { ready: number; failed: number; pending: number; generating: number };
}

export interface CorpusStatsResponse {
  by_category: Record<string, number>;
  by_language: Record<string, number>;
  total: number;
}

export function generateWavs(
  req: GenerateWavsRequest
): Promise<GenerateWavsResponse> {
  return request("/speech/generate-wavs", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function fetchSpeechStats(): Promise<SpeechStatsResponse> {
  return request("/speech/stats");
}

export function retryFailedSamples(
  providers?: string[]
): Promise<GenerateWavsResponse> {
  return request("/speech/generate-wavs/retry", {
    method: "POST",
    body: JSON.stringify({ providers }),
  });
}

export function fetchCorpusStats(): Promise<CorpusStatsResponse> {
  return request("/speech/corpus/stats");
}

export interface SampleBrowseItem {
  id: string;
  status: string;
  file_path: string;
  duration_s: number;
  sample_rate: number;
  created_at: string;
  voice_name: string;
  voice_id_str: string;
  provider: string;
  gender: string;
  accent: string | null;
  voice_language: string;
  text: string;
  category: string;
  expected_intent: string | null;
  expected_action: string | null;
  corpus_language: string;
}

export interface SampleBrowsePage {
  items: SampleBrowseItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface SampleFilters {
  providers: string[];
  genders: string[];
  languages: string[];
  categories: string[];
  accents: string[];
  statuses: string[];
}

export function browseSamples(filters?: {
  status?: string;
  provider?: string;
  gender?: string;
  language?: string;
  corpus_language?: string;
  category?: string;
  accent?: string;
  voice_name?: string;
  text_search?: string;
  sort_by?: string;
  sort_dir?: string;
  limit?: number;
  offset?: number;
}): Promise<SampleBrowsePage> {
  const params = new URLSearchParams();
  if (filters) {
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== "") params.set(k, String(v));
    });
  }
  const qs = params.toString();
  return request(`/speech/samples${qs ? `?${qs}` : ""}`);
}

export function fetchSampleFilters(): Promise<SampleFilters> {
  return request("/speech/samples/filters");
}

export function getSampleAudioUrl(sampleId: string): string {
  return `/api/speech/samples/${sampleId}/audio`;
}

// ---------------------------------------------------------------------------
// Cars
// ---------------------------------------------------------------------------

export interface CarResponse {
  id: string;
  name: string;
  description: string | null;
  metadata_json: Record<string, unknown> | null;
  noise_file_count: number;
}

export function listCars(): Promise<CarResponse[]> {
  return request("/cars/");
}

export function getCarNoiseTypes(carId: string, noiseCategory?: string): Promise<string[]> {
  const qs = noiseCategory ? `?noise_category=${noiseCategory}` : "";
  return request(`/cars/${carId}/noise-types${qs}`);
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

export async function listLLMTestSuites(): Promise<TestSuiteResponse[]> {
  const all = await listTestSuites();
  return all.filter((s) => !s.telephony_enabled);
}

export async function listTelephonySuites(): Promise<TestSuiteResponse[]> {
  const all = await listTestSuites();
  return all.filter((s) => s.telephony_enabled);
}

export function fetchAudioSources(): Promise<AudioSourcesResponse> {
  return request("/tests/suites/audio-sources");
}

export function deleteTestSuite(
  suiteId: string
): Promise<{ status: string; id: string }> {
  return request(`/tests/suites/${suiteId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

export function launchRun(
  suiteId: string,
  resume = false,
  sampleSize?: number
): Promise<RunResponse> {
  return request("/runs", {
    method: "POST",
    body: JSON.stringify({
      test_suite_id: suiteId,
      resume,
      sample_size: sampleSize ?? null,
    }),
  });
}

export function listRuns(): Promise<RunResponse[]> {
  return request("/runs");
}

export async function listLLMRuns(): Promise<RunResponse[]> {
  const [runs, telSuites] = await Promise.all([listRuns(), listTelephonySuites()]);
  const telSuiteIds = new Set(telSuites.map((s) => s.id));
  return runs.filter((r) => !telSuiteIds.has(r.test_suite_id));
}

export async function listTelephonyRuns(): Promise<RunResponse[]> {
  const [runs, telSuites] = await Promise.all([listRuns(), listTelephonySuites()]);
  const telSuiteIds = new Set(telSuites.map((s) => s.id));
  return runs.filter((r) => telSuiteIds.has(r.test_suite_id));
}

export function getRun(runId: string): Promise<RunResponse> {
  return request(`/runs/${runId}`);
}

export function cancelRun(runId: string): Promise<void> {
  return request(`/runs/${runId}`, { method: "DELETE" });
}

export function deleteRun(
  runId: string
): Promise<{ status: string; id: string }> {
  return request(`/runs/${runId}/permanent`, { method: "DELETE" });
}

export async function activeRunCount(): Promise<number> {
  const runs = await listRuns();
  return runs.filter((r) => r.status === "running").length;
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
    noise_level_db?: number;
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
// Dashboard
// ---------------------------------------------------------------------------

export interface DashboardResponse {
  total_runs: number;
  total_cases: number;
  overall_pass_rate: number | null;
  overall_mean_score: number | null;
  mean_latency_ms: number | null;
  mean_wer: number | null;
  accuracy_by_noise_level: Array<Record<string, unknown>> | null;
  accuracy_by_speech_level: Array<Record<string, unknown>> | null;
  accuracy_by_noise: Array<Record<string, unknown>> | null;
  accuracy_by_backend: Array<Record<string, unknown>> | null;
  wer_by_noise_level: Array<Record<string, unknown>> | null;
  wer_by_backend: Array<Record<string, unknown>> | null;
  speech_level_heatmap: {
    row_labels: number[];
    col_labels: number[];
    values: Array<Array<number | null>>;
    row_name: string;
    col_name: string;
  } | null;
  echo_heatmap: {
    row_labels: number[];
    col_labels: number[];
    values: Array<Array<number | null>>;
    row_name: string;
    col_name: string;
  } | null;
  latency_by_backend: Array<Record<string, unknown>> | null;
  parameter_effects: Record<string, unknown> | null;
  run_history: Array<Record<string, unknown>> | null;
  accuracy_by_voice_provider?: Array<Record<string, unknown>>;
  accuracy_by_corpus_category?: Array<Record<string, unknown>>;
  accuracy_by_voice_gender?: Array<Record<string, unknown>>;
}

export interface AnalyticsFilters {
  llm_backend?: string;
  pipeline?: string;
  noise_type?: string;
  voice_provider?: string;
  corpus_category?: string;
  voice_gender?: string;
}

export interface InsightsResponse {
  analysis: string;
  stats_summary: Record<string, unknown>;
  generated_at: string;
}

export function fetchInsights(backend = "auto"): Promise<InsightsResponse> {
  return request(`/results/dashboard/insights?backend=${encodeURIComponent(backend)}`, { method: "POST" });
}

export function fetchDashboard(): Promise<DashboardResponse> {
  return request("/results/dashboard/aggregate");
}

// ---------------------------------------------------------------------------
// System Health
// ---------------------------------------------------------------------------

export interface SystemMetrics {
  cpu_percent: number;
  cpu_count: number;
  ram_total_gb: number;
  ram_used_gb: number;
  ram_percent: number;
  gpu: Array<{
    name: string;
    util_percent: number | null;
    mem_used_gb: number | null;
    mem_total_gb: number | null;
    mem_percent: number | null;
    temperature_c: number | null;
  }> | null;
  disk_percent: number | null;
  uptime_s: number | null;
  hostname: string | null;
  platform: string | null;
}

export interface WorkerActivity {
  run_id: string | null;
  status: string;
  current_case: Record<string, unknown> | null;
  cases_per_min: number;
  last_heartbeat: string | null;
  recent_errors: Array<Record<string, unknown>> | null;
  error_budget: Record<string, { errors: number; total: number; consecutive: number }> | null;
  worker_log: Array<{ level: string; message: string; timestamp: string }> | null;
}

export interface HealthResponse {
  system: SystemMetrics;
  worker: WorkerActivity;
  timestamp: string;
}

export function fetchSystemHealth(): Promise<HealthResponse> {
  return request("/health/system");
}

export function getAudioUrl(runId: string, caseId: string, type: "clean" | "degraded" | "echo" | "downlink" = "degraded"): string {
  return `/api/results/${runId}/cases/${caseId}/audio?type=${type}`;
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export interface KeyStatusResponse {
  openai: boolean;
  google: boolean;
  anthropic: boolean;
  elevenlabs: boolean;
  deepgram: boolean;
  azure: boolean;
  ollama: boolean;
}

export function fetchKeyStatus(): Promise<KeyStatusResponse> {
  return request("/settings/key-status");
}

export interface SettingsResponse {
  openai_api_key: string | null;
  google_api_key: string | null;
  anthropic_api_key: string | null;
  elevenlabs_api_key: string | null;
  deepgram_api_key: string | null;
  azure_speech_key: string | null;
  azure_speech_region: string | null;
  default_llm_backend: string | null;
  default_stt_backend: string | null;
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

export interface OllamaModel {
  name: string;
  size_gb: number | null;
  parameter_size: string | null;
  modified_at: string | null;
}

export interface OllamaStatusResponse {
  connected: boolean;
  url: string;
  models: OllamaModel[];
  error: string | null;
}

export function fetchOllamaModels(): Promise<OllamaStatusResponse> {
  return request("/settings/ollama-models");
}

export interface TestLLMResponse {
  success: boolean;
  response: string | null;
  error: string | null;
  latency_ms: number | null;
}

export function testLLM(backend: string, prompt = "Say hello in one sentence."): Promise<TestLLMResponse> {
  return request("/settings/test-llm", {
    method: "POST",
    body: JSON.stringify({ backend, prompt }),
  });
}

export interface SlurpImportResponse {
  imported: number;
  converted: number;
  skipped: number;
  failed: number;
  total_audio_files_found: number;
  has_annotations: boolean;
  annotation_count: number;
  by_scenario: Record<string, number>;
}

export function importSlurp(maxPerScenario = 100): Promise<SlurpImportResponse> {
  return request(`/speech/import-slurp?max_per_scenario=${maxPerScenario}`, {
    method: "POST",
  });
}
