# Use Python 3.12 on Linux (solves the macOS nautilus-trader issue)
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install uv and dependencies
RUN pip install uv
RUN uv sync

# Run the agent
CMD ["uv", "run", "python", "main.py"]