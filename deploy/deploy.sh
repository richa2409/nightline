#!/usr/bin/env bash
# Simple zero-downtime-ish deploy for a single VM running docker-compose.
# Usage: ./deploy.sh
set -euo pipefail

APP_DIR="/opt/anon-chat-ai"
BRANCH="main"

echo "==> Pulling latest code"
cd "$APP_DIR"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

echo "==> Pulling latest images"
docker compose pull

echo "==> Recreating containers"
docker compose up -d --remove-orphans

echo "==> Pruning old images"
docker image prune -f

echo "==> Waiting for API health check"
for i in $(seq 1 15); do
  if curl -fs http://localhost:8080/api/health > /dev/null; then
    echo "API is healthy."
    exit 0
  fi
  sleep 2
done

echo "API failed health check after deploy!" >&2
exit 1
