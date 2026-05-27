# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system titan && useradd --system --gid titan --create-home --home-dir /home/titan titan

COPY requirements.txt /tmp/titan-core-requirements.txt

COPY --from=titan_shared pyproject.toml /tmp/titan-shared/pyproject.toml
COPY --from=titan_shared README.md /tmp/titan-shared/README.md
COPY --from=titan_shared titan_shared /tmp/titan-shared/titan_shared

COPY --from=titan_ai pyproject.toml /tmp/titan-ai/pyproject.toml
COPY --from=titan_ai README.md /tmp/titan-ai/README.md
COPY --from=titan_ai titan_ai /tmp/titan-ai/titan_ai

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --no-build-isolation /tmp/titan-shared /tmp/titan-ai && \
    python -m pip install -r /tmp/titan-core-requirements.txt

COPY --chown=titan:titan titan_battlebuddy /app/titan_battlebuddy
COPY --chown=titan:titan titan_core /app/titan_core
COPY --chown=titan:titan titan_ui /app/titan_ui

RUN mkdir -p /app/data && chown -R titan:titan /app

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=3).read()"]

USER titan

CMD ["python", "-m", "uvicorn", "titan_battlebuddy.main:app", "--host", "0.0.0.0", "--port", "8001"]
