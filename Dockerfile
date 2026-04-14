# Use Python 3.12 on Linux (solves the macOS nautilus-trader issue)
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install dependencies
RUN pip install anthropic python-dotenv boto3 nautilus-trader requests "fsspec[http]"

# Run the loop
CMD ["python", "cloud_loop_runner.py"]