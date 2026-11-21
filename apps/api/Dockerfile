# Build context: repository root (see docker-compose.yml). Two stages:
#   1. build the public chat widget (plain TypeScript -> dist/*.js, *.css)
#   2. Python API image that also serves those widget assets (ADR-027)
FROM node:24-alpine AS widget
WORKDIR /widget
COPY apps/widget/package.json apps/widget/package-lock.json ./
RUN npm ci
COPY apps/widget/tsconfig.json ./
COPY apps/widget/src ./src
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    WIDGET_DIST_DIR=/app/widget
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
RUN pip install --no-cache-dir .
COPY --from=widget /widget/dist/loader.js /widget/dist/frame.js /widget/dist/frame.css /widget/dist/frame.html ./widget/
USER app
EXPOSE 8073
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8073"]
