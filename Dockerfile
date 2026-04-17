FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (git needed for snapshot push)
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Install uv and dependencies
RUN pip install uv
RUN uv sync

# Run the agent
CMD ["uv", "run", "python", "main.py"]