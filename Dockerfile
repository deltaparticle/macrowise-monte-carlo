# Macrowise Monte Carlo Simulator — production container
# Deploy anywhere Docker runs (Render, Fly, ECS, self-hosted).

FROM python:3.11-slim

# System packages needed by numpy / pandas / scipy wheels on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      gcc \
      g++ \
      gfortran \
      libatlas-base-dev \
      curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer 1: dependencies (cached across code changes).
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Layer 2: application source.
COPY api ./api
COPY macrowise ./macrowise
COPY data ./data

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

# Two workers is a sensible default for CPU-bound simulation work on a small
# container. Tune via docker-compose or platform config.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 2 --timeout-keep-alive 300"]
