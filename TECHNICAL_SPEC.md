# Audio LLM Test Platform — Technical Specification

## 1. Purpose

A web-based platform for evaluating how well LLMs understand human speech in automotive cabin conditions. The system synthesizes diverse speech inputs, degrades them with parameterized noise and acoustic echo (simulating a car's speaker-to-microphone feedback path), sends them through LLMs via two pipelines, evaluates correctness, and provides statistical analysis across 10K+ test cases.

---

## 2. System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     React Dashboard (Vite)                   │
│  Dashboard | Speech Corpus | Test Suites | Run Monitor | Results │
└──────────────────────┬───────────────────────────────────────┘
                       │ REST + WebSocket (/api/*)
┌──────────────────────▼───────────────────────────────────────┐
│                    FastAPI Backend (uvicorn)                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
│  │  Speech   │  │  Audio   │  │   LLM    │  │  Execution  │ │
│  │Synthesis  │  │Processing│  │ Backends │  │   Engine    │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────────┘ │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────────────┐ │
│  │Evaluation│  │  Stats   │  │   PostgreSQL + Redis (arq) │ │
│  └──────────┘  └──────────┘  └────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS + Recharts | Dashboard UI |
| Backend API | FastAPI (async) + uvicorn | REST API + WebSocket |
| Database | PostgreSQL 16 (asyncpg + SQLAlchemy 2.0) | Persistent storage |
| Task Queue | Redis 7 + arq | Background job execution |
| Audio DSP | NumPy + SciPy (sosfilt, signal) + soundfile | Noise, filters, echo, mixing |
| TTS | OpenAI TTS, Google Cloud TTS, ElevenLabs | Speech synthesis |
| LLM Backends | OpenAI GPT-4o audio, Gemini, Claude, Ollama | Models under test |
| ASR | Whisper (local + API) | Speech-to-text for Pipeline B |
| Statistics | pandas + scipy.stats | ANOVA, CI, pairwise tests |

---

## 3. Audio Processing Pipeline

### 3.1 Signal Flow

```
Clean Speech WAV (16 kHz, float64)
        │
        ├──► Noise Generator ──► Optional Filter ──► SNR Mixer
        │                                              │
        │         ┌────────────────────────────────────┘
        │         ▼
        │    Echo Mixer ◄── EQ Chain ◄── Delay+Gain ◄── LLM TTS Output
        │         │
        │         ▼
        │    Degraded Audio
        │         │
        ├── Pipeline A: ──► Multimodal LLM ──► Response
        │
        └── Pipeline B: ──► Whisper ASR ──► Transcript ──► Text LLM ──► Response
```

### 3.2 AudioBuffer (`backend/app/audio/types.py`)

Core immutable data type for all audio operations:

```python
@dataclass(frozen=True, slots=True)
class AudioBuffer:
    samples: np.ndarray   # float64, mono, range [-1.0, 1.0]
    sample_rate: int      # Hz (canonical: 16000)
```

Properties: `duration_s`, `rms`, `peak`, `rms_db`, `num_samples`
Methods: `resample(target_sr)`, `normalize(target_rms|target_peak)`, `trim_to_duration(s)`, `loop_to_length(n)`

**Sample rate convention**: 16 kHz internal (Whisper native). Upsample to 24 kHz only at GPT-4o API boundary.

### 3.3 Noise Generation (`backend/app/audio/noise.py`)

**Pink noise**: FFT of white noise → scale magnitudes by 1/√f → IFFT. Normalized to unit RMS.

**Pink noise + LPF** (default car noise): Pink noise through 2nd-order Butterworth LPF at 100 Hz:
```python
sos = scipy.signal.butter(2, 100, btype='low', fs=16000, output='sos')
filtered = scipy.signal.sosfilt(sos, pink_samples)
```

**File-based noise**: Load WAV, resample, loop to target length, RMS-normalize.

### 3.4 SNR Mixing (`backend/app/audio/mixer.py`)

```
SNR = 20 * log10(rms_speech / rms_noise)
→ noise_scale = rms_speech / (rms_noise * 10^(snr_db/20))
→ mixed = speech + noise_scale * noise
→ soft_clip via np.tanh()
```

### 3.5 Filter Chain (`backend/app/audio/filters.py`)

All filters use **SOS (second-order sections)** form for numerical stability. Coefficient formulas from the **Audio EQ Cookbook** (Robert Bristow-Johnson).

Supported filter types:

| Type | Parameters | Coefficients |
|------|-----------|-------------|
| LPF | frequency, Q | Standard 2nd-order biquad |
| HPF | frequency, Q | Standard 2nd-order biquad |
| Peaking EQ | frequency, Q, gain_db | A = 10^(gain/40), alpha = sin(w0)/(2Q) |
| Low Shelf | frequency, Q, gain_db | With 2√A·alpha coupling term |
| High Shelf | frequency, Q, gain_db | With 2√A·alpha coupling term |

`FilterChain` concatenates multiple SOS sections into an Nx6 matrix and applies with a single `scipy.signal.sosfilt()` call.

### 3.6 Echo Path (`backend/app/audio/echo.py`)

Models speaker-to-microphone acoustic feedback in a car cabin:

```python
@dataclass
class EchoConfig:
    delay_ms: float      # 0-500ms (speaker-to-mic propagation)
    gain_db: float       # -100 to 0 dB (echo attenuation)
    eq_chain: list[FilterSpec]  # Cabin frequency response
```

Processing: delay (sample offset) → linear gain → EQ filter chain → sum with mic input.

**Typical car cabin EQ**: HPF 80Hz + LPF 6kHz + peaking 2.5kHz (+4dB, Q=2.0)

### 3.7 Echo Feedback Loop (`backend/app/pipeline/echo_feedback.py`)

Multi-turn simulation (NOT real-time):
1. Add noise to clean speech
2. Send to LLM, get response
3. If LLM returns audio (GPT-4o), use it; else TTS the text
4. Apply echo path to LLM output audio
5. Mix echo into next turn's input
6. Repeat for N turns

This gives deterministic, reproducible results.

---

## 4. Speech Synthesis

### 4.1 TTS Providers

| Provider | Module | Voices | Best For |
|----------|--------|--------|----------|
| OpenAI | `speech/tts_openai.py` | 6 (alloy, echo, fable, onyx, nova, shimmer) | Baseline, fast |
| Google Cloud | `speech/tts_google.py` | 100+ WaveNet/Neural2 | Accent/language diversity |
| ElevenLabs | `speech/tts_elevenlabs.py` | Many, voice cloning | Natural quality, age variety |

All implement the `TTSProvider` protocol:
```python
class TTSProvider(Protocol):
    async def synthesize(self, text: str, voice_id: str) -> AudioBuffer
    async def list_voices(self) -> list[VoiceInfo]
```

### 4.2 Voice Catalog (`speech/catalog.py`)

Metadata per voice: provider, voice_id, name, gender, age_group, accent, language.

`get_diverse_voice_set(count, language)` uses round-robin bucket sampling across gender, age, accent, and provider to maximize demographic coverage.

### 4.3 Corpus (`speech/corpus.py`)

- **100 Harvard sentences** (Lists 1-10): phonetically balanced, standard in speech research
- **Command templates** (5 categories × 5 templates × 10 fill values):
  - Navigation: "Navigate to {destination}", "Find the nearest {poi_type}"
  - Media: "Play {song} by {artist}", "Skip this song"
  - Climate: "Set temperature to {temp} degrees", "Turn on the AC"
  - Phone: "Call {contact}", "Read my messages"
  - General: "What's the weather", "Set a timer for {duration}"

Each template maps to an expected_intent and expected_action for evaluation.

---

## 5. LLM Backends

### 5.1 Backend Protocol

```python
class LLMBackend(Protocol):
    name: str
    supports_audio_input: bool
    rate_limit: RateLimitConfig
    async def query_with_audio(self, audio, system_prompt, context?) -> LLMResponse
    async def query_with_text(self, text, system_prompt, context?) -> LLMResponse
```

### 5.2 Implementations

| Backend | Module | Audio Input | Notes |
|---------|--------|-------------|-------|
| GPT-4o Audio | `llm/openai_audio.py` | Yes | PCM16 @ 24kHz, returns audio + text |
| Gemini | `llm/gemini.py` | Yes | WAV inline data |
| Claude | `llm/anthropic_backend.py` | No | Pipeline B only |
| Ollama (local) | `llm/ollama.py` | No | Pipeline B only |

### 5.3 ASR Backend

```python
class ASRBackend(Protocol):
    async def transcribe(self, audio: AudioBuffer) -> Transcription
```

Two implementations: `WhisperLocalBackend` (openai-whisper, runs in executor) and `WhisperAPIBackend` (OpenAI API).

---

## 6. Test Pipelines

### Pipeline A — Direct Audio
`backend/app/pipeline/direct_audio.py`

Clean speech → add noise at SNR → (optional echo) → encode for API → multimodal LLM → evaluate

Only works with backends where `supports_audio_input == True`.

### Pipeline B — ASR + Text
`backend/app/pipeline/asr_text.py`

Clean speech → add noise at SNR → (optional echo) → Whisper transcribe → text LLM → evaluate

Works with all backends. Also captures WER (transcript vs original text).

### Pipeline Echo Feedback
`backend/app/pipeline/echo_feedback.py`

Multi-turn: each turn adds the previous LLM response's audio as echo into the mic input. Configurable `num_turns`.

---

## 7. Evaluation

### 7.1 Command Match (`evaluation/command_match.py`)

For predefined commands with known expected actions:
1. **Exact match**: normalized text comparison (lowercase, strip punctuation)
2. **Fuzzy match**: Levenshtein ratio (threshold 0.8)
3. **Keyword match**: proportion of expected keywords found in response

Score = max(exact, fuzzy, keyword). Pass threshold: 0.6.

### 7.2 LLM-as-Judge (`evaluation/llm_judge.py`)

For open-ended responses. Sends structured rubric to a judge LLM:

```
Rate 1-5:
1: Completely wrong/dangerous
2: Misunderstood
3: Partially correct
4: Correct but suboptimal
5: Perfect
```

Multiple judge calls (default 3) with median for reliability. Score normalized to 0-1.

### 7.3 Metrics (`evaluation/metrics.py`)

- **WER** (Word Error Rate): Levenshtein on words. 0.0 = perfect.
- **CER** (Character Error Rate): Levenshtein on characters.

---

## 8. Execution Engine

### 8.1 Rate Limiter (`execution/rate_limiter.py`)

Token bucket algorithm with asyncio.Semaphore for concurrency:
```python
class TokenBucketRateLimiter:
    requests_per_minute: int
    max_concurrent: int  # asyncio.Semaphore
```

One limiter per LLM backend.

### 8.2 Scheduler (`execution/scheduler.py`)

```python
class TestScheduler:
    async def run(self, test_cases, completed_ids?) -> list[TestResultRecord]
```

- asyncio-based (I/O-bound, not CPU-bound)
- Bounded concurrency via global semaphore (default 50)
- Per-backend rate limiting
- Callbacks: `on_result` (write to DB), `on_progress` (WebSocket broadcast)

### 8.3 Test Case Config

```python
@dataclass
class TestCaseConfig:
    id: str
    speech_file: str
    original_text: str
    expected_intent: str
    snr_db: float
    noise_type: str
    delay_ms: float
    gain_db: float
    pipeline: str           # "direct_audio" or "asr_text"
    llm_backend: str        # e.g. "openai:gpt-4o-audio-preview"
    deterministic_hash: str # SHA-256 for checkpointing
```

### 8.4 Sweep Expansion

The cartesian product of all parameters generates test cases:

```
speech_samples × snr_values × noise_types × delay_values × gain_values × pipelines × backends
```

Each combination gets a deterministic SHA-256 hash for deduplication and resume.

### 8.5 Background Workers (`execution/worker.py`)

arq tasks running in a separate container:
- `run_test_suite(run_id)`: loads config, initializes backends, runs scheduler, writes results to DB
- `synthesize_speech_batch(task_id)`: generates WAV files from TTS providers

---

## 9. Statistical Analysis

### 9.1 Core Analysis (`stats/analysis.py`)

| Analysis | Method | Output |
|----------|--------|--------|
| Accuracy vs parameter | Group-by + mean + 95% CI | Per-group mean, CI bounds |
| CI for proportions | Wilson score interval | Better than normal approx for pass rates |
| CI for means | t-distribution (n≥30) or bootstrap (n<30) | Score confidence bounds |
| Pairwise comparison | McNemar's test (binary), Wilcoxon signed-rank (continuous) | p-values for backend differences |
| Parameter effects | One-way ANOVA per factor | F-statistic, p-value, eta-squared |
| Threshold finding | Logistic regression | P(pass) ~ SNR + delay + gain + backend |

### 9.2 Key Visualizations

1. **Accuracy vs SNR curves**: one line per backend, 95% CI shading — the primary output
2. **SNR × Echo Delay heatmaps**: accuracy as color, one per backend
3. **Backend comparison bars**: grouped by SNR level, with error bars
4. **Parameter sensitivity tornado chart**: from ANOVA effect sizes

---

## 10. Database Schema

### Tables

```
voices
├── id (UUID PK)
├── provider (enum: openai/google/elevenlabs)
├── voice_id (varchar 255)
├── name, gender, age_group, accent, language
└── metadata_json (JSONB)

corpus_entries
├── id (UUID PK)
├── text (text)
├── category (enum: harvard_sentence/navigation/media/climate/phone/general)
├── expected_intent, expected_action
└── language (varchar 10)

speech_samples
├── id (UUID PK)
├── corpus_entry_id (FK → corpus_entries)
├── voice_id (FK → voices)
├── file_path, duration_s, sample_rate
└── status (enum: pending/generating/ready/failed)

test_suites
├── id (UUID PK)
├── name, description
└── status (enum: draft/ready/running/completed/archived)

sweep_configs
├── id (UUID PK)
├── test_suite_id (FK → test_suites)
├── snr_db_values, delay_ms_values, gain_db_values (JSONB arrays)
├── noise_types, pipelines, llm_backends (JSONB arrays)
└── eq_configs (JSONB)

test_cases
├── id (UUID PK)
├── test_suite_id (FK → test_suites)
├── speech_sample_id (FK → speech_samples)
├── snr_db, delay_ms, gain_db, noise_type
├── eq_config_json (JSONB)
├── pipeline (enum: direct_audio/asr_text)
├── llm_backend (varchar 100)
├── status (enum: pending/running/completed/failed)
└── deterministic_hash (varchar 64, UNIQUE)

test_runs
├── id (UUID PK)
├── test_suite_id (FK → test_suites)
├── started_at, completed_at (timestamp)
├── status (enum: pending/running/completed/cancelled/failed)
└── total_cases, completed_cases, failed_cases, progress_pct

test_results
├── id (UUID PK)
├── test_run_id (FK → test_runs)
├── test_case_id (FK → test_cases)
├── llm_response_text, llm_response_audio_path
├── llm_latency_ms
├── asr_transcript, wer
├── evaluation_score (float 0-1), evaluation_passed (bool)
├── evaluation_details_json (JSONB)
└── evaluator_type (varchar 100)
```

All tables have `created_at` and `updated_at` columns via Base class.

---

## 11. REST API

### Speech Corpus

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/speech/voices` | List voices (filter: provider, gender, language, accent) |
| GET | `/api/speech/corpus` | List corpus entries (filter: category, language; paginated) |
| POST | `/api/speech/corpus/seed` | Seed 100 Harvard sentences + 250 car commands |
| POST | `/api/speech/synthesize` | Create pending speech samples (corpus × voices) |
| GET | `/api/speech/samples/{id}/audio` | Stream sample WAV file |

### Test Configuration

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/tests/suites` | Create suite from sweep config (expands cartesian product) |
| GET | `/api/tests/suites` | List all suites with case counts |
| GET | `/api/tests/suites/{id}` | Get suite details |
| POST | `/api/tests/suites/preview` | Preview sweep case count without creating |
| DELETE | `/api/tests/suites/{id}` | Delete suite + cascade |

### Test Runs

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/runs` | Launch run (creates TestRun record) |
| GET | `/api/runs` | List all runs |
| GET | `/api/runs/{id}` | Get run status + progress |
| DELETE | `/api/runs/{id}` | Cancel run |

### Results

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/results` | Query results (filter: run, suite, backend, pipeline, snr, passed) |
| GET | `/api/results/{run_id}/stats` | Full statistical analysis |
| GET | `/api/results/{run_id}/heatmap` | Heatmap data (row_param × col_param) |
| GET | `/api/results/{run_id}/export` | Export CSV/JSON/Parquet |
| GET | `/api/results/{run_id}/cases/{id}/audio` | Stream test case audio |

### WebSocket

| Path | Description |
|------|-------------|
| WS `/api/ws/runs/{id}` | Live progress: `{type: "progress", completed, total, pct}` |

---

## 12. Frontend Pages

### Dashboard (`/`)
Stats cards (total suites, runs, pass rate, latency) + recent runs table + quick actions.

### Speech Corpus (`/corpus`)
3 tabs: Voices (filterable table), Corpus (filterable table), Generate (batch synthesis form).

### Test Suites (`/tests`)
Suite list + new suite form with: SNR chip selector, noise checkboxes, echo delay/gain selectors, pipeline/backend checkboxes. Preview button shows total case count.

### Run Monitor (`/runs/:id`)
WebSocket-connected: live progress bar, per-backend throughput, scrolling result log, cancel button.

### Results (`/results/:id`)
Summary cards + 3 tabs: Charts (accuracy vs SNR LineChart per backend, heatmap), Table (filterable paginated results), Export (CSV/JSON download).

---

## 13. Infrastructure

### Docker Compose Services

```yaml
services:
  db:        postgres:16-alpine     (port 5432)
  redis:     redis:7-alpine         (port 6379)
  backend:   Python 3.12-slim       (port 8000, uvicorn --reload)
  worker:    Same image             (arq worker)
  frontend:  node:20-alpine         (port 5173, vite dev --host)
```

### Environment Variables

```
ALT_DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/audio_llm_test
ALT_REDIS_URL=redis://redis:6379
ALT_OPENAI_API_KEY=sk-...
ALT_GOOGLE_API_KEY=...
ALT_ANTHROPIC_API_KEY=sk-ant-...
ALT_ELEVENLABS_API_KEY=...
ALT_OLLAMA_BASE_URL=http://localhost:11434
ALT_AUDIO_STORAGE_PATH=storage/audio
ALT_RESULTS_STORAGE_PATH=storage/results
```

### Auto-migration

On backend startup, `Base.metadata.create_all` creates all tables automatically. No manual Alembic step needed for initial setup.

---

## 14. Project File Listing

```
audio_llm_test/
├── pyproject.toml                          # Python deps + config
├── Dockerfile                              # Backend/worker image
├── docker-compose.yml                      # Full stack orchestration
├── .env.example                            # Environment template
├── alembic.ini                             # Alembic config
├── alembic/
│   ├── env.py                              # Async migration env
│   ├── script.py.mako                      # Migration template
│   └── versions/001_initial.py             # Initial schema migration
│
├── backend/app/
│   ├── main.py                             # FastAPI app + lifespan
│   ├── config.py                           # Pydantic Settings
│   │
│   ├── audio/                              # Signal processing
│   │   ├── types.py                        # AudioBuffer, FilterSpec
│   │   ├── noise.py                        # Pink/white noise generators
│   │   ├── filters.py                      # Biquad FilterChain (SOS)
│   │   ├── echo.py                         # EchoPath simulation
│   │   ├── mixer.py                        # SNR mixing
│   │   └── io.py                           # WAV I/O, PCM16, base64
│   │
│   ├── speech/                             # TTS + corpus
│   │   ├── tts_base.py                     # TTSProvider protocol
│   │   ├── tts_openai.py                   # OpenAI TTS
│   │   ├── tts_google.py                   # Google Cloud TTS
│   │   ├── tts_elevenlabs.py               # ElevenLabs TTS
│   │   ├── corpus.py                       # Harvard sentences + commands
│   │   └── catalog.py                      # Voice diversity selector
│   │
│   ├── llm/                                # LLM backends
│   │   ├── base.py                         # LLMBackend + ASRBackend protocols
│   │   ├── openai_audio.py                 # GPT-4o audio
│   │   ├── gemini.py                       # Google Gemini
│   │   ├── anthropic_backend.py            # Claude
│   │   ├── ollama.py                       # Local Ollama
│   │   └── whisper.py                      # Whisper local + API
│   │
│   ├── pipeline/                           # Test execution pipelines
│   │   ├── base.py                         # PipelineInput/Result types
│   │   ├── direct_audio.py                 # Pipeline A
│   │   ├── asr_text.py                     # Pipeline B
│   │   └── echo_feedback.py                # Multi-turn echo
│   │
│   ├── evaluation/                         # Response evaluation
│   │   ├── base.py                         # Evaluator protocol
│   │   ├── command_match.py                # Exact/fuzzy/keyword matching
│   │   ├── llm_judge.py                    # LLM-as-judge (1-5 rubric)
│   │   └── metrics.py                      # WER, CER
│   │
│   ├── execution/                          # Parallel execution
│   │   ├── rate_limiter.py                 # Token bucket + semaphore
│   │   ├── scheduler.py                    # Async test scheduler
│   │   └── worker.py                       # arq background tasks
│   │
│   ├── stats/                              # Statistical analysis
│   │   ├── analysis.py                     # ANOVA, CI, pairwise tests
│   │   └── aggregation.py                  # Pivots, exports, DataFrames
│   │
│   ├── models/                             # SQLAlchemy ORM
│   │   ├── base.py                         # DeclarativeBase + session
│   │   ├── speech.py                       # Voice, CorpusEntry, SpeechSample
│   │   ├── test.py                         # TestSuite, SweepConfig, TestCase
│   │   └── run.py                          # TestRun, TestResult
│   │
│   └── api/                                # REST endpoints
│       ├── speech.py                       # Corpus + TTS management
│       ├── tests.py                        # Suite CRUD + sweep expansion
│       ├── runs.py                         # Run launch/monitor/cancel
│       ├── results.py                      # Query + stats + export
│       └── ws.py                           # WebSocket progress
│
├── frontend/
│   ├── package.json                        # React + Tailwind + Recharts
│   ├── Dockerfile                          # Node 20 dev server
│   ├── vite.config.ts                      # Proxy + Tailwind plugin
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx                        # App bootstrap
│       ├── App.tsx                         # Layout + routing
│       ├── App.css                         # Tailwind import
│       ├── api/client.ts                   # Typed API client
│       ├── pages/
│       │   ├── Dashboard.tsx
│       │   ├── SpeechCorpus.tsx
│       │   ├── TestSuites.tsx
│       │   ├── RunMonitor.tsx
│       │   └── Results.tsx
│       └── components/
│           ├── AudioPlayer.tsx
│           └── StatsCard.tsx
│
├── tests/
│   └── unit/
│       ├── test_types.py                   # AudioBuffer tests
│       ├── test_filters.py                 # Biquad/SOS filter tests
│       ├── test_noise.py                   # Noise generation tests
│       ├── test_mixer.py                   # SNR accuracy tests
│       ├── test_echo.py                    # Echo path tests
│       └── test_metrics.py                 # WER/CER tests
│
└── scripts/
    └── demo_audio.py                       # Generate sample degraded audio
```

---

## 15. Key Dependencies

### Backend (Python 3.11+)
```
numpy>=1.24          scipy>=1.11          soundfile>=0.12
fastapi>=0.110       uvicorn>=0.29        websockets>=12.0
sqlalchemy[asyncio]>=2.0  asyncpg>=0.29  alembic>=1.13
arq>=0.26            redis>=5.0
pydantic>=2.0        pydantic-settings>=2.0  pyyaml>=6.0
openai>=1.30         google-generativeai>=0.5  anthropic>=0.25  httpx>=0.27
pandas>=2.0          matplotlib>=3.8      seaborn>=0.13
Levenshtein>=0.25    python-multipart>=0.0.9
```

### Frontend (Node 20+)
```
react@18  react-dom@18  react-router-dom
@tanstack/react-query  recharts  tailwindcss  @tailwindcss/vite
typescript  vite  @vitejs/plugin-react
```

---

## 16. Deployment

### Quick Start
```bash
# 1. Clone and configure
cp .env.example .env   # Edit with your API keys

# 2. Launch
docker compose up -d --build

# 3. Access
# Dashboard: http://<host>:5173
# API docs:  http://<host>:8000/docs
# Health:    http://<host>:8000/api/health
```

### First Run Workflow
1. Open dashboard → Speech Corpus → click "Seed Corpus" (creates 350 entries)
2. Add voices (requires API keys configured)
3. Generate speech samples (corpus × voices)
4. Create test suite with sweep parameters
5. Launch run
6. Monitor progress → view results

---

## 17. Testing

```bash
# Unit tests (68 tests, audio core)
source .venv/bin/activate
PYTHONPATH=. pytest tests/unit/ -v

# Audio demo (generates WAV files)
PYTHONPATH=. python scripts/demo_audio.py [optional_input.wav]
# Output: storage/demo/*.wav
```

### What the Tests Verify
- Filter frequency response accuracy (±0.5 dB at cutoff, correct rolloff slope)
- SNR mixing accuracy (±0.1 dB)
- Echo delay precision (±1 sample)
- Pink noise spectral slope (~3 dB/octave)
- Peaking EQ boost/cut accuracy (±1 dB)
- WER/CER edit distance correctness
- Resampling, normalization, stereo→mono conversion
