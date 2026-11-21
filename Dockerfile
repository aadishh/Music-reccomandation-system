
# Python 3.11
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY requirements.txt .

# Install Python dependencies
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

RUN python -m pip install --no-cache-dir \
    --only-binary=:all: \
    -r requirements.txt



# Copy application
COPY . .

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV TF_CPP_MIN_LOG_LEVEL=2
ENV DEEPFACE_HOME=/tmp/.deepface
ENV PORT=8080
ENV SQLITE_DB_PATH=/tmp/music_recommender.db

# Create temporary directory
RUN mkdir -p /tmp

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

# Start Flask application
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8080} --timeout 300 --workers 1 --max-requests 100 app:app"]
