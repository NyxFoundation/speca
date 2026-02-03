FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    SEMGREP_ENABLE_VERSION_CHECK=0

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    unzip \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir semgrep

WORKDIR /app
