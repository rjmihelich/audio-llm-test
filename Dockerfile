FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for audio processing and TTS
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    espeak-ng \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy everything first, then install
COPY . .
RUN pip install --no-cache-dir ".[dev]" && \
    pip install --no-cache-dir edge-tts gTTS pyttsx3 faster-whisper || true

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
