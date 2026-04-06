FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for soundfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copy everything first, then install
COPY . .
RUN pip install --no-cache-dir ".[dev]"

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
