# YouTube Top-K Leaderboard MVP

[![CI](https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/ci.yml/badge.svg)](https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/ci.yml)
[![Lint](https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/lint.yml/badge.svg)](https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/lint.yml)
[![Functional](https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/functional.yml/badge.svg)](https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/functional.yml)

A FastAPI + PostgreSQL backend that ingests video view events and returns the
most-watched videos for hour and day tumbling windows. Push-based ingestion,
upsert-on-window aggregation, no streaming infrastructure.

## Quickstart

```bash
git clone https://github.com/iliazlobin/sd-youtube-backend-mvp.git
cd sd-youtube-backend-mvp

# Start the stack
docker compose up -d --build

# Run migrations (first time)
docker compose run --rm app alembic upgrade head

# Verify
curl http://localhost:8010/healthz
# → {"status":"ok"}
```

## API Reference

| Method | Path                      | Status | Description                      |
|--------|---------------------------|--------|----------------------------------|
| POST   | `/v1/videos`              | 201    | Create a new video               |
| GET    | `/v1/videos/{video_id}`   | 200    | Get video by ID                  |
| POST   | `/v1/events/view`         | 202    | Ingest a single view event       |
| POST   | `/v1/events/view/batch`   | 202    | Ingest up to 500 view events     |
| GET    | `/v1/top-k`               | 200    | Top-K leaderboard by window      |
| GET    | `/healthz`                | 200    | Health check                     |

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

# Batch ingest (up to 500 events)
curl -X POST http://localhost:8010/v1/events/view/batch \
  -H "Content-Type: application/json" \
  -d '{"events":[{"event_id":"aaa...","video_id":"<uuid>","viewer_id":"user2","event_time":"2026-06-30T12:01:00Z"}]}'

# Top-K leaderboard (most recent completed hour)
curl "http://localhost:8010/v1/top-k?window=hour&k=10"

# Top-K for the day
curl "http://localhost:8010/v1/top-k?window=day&k=5"
```

### `GET /v1/top-k` query parameters

| Param    | Type   | Required | Default | Range    | Description             |
|----------|--------|----------|---------|----------|-------------------------|
| `window` | string | yes      | —       | hour,day | Tumbling window         |
| `k`      | int    | no       | 50      | 1–100    | Number of results       |

### Response shapes

<details>
<summary><code>POST /v1/videos</code> → 201</summary>

```json
{
  "video_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "title": "My Video",
  "category": "Music",
  "region": null,
  "created_at": "2026-06-30T12:00:00Z"
}
```
</details>

<details>
<summary><code>POST /v1/events/view</code> → 202</summary>

```json
{"status": "accepted", "count": 1}
```
</details>

<details>
<summary><code>GET /v1/top-k?window=hour&k=3</code> → 200</summary>

```json
{
  "results": [
    {"video_id": "uuid-1", "title": "Video A", "view_count": 42, "rank": 1},
    {"video_id": "uuid-2", "title": "Video B", "view_count": 30, "rank": 2},
    {"video_id": "uuid-3", "title": "Video C", "view_count": 15, "rank": 3}
  ],
  "metadata": {"window": "hour", "refreshed_at": "2026-06-30T12:05:00Z", "k": 3}
}
```
</details>

### Error responses

| Status | When                                                |
|--------|-----------------------------------------------------|
| 404    | Video not found                                     |
| 422    | Invalid window ("week"), k out of range, batch >500 |

## Architecture

```
Client → FastAPI (port 8000) → PostgreSQL 16
                                  ├── videos               (video metadata)
                                  ├── view_events          (idempotent ON CONFLICT DO NOTHING)
                                  └── window_aggregates    (UPSERT on video_id + window_start)
```

**Key design decisions:**

- **Idempotent ingestion** — duplicate `event_id`s are silently dropped via
  `ON CONFLICT (event_id) DO NOTHING`. Fire-and-forget semantics (202 Accepted,
  no body parsed on return).

- **Window aggregation** — `INSERT ... ON CONFLICT (video_id, window_start) DO UPDATE`
  with `view_count = EXCLUDED.view_count` (replace semantics). Aggregation is
  triggered manually for MVP (call `aggregate_window` from a script or scheduled
  endpoint); the computed windows cover the most recently completed hour/day.

- **Top-K reads** — `GET /v1/top-k` queries `window_aggregates` directly with
  `ORDER BY view_count DESC LIMIT k`. No in-memory sort, no Redis sorted set.

- **Pure PostgreSQL** — no Kafka, Flink, Redis, or Space-Saving sketch. The MVP
  path proves the data model and aggregation logic before introducing streaming.

## Data Model

```sql
Video {
  video_id:      uuid PK
  title:         text
  category:      text        ← nullable
  region:        text        ← nullable
  created_at:    timestamp   ← default now()
}

ViewEvent {
  event_id:      uuid PK     ← idempotency key
  video_id:      uuid FK     ← references Video
  viewer_id:     text
  event_time:    timestamp
  created_at:    timestamp   ← default now()
}

WindowAggregate {
  id:            serial PK
  video_id:      uuid FK
  window_start:  timestamp
  window_end:    timestamp
  view_count:    integer
  UNIQUE(video_id, window_start)
}
```

## Configuration

| Variable       | Default                                                      | Description            |
|----------------|--------------------------------------------------------------|------------------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/youtube_topk` | Database connection    |
| `APP_PORT`     | `8000`                                                       | App listen port        |

Supports `postgresql+asyncpg://` (production) and `sqlite+aiosqlite://` (local
dev convenience). Place overrides in `.env`.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run unit tests (SQLite, fast)
pytest tests/unit/ -v

# Run tests against PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/youtube_topk \
  pytest tests/functional/ -v

# Acceptance tests (against running app)
API_BASE_URL=http://localhost:8000 pytest verify/acceptance/ -v

# Lint
ruff check src/ tests/
ruff format --check src/ tests/
```

## CI

Three GitHub Actions workflows:

| Workflow     | Triggers                 | What it runs                          |
|-------------|--------------------------|---------------------------------------|
| CI          | push/PR to main + cron   | Unit tests + acceptance against PG    |
| Functional  | push/PR to main + cron   | Functional tests against PG           |
| Lint        | push/PR to main + cron   | Ruff lint (E, F, I, B, UP, N, W)      |

## Project Layout

```
src/youtube_topk/
├── main.py               # FastAPI app factory + lifespan
├── config.py             # pydantic-settings (DATABASE_URL, APP_PORT)
├── db.py                 # Async SQLAlchemy engine + session factory
├── models/
│   ├── video.py          # Video ORM model
│   ├── view_event.py     # ViewEvent ORM model (idempotent ON CONFLICT)
│   └── window_aggregate.py  # WindowAggregate ORM model (UPSERT)
├── schemas/
│   ├── video.py          # CreateVideoRequest, VideoResponse
│   ├── event.py          # ViewEventRequest, BatchViewEventsRequest, AcceptedResponse
│   └── topk.py           # TopKResponse, TopKResult, TopKMetadata
├── routers/
│   ├── videos.py         # POST/GET /v1/videos
│   ├── events.py         # POST /v1/events/view, /view/batch
│   ├── topk.py           # GET /v1/top-k
│   └── health.py         # GET /healthz
└── services/
    ├── aggregation.py    # Window boundary computation + top-K query
    ├── events.py         # Single + batch view event ingestion
    └── videos.py         # Video CRUD
tests/
├── unit/                 # 19 tests (SQLite, no DB required)
├── functional/           # Against live PostgreSQL
└── conftest.py           # Shared fixtures
verify/
└── acceptance/           # Against running app (FR1–FR4)
```

## Limitations

- Aggregation must be triggered manually — no cron/scheduler ships with the MVP.
- Windows are tumbling only (hour, day); no sliding or trending windows.
- No region or category filtering on top-K queries.
- No auth, rate limiting, or bot filtering.
- Batch ingestion capped at 500 events per request.
- Top-K capped at 100 results.
- SQLite tests require PostgreSQL for UUID-native columns (unit tests are
  PostgreSQL-backed via `aiosqlite` with UUID casting).
