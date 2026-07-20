FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && addgroup --system app \
    && adduser --system --ingroup app app

COPY --chown=app:app app/ ./app/
COPY --chown=app:app scripts/ ./scripts/
RUN mkdir -p /app/data && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)" || exit 1

# One worker is intentional: in-process visualization presence is not shared
# unless the deployment explicitly enables a real Redis-backed multi-worker setup.
CMD ["sh", "-c", "python scripts/migrate_order_sources.py && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --ws-max-size 16384"]
