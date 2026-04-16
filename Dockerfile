# Dockerfile for autonomous agents with data retrieval

FROM python:3.11-slim

WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install AWS CLI
RUN pip install --no-cache-dir awscli

# Create cache directory
RUN mkdir -p /data-cache

# Copy scripts
COPY scripts/ /scripts/
RUN chmod +x /scripts/*.py

# Set environment
ENV PATH="/scripts:${PATH}" \
    DATA_CACHE_DIR="/data-cache" \
    PYTHONUNBUFFERED=1

# Default command - list datasets
CMD ["python", "/scripts/data_retriever.py", "list-datasets"]
