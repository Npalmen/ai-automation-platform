FROM node:22-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG BUILD_COMMIT_SHA=unknown
ARG BUILD_TIME=unknown
ARG RELEASE_ID=unknown

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY storage ./storage
COPY --from=frontend-build /frontend/dist ./frontend/dist

RUN python scripts/write_build_metadata.py \
    --commit-sha "$BUILD_COMMIT_SHA" \
    --build-time "$BUILD_TIME" \
    --release-id "$RELEASE_ID" \
    --output /app/build-metadata.json

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "172.16.0.0/12,10.0.0.0/8,127.0.0.1"]
