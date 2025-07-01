# Multi-stage build for production
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/opt/venv/bin:$PATH"

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Set working directory
WORKDIR /app

# Create non-root user
RUN useradd --create-home --shell /bin/bash --uid 1000 app

# Copy application files
COPY --chown=app:app kyc_mcp_server.py .
COPY --chown=app:app kyc_http_server.py .
COPY --chown=app:app kyc_client.py .
COPY --chown=app:app config.py .
COPY --chown=app:app config_db.py .
COPY --chown=app:app models.py .
COPY --chown=app:app database.py .
COPY --chown=app:app database_models.py .
COPY --chown=app:app universal_database.py .
COPY --chown=app:app mysql_config.py .
COPY --chown=app:app enhanced_langchain_agent.py .

# Copy Google Sheets integration files
COPY --chown=app:app google_config.py .
COPY --chown=app:app google_sheets_database.py .
COPY --chown=app:app universal_google_sheets.py .
COPY --chown=app:app google_drive_storage.py .

# Copy environment files
COPY --chown=app:app .env* ./

# Copy Google credentials (will be mounted at runtime)
# Note: The actual credentials.json will be mounted via docker-compose volumes

# Create data directory
RUN mkdir -p /app/data && chown app:app /app/data

# Switch to non-root user
USER app

# Expose ports
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Default command (can be overridden)
CMD ["python", "kyc_http_server.py"]