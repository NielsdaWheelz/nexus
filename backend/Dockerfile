FROM python:3.13-slim

# Install Node.js + npm for HTML extraction helper
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy all files (needed for uv to find app package)
COPY . .

# Install Python dependencies using uv
RUN pip install uv && uv sync --all-extras

# Install Node.js dependencies (production only)
RUN npm install --production

# Default command: run Celery worker
CMD ["celery", "-A", "app.celery_app", "worker", "-Q", "documents,embeddings", "-l", "info"]
