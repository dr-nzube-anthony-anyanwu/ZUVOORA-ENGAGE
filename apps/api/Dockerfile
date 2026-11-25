# ZUVOORA Engage API + worker image (Phase 6, ADR-043). Build context: repository root.
#   1. build the public chat widget (plain TypeScript -> dist/*.js, *.css)
#   2. Python API image that also serves those widget assets (ADR-027)
# The same image runs the worker (`python -m app.worker`). Non-root, fixed UID.
# Base images pinned by digest (checked 2026-11-25: node 24.22.3-alpine, python 3.12.16-slim).
ARG NODE_IMAGE=node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5
ARG PYTHON_IMAGE=python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b

FROM ${NODE_IMAGE} AS widget
WORKDIR /widget
COPY apps/widget/package.json apps/widget/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/widget/tsconfig.json ./
COPY apps/widget/src ./src
RUN npm run build

FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 WIDGET_DIST_DIR=/app/widget
WORKDIR /app
# Debian security fixes released after the pinned base image (image scan, 2026-11-25).
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home app
COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
RUN pip install --no-cache-dir . && rm -rf /root/.cache
COPY --from=widget /widget/dist/loader.js /widget/dist/frame.js /widget/dist/frame.css /widget/dist/frame.html ./widget/
USER 10001:10001
EXPOSE 8073
HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-m", "app.healthcheck", "api"]
# Proxy headers are handled inside the app (FORWARDED_ALLOW_IPS, app/middleware.py), so uvicorn's
# own handling is switched off; no Server header; requests finish before shutdown.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8073", \
     "--no-proxy-headers", "--no-server-header", "--timeout-graceful-shutdown", "25"]
