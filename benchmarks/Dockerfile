FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    SEMGREP_ENABLE_VERSION_CHECK=0 \
        PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    unzip \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir semgrep

RUN groupadd -r bench && useradd -r -g bench -m bench

WORKDIR /app
ENV PYTHONPATH=/app

USER bench
