# Picking & staging app (2026-11-20). Cloud Run service picking-app: docs/PICKING_STAGING_APP.md "Deploying".
# Build from the repo root:  docker build -f deploy/picking_app/Dockerfile -t picking-app .
# One worker (one Plex web session, one cache), 40 threads (the pick list loads ingredients in parallel; Cloud Run --concurrency 40 matches; Plex API calls are capped at 16 in plex_api); moves are serialized in the app.
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble
WORKDIR /app
COPY deploy/picking_app/requirements.txt deploy/picking_app/requirements.txt
RUN pip install --no-cache-dir -r deploy/picking_app/requirements.txt
COPY scripts/plex_web_export.py scripts/load_plex_csv_dump.py scripts/
COPY deploy/picking_app deploy/picking_app
ENV PLEX_ENV=test PICKING_LOG=/tmp/picking_moves.jsonl PICKING_BQ_LOG=1 HOST=0.0.0.0
# Not root (audit 11-23 #27): the Playwright image's own user; the app writes only /tmp and GCS.
USER pwuser
CMD exec gunicorn --chdir deploy/picking_app -w 1 --threads 40 -b 0.0.0.0:${PORT:-8080} --timeout 300 app:app
