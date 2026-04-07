# Audio LLM Test Platform

Test platform for evaluating how well LLMs understand speech under real-world audio conditions — noise, echo, babble, and varying signal quality. Built for automotive cabin voice assistant testing.

## What It Does

Generates speech audio, degrades it with configurable noise/echo/gain parameters, runs it through LLM pipelines (direct audio or ASR+text), and evaluates whether the LLM understood the command correctly. Results are visualized in a dashboard with statistical analysis.

**Two pipeline types:**
- `direct_audio` — Send audio directly to a multimodal LLM
- `asr_text` — Speech-to-text first (Whisper), then send transcript to LLM

**Sweep parameters:** SNR (dB), noise type (white/pink/babble), echo delay, echo gain, LLM backend, pipeline type.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/audio-llm-test.git
cd audio-llm-test

# Run setup (installs Python, Node, PostgreSQL, Redis, Ollama, Whisper)
chmod +x setup.sh
./setup.sh

# Start all services
./start.sh

# Open the UI
open http://localhost:5173
```

The setup script handles everything automatically — Python venv, system dependencies, database creation, Ollama + Mistral model download, Whisper model caching.

## Runs 100% Free/Local

No API keys required. The default stack uses:

| Component | Free/Local Option |
|-----------|------------------|
| LLM | [Ollama](https://ollama.ai) + Mistral 7B |
| Speech-to-Text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (local) |
| Text-to-Speech | [Edge TTS](https://github.com/rany2/edge-tts) (Microsoft, free) |
| Database | PostgreSQL |
| Task Queue | Redis |

Paid cloud services (OpenAI, Anthropic, Google, ElevenLabs, Deepgram) are supported but optional. The UI flags them with `[$]` and disables them if no API key is configured.

## Requirements

- **macOS** or **Linux** (x86_64 or ARM64)
- ~6GB disk space (Ollama Mistral model + Whisper + dependencies)
- 8GB+ RAM recommended

The `setup.sh` script installs all other dependencies automatically:
- Python 3.11+
- Node.js 18+
- PostgreSQL 16
- Redis 7
- Ollama

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend   │────▶│  Backend API │────▶│  PostgreSQL   │
│  React/Vite  │     │   FastAPI    │     │              │
│  :5173       │     │   :8000      │     │  :5432       │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                     ┌──────▼───────┐     ┌──────────────┐
                     │  arq Worker  │────▶│    Redis      │
                     │  (test exec) │     │   :6379      │
                     └──────┬───────┘     └──────────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │  Ollama  │  │ Whisper  │  │ Edge TTS │
        │ (LLM)   │  │  (STT)   │  │  (TTS)   │
        └──────────┘  └──────────┘  └──────────┘
```

## Manual Setup

If you prefer not to use `setup.sh`:

```bash
# 1. Create Python venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[whisper-local]"
pip install edge-tts faster-whisper

# 2. Install frontend
cd frontend && npm install && cd ..

# 3. Start PostgreSQL + Redis (or use Docker)
docker compose up db redis -d

# 4. Copy env config
cp .env.example .env

# 5. Install Ollama and pull a model
brew install ollama  # or curl -fsSL https://ollama.ai/install.sh | sh
ollama pull mistral

# 6. Start services
uvicorn backend.app.main:app --reload --port 8000 &
arq backend.app.execution.worker.WorkerSettings &
cd frontend && npm run dev
```

## Docker

```bash
cp .env.example .env
docker compose up
```

This starts PostgreSQL, Redis, backend, worker, and frontend. You still need Ollama running on the host if using local LLM mode.

## Project Structure

```
backend/
  app/
    api/          # FastAPI route handlers
    models/       # SQLAlchemy models (PostgreSQL)
    audio/        # Audio processing (noise, echo, filters)
    llm/          # LLM backends (Ollama, OpenAI, Anthropic, Gemini)
    speech/       # TTS providers (Edge, ElevenLabs, Google, etc.)
    pipeline/     # Test pipelines (direct_audio, asr_text)
    evaluation/   # Result evaluators (command_match, llm_judge)
    execution/    # arq worker + scheduler
    stats/        # Statistical analysis (ANOVA, confidence intervals)
frontend/
  src/
    pages/        # Dashboard, TestSuites, Results, etc.
    api/          # TypeScript API client
    components/   # Shared UI components
```

## Configuration

All settings use the `ALT_` prefix and can be set via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `ALT_DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/audio_llm_test` | PostgreSQL connection |
| `ALT_REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `ALT_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API URL |
| `ALT_OPENAI_API_KEY` | (empty) | OpenAI API key (optional) |
| `ALT_ANTHROPIC_API_KEY` | (empty) | Anthropic API key (optional) |
| `ALT_GOOGLE_API_KEY` | (empty) | Google API key (optional) |
| `ALT_MAX_CONCURRENT_WORKERS` | `4` | Parallel test execution |

## License

MIT
