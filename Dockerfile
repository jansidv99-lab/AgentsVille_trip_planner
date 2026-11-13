# Phase 6 – Step 1: container image for the Streamlit app, deployed to Cloud Run.
# Secrets are NOT baked in: OPENAI_API_KEY comes from Secret Manager at runtime,
# and .dockerignore keeps .env out of the build context entirely.

FROM python:3.11-slim

# No .pyc files, unbuffered logs (so Cloud Logging gets lines immediately), smaller pip layer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080

WORKDIR /app

# Install dependencies first: this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy only the application code (tests, plans, and dev files are not needed at runtime).
COPY app.py models.py llm.py project_lib.py ./
COPY agents/ agents/
COPY ui/ ui/

# Run as an unprivileged user instead of root.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8080

# Cloud Run sets $PORT; Streamlit must listen on it on all interfaces.
# "exec" makes Streamlit PID 1 so it receives Cloud Run's shutdown signal (SIGTERM).
CMD ["sh", "-c", "exec streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
