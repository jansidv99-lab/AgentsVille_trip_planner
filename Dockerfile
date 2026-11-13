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
# Fix: quality/ (graders, schema, pricing, labels – imported by llm.py since Layer B B0) and prompts/
# (versioned prompt templates since B4) were missing, so the app failed to import in production.
COPY quality/ quality/
COPY prompts/ prompts/

# Fail the BUILD if the app can't import or can't load its prompt templates – the health endpoint alone
# can't catch this (Streamlit only executes app.py when a browser session connects).
RUN OPENAI_API_KEY=build-check python -c "import app; from agents.prompts import available_prompt_versions, load_prompt_template; [load_prompt_template(v) for v in available_prompt_versions()]; print('import check OK:', available_prompt_versions())"

# Run as an unprivileged user instead of root.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8080

# Cloud Run sets $PORT; Streamlit must listen on it on all interfaces.
# "exec" makes Streamlit PID 1 so it receives Cloud Run's shutdown signal (SIGTERM).
CMD ["sh", "-c", "exec streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
