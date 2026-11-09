# =============================================================================
# Stage 1: Build isolated Python virtual environment for rembg + FastAPI + OpenCV
# =============================================================================
FROM python:3.12.9-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY kivy/web/tools/requirements-background.txt /tmp/requirements-background.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /tmp/requirements-background.txt

# =============================================================================
# Stage 2: Hardened non-root production runtime
# =============================================================================
FROM python:3.12.9-slim-bookworm AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -m -d /home/appuser -s /usr/sbin/nologin appuser \
    && mkdir -p /home/appuser/.u2net /app \
    && chown -R appuser:appgroup /home/appuser /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appgroup kivy/web/tools/background_server.py /app/background_server.py

WORKDIR /app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    U2NET_HOME="/home/appuser/.u2net" \
    NUMBA_CACHE_DIR="/home/appuser/.u2net/numba_cache" \
    OMP_NUM_THREADS="2" \
    HOST="0.0.0.0" \
    PORT="7000"

USER 10001:10001

EXPOSE 7000

HEALTHCHECK --interval=10s --timeout=5s --start-period=120s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7000/health', timeout=3)" || exit 1

CMD ["uvicorn", "background_server:app", "--host", "0.0.0.0", "--port", "7000", "--workers", "1", "--no-access-log"]
