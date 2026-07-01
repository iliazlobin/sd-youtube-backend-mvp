# Deploy — YouTube Top-K Leaderboard MVP

## Prerequisites

- Docker and Docker Compose installed
- Port 8010 (or `$APP_PORT`) available

## Quick start

```bash
# Clone and enter the project
git clone https://github.com/iliazlobin/sd-youtube-backend-mvp.git
cd sd-youtube-backend-mvp

# Start the stack
docker compose up -d --build

# Run database migrations (first time only)
docker compose run --rm app alembic upgrade head

# Smoke test
curl http://localhost:${APP_PORT:-8010}/healthz
```

## Teardown

```bash
docker compose down -v
```

## Custom port

```bash
APP_PORT=9000 docker compose up -d --build
```
