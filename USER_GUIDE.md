# Audio LLM Test Platform — User Guide

## Quick Start

The platform is running on Docker at **http://10.10.70.10:5173** (dashboard) with the API at **http://10.10.70.10:8000**.

### Services

| Service   | URL                        | Purpose                          |
|-----------|----------------------------|----------------------------------|
| Dashboard | http://10.10.70.10:5173    | Web UI for all operations        |
| API       | http://10.10.70.10:8000    | REST API + WebSocket             |
| API Docs  | http://10.10.70.10:8000/docs | Interactive Swagger UI          |
| PostgreSQL| 10.10.70.10:5432           | Database (audio_llm_test)        |
| Redis     | 10.10.70.10:6379           | Task queue                       |

---

## Configuration

### API Keys

Edit the `.env` file on the Docker host (`~/audio-llm-test/.env`) with your API keys:

```bash
ssh ryan@10.10.70.10
nano ~/audio-llm-test/.env
```

Required keys (add whichever services you want to test):

```
ALT_OPENAI_API_KEY=sk-...          # For GPT-4o audio + Whisper + TTS
ALT_GOOGLE_API_KEY=...             # For Gemini
ALT_ANTHROPIC_API_KEY=sk-ant-...   # For Claude
ALT_ELEVENLABS_API_KEY=...         # For ElevenLabs TTS voices
```

After editing, restart the backend:
```bash
cd ~/audio-llm-test && docker compose restart backend worker
```

### Local LLMs (Ollama)

If you have Ollama running on a machine accessible to the Docker host, set:
```
ALT_OLLAMA_BASE_URL=http://<ollama-host>:11434
```

---

## Workflow

### Step 1: Build Your Speech Corpus

The system needs audio samples of human speech to test against. You build these by:

1. **Go to Speech Corpus page** in the dashboard
2. **Seed the corpus** with built-in Harvard sentences and car commands
3. **Browse voices** — filter by provider, gender, accent, language
4. **Generate speech** — select corpus entries and voices, then trigger batch TTS synthesis

The system generates all combinations (entries x voices) as WAV files. For example:
- 100 Harvard sentences x 10 diverse voices = 1,000 speech samples
- 50 car commands x 10 voices = 500 speech samples

**Voice diversity**: Use Google Cloud TTS for the widest selection of accents and languages. ElevenLabs for the most natural-sounding voices. OpenAI TTS for baseline.

**Tip**: Start small (a few sentences, 2-3 voices) to verify the pipeline works, then scale up.

### Step 2: Configure a Test Suite

A test suite defines the parameter sweep — the cartesian product of all conditions you want to test.

1. **Go to Test Suites page**
2. **Create New Suite** with:

   **SNR levels** (signal-to-noise ratio in dB):
   - Typical sweep: `[-10, -5, 0, 5, 10, 20]`
   - 20 dB = quiet background noise (easy)
   - 0 dB = noise equal to speech (moderate)
   - -10 dB = noise louder than speech (very hard)

   **Noise types**:
   - `pink_lpf` — Pink noise with 100 Hz low-pass filter (simulates road/engine rumble)
   - `white` — White noise (uniform frequency, harsher)
   - `file` — Custom noise recordings (you can upload WAV files)

   **Echo parameters**:
   - Delay: `[0, 50, 100, 200, 500]` ms — speaker-to-mic propagation time
   - Gain: `[-60, -40, -20, -10, 0]` dB — echo attenuation (0 dB = full echo, -60 dB = barely audible)
   - EQ: Optional filter chain simulating the car cabin's frequency response

   **Pipelines**:
   - `direct_audio` — Send degraded audio directly to a multimodal LLM (GPT-4o, Gemini)
   - `asr_text` — Transcribe with Whisper first, then send text to any LLM

   **LLM backends**: Select which models to test (GPT-4o, Gemini, Claude, Ollama, etc.)

3. **Preview** the total case count before creating — the sweep generates the cartesian product:

   ```
   100 speech files x 6 SNRs x 5 delays x 5 gains x 2 noise x 2 pipelines x 3 backends
   = 180,000 test cases
   ```

   **Tip**: Start with a smaller sweep to validate, then expand.

### Step 3: Run Tests

1. **Go to the Test Suite** you created
2. Click **Launch Run**
3. **Monitor progress** on the Run Monitor page:
   - Live progress bar
   - Per-backend throughput (requests/sec)
   - Scrolling log of individual results
   - Cancel button if needed

The system runs tests in parallel with per-backend rate limiting to avoid API throttling. Results are checkpointed — if a run is interrupted, you can resume it.

### Step 4: Analyze Results

After a run completes (or while it's running), go to the **Results** page:

**Summary stats**:
- Overall pass rate and mean score
- Total completed / failed / errored tests
- Mean and median latency

**Charts tab**:
- **Accuracy vs SNR curve** — One line per LLM backend with 95% confidence intervals. This is the key chart — it shows where each backend's comprehension breaks down as noise increases.
- **Heatmaps** — Accuracy as a function of two parameters (e.g., SNR x echo delay). Reveals interaction effects.

**Table tab**:
- Filter and sort individual results
- Click any result to see the LLM response, evaluation details, and play the audio

**Export tab**:
- Download raw results as CSV, JSON, or Parquet for further analysis in Python/R/Excel

---

## Audio Processing Parameters

### Noise

| Parameter | Range | Description |
|-----------|-------|-------------|
| SNR (dB) | -20 to +40 | Signal-to-noise ratio. Lower = more noise. |
| Type | pink_lpf, white, file | Pink+LPF = car rumble, White = harsh, File = custom |
| LPF cutoff | Hz | Low-pass filter on pink noise (default 100 Hz) |
| LPF order | 1-4 | Filter steepness (default 2 = -12 dB/octave) |

### Echo

| Parameter | Range | Description |
|-----------|-------|-------------|
| Delay | 0-500 ms | Speaker-to-mic propagation delay |
| Gain | -100 to 0 dB | Echo attenuation. 0 = full echo, -100 = silent |
| EQ chain | FilterSpec list | Cabin frequency response simulation |

### Filter Types (for Echo EQ)

| Type | Parameters | Use case |
|------|-----------|----------|
| `lpf` | frequency, Q | Low-pass filter (air absorption, speaker rolloff) |
| `hpf` | frequency, Q | High-pass filter (cabinet coupling) |
| `peaking` | frequency, Q, gain_db | Parametric EQ (cabin resonances) |
| `lowshelf` | frequency, Q, gain_db | Low shelf (bass boost/cut) |
| `highshelf` | frequency, Q, gain_db | High shelf (treble boost/cut) |

**Typical car cabin EQ chain**:
```
HPF at 80 Hz (Q=0.707)     — speaker low-frequency rolloff
LPF at 6000 Hz (Q=0.707)   — air absorption
Peaking at 2500 Hz (Q=2.0, +4 dB) — cabin resonance
```

---

## Evaluation

### Command Matching
For predefined commands (navigation, media, climate, phone), the system checks if the LLM's response matches the expected action using:
- **Exact match** — normalized text comparison
- **Fuzzy match** — Levenshtein similarity (threshold: 0.8)
- **Keyword match** — key words from expected action found in response

Score: 0.0 to 1.0 (best of all methods). Pass threshold: 0.6.

### LLM-as-Judge
For open-ended responses, a separate LLM judges the response on a 1-5 scale:
1. Completely wrong/dangerous
2. Misunderstood the request
3. Partially correct
4. Correct but suboptimal
5. Perfect response

Multiple judge calls (default 3) with majority vote for reliability.

### Word Error Rate (WER)
For the ASR pipeline, WER measures how accurately Whisper transcribed the degraded audio compared to the original text. Lower is better (0.0 = perfect).

---

## API Reference

Interactive API docs: **http://10.10.70.10:8000/docs**

Key endpoints:

```
GET  /api/health                    — Health check
GET  /api/speech/voices             — List TTS voices
GET  /api/speech/corpus             — List corpus entries
POST /api/speech/synthesize         — Batch TTS generation
POST /api/tests/suites              — Create test suite
POST /api/tests/suites/preview      — Preview sweep count
POST /api/runs                      — Launch test run
GET  /api/runs/{id}                 — Run status
GET  /api/results?run_id=X          — Query results
GET  /api/results/{run_id}/stats    — Statistical analysis
GET  /api/results/{run_id}/heatmap  — Heatmap data
GET  /api/results/{run_id}/export   — Export CSV/JSON/Parquet
WS   /api/ws/runs/{id}              — Live progress stream
```

---

## CLI / Scripting

### Audio Demo Script
Generate sample degraded audio files to hear the effects:

```bash
cd ~/audio-llm-test
source .venv/bin/activate

# With synthetic tone
PYTHONPATH=. python scripts/demo_audio.py

# With your own speech file
PYTHONPATH=. python scripts/demo_audio.py /path/to/speech.wav
```

Output goes to `storage/demo/` — open the WAV files to hear various SNR/echo levels.

### Running Tests Programmatically

```python
import asyncio
from backend.app.audio.io import load_audio
from backend.app.audio.noise import pink_noise_filtered
from backend.app.audio.mixer import mix_at_snr
from backend.app.audio.echo import EchoConfig, EchoPath
from backend.app.audio.types import FilterSpec

# Load your speech
speech = load_audio("my_speech.wav", target_sample_rate=16000)

# Add noise at 5 dB SNR
noise = pink_noise_filtered(speech.duration_s, lpf_cutoff_hz=100, sample_rate=16000)
noisy = mix_at_snr(speech, noise, snr_db=5.0)

# Add echo with cabin EQ
echo_cfg = EchoConfig(
    delay_ms=100,
    gain_db=-10,
    eq_chain=[
        FilterSpec("hpf", 80.0),
        FilterSpec("lpf", 6000.0),
        FilterSpec("peaking", 2500.0, Q=2.0, gain_db=4.0),
    ],
)
echo_path = EchoPath(echo_cfg, 16000)
degraded = echo_path.apply(noisy, speech)  # speech doubles as echo source here

# Save result
from backend.app.audio.io import save_audio
save_audio(degraded, "degraded_output.wav")
```

---

## Docker Management

```bash
# SSH to Docker host
ssh ryan@10.10.70.10

# View logs
cd ~/audio-llm-test
docker compose logs -f backend    # Backend logs
docker compose logs -f worker     # Worker logs
docker compose logs -f frontend   # Frontend logs

# Restart services
docker compose restart backend worker

# Stop everything
docker compose down

# Rebuild after code changes
docker compose up -d --build

# View database
docker compose exec db psql -U postgres audio_llm_test
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| API 500 error on first use | Click "Seed Corpus" first to populate the database |
| Empty voices list | Add API keys to `.env`, then use TTS provider APIs to register voices |
| Rate limit errors (429) | Reduce `max_concurrent` in rate limiter config or add delay |
| Whisper OOM on large files | Use `whisper-1` API instead of local model, or use a smaller model size |
| No speech samples ready | Run batch synthesis and wait for TTS to complete |
| Test suite creation fails | Need at least one speech sample with status "ready" |
| Frontend can't connect to API | Verify backend is running: `curl http://10.10.70.10:8000/api/health` |
| Database tables missing | Backend creates tables on startup automatically. Restart: `docker compose restart backend` |
