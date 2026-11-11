FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
COPY packages /app/packages
COPY apps/api /app/apps/api

RUN pip install --no-cache-dir \
    fastapi uvicorn httpx asyncpg nats-py pydantic \
    && pip install --no-cache-dir -e /app/packages/domain -e /app/packages/contracts -e /app/apps/api

EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "finchly_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
