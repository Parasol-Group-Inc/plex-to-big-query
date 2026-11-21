# Picking & staging app (draft, 2026-11-20). Not deployed yet: docs/PICKING_STAGING_APP.md "Deploying".
# Build from the repo root:  docker build -f deploy/picking_app/Dockerfile -t picking-app .
# One worker, one thread: a single Plex web session, moves one at a time.
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble
WORKDIR /app
COPY deploy/picking_app/requirements.txt deploy/picking_app/requirements.txt
RUN pip install --no-cache-dir -r deploy/picking_app/requirements.txt
COPY scripts/plex_web_export.py scripts/load_plex_csv_dump.py scripts/
COPY deploy/picking_app deploy/picking_app
ENV PLEX_ENV=test PICKING_LOG=/tmp/picking_moves.jsonl PICKING_BQ_LOG=1 HOST=0.0.0.0
CMD exec gunicorn --chdir deploy/picking_app -w 1 --threads 1 -b 0.0.0.0:${PORT:-8080} --timeout 300 app:app
