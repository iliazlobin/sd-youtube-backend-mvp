# YouTube Top-K Leaderboard MVP

A FastAPI + PostgreSQL backend that ingests view events and returns the most-watched videos
for hour and day tumbling windows.

## Stack

- Python 3.12 + FastAPI + uvicorn
- PostgreSQL 16 + SQLAlchemy (async) + Alembic
- Docker Compose

## Quickstart

```bash
git clone https://github.com/iliazlobin/sd-youtube-backend-mvp.git
cd sd-youtube-backend-mvp
docker compose up -d --build
docker compose run --rm app alembic upgrade head
curl http://localhost:8010/healthz
```

## API

| Method | Path                  | Status | Description                     |
|--------|-----------------------|--------|---------------------------------|
| POST   | `/v1/videos`          | 201    | Create a new video              |
| GET    | `/v1/videos/{id}`     | 200    | Get video details               |
| POST   | `/v1/events/view`     | 202    | Ingest a single view event      |
| POST   | `/v1/events/view/batch` | 202  | Ingest up to 500 view events    |
| GET    | `/v1/top-k`           | 200    | Top-K videos by window          |
| GET    | `/healthz`            | 200    | Health check                    |

### Example requests

```bash
# Create a video
curl -X POST http://localhost:8010/v1/videos \
  -H "Content-Type: application/json" \
  -d '{"title":"My Video","category":"Music"}'

# Ingest a view event
curl -X POST http://localhost:8010/v1/events/view \
  -H "Content-Type: application/json" \
  -d '{"event_id":"11111111-1111-1111-1111-111111111111","video_id":"<video-uuid>","viewer_id":"user1","event_time":"2026-06-30T12:00:00Z"}'

# Top-K leaderboard
curl "http://localhost:8010/v1/top-k?window=hour&k=10"
```

### Top-K query parameters

| Param    | Type   | Default | Range | Description        |
|----------|--------|---------|-------|--------------------|
| `window` | string | —       | hour, day | Tumbling window |
| `k`      | int    | 50      | 1–100 | Number of results  |

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/
```

## Architecture

```
Client → FastAPI (port 8000) → PostgreSQL 16
                                 ├── videos
                                 ├── view_events (idempotent ON CONFLICT)
                                 └── window_aggregates (UPSERT on window)
```

Windows are computed on read — `GET /v1/top-k` returns the most recently completed
hour or day window. Aggregation must be triggered manually for MVP (call
`aggregate_window` from a script or scheduled endpoint).

## Project layout

```
src/youtube_topk/
├── main.py          # App factory + lifespan
├── config.py        # pydantic-settings
├── db.py            # Async SQLAlchemy engine + session
├── models/          # ORM models (Video, ViewEvent, WindowAggregate)
├── schemas/         # Pydantic request/response DTOs
├── routers/         # HTTP layer (videos, events, topk, health)
└── services/        # Business logic (ingestion, aggregation)
```
