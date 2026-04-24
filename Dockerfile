# Dockerfile for agentic trading system
# Runs the NautilusTrader backtest engine with AWS S3 data retrieval

FROM python:3.12-slim

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN mkdir -p /data-cache

ENV VIRTUAL_ENV="/workspace/.venv" \
    PATH="/workspace/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/workspace:/workspace/.venv/lib/python3.12/site-packages" \
    DATA_CACHE_DIR="/data-cache"

CMD ["python", "main.py"]