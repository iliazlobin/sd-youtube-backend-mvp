# YouTube Top-K MVP — Build Spec

## 1. Goal & scope

Build a minimal Top-K leaderboard API that ingests view events and returns the most-watched videos for hour and day tumbling windows. This is the MVP of the System Design: YouTube Top-K Leaderboard — a single FastAPI backend with PostgreSQL, no streaming infrastructure.

**In scope**
- View event ingestion (single + batch)
- Video CRUD
- Tumbling-window aggregation (hour, day) via PostgreSQL
- Top-K query with metadata

**Out of scope**
- Sliding/trending windows
- Region and category filtering
- Kafka, Flink, Redis, Space-Saving sketch
- Bot filtering, auth, rate limiting

## 2. Functional requirements

- **FR1 — Return top-K by time window.** `GET /v1/top-k?window=hour|day&k=50` → returns `{results: [{video_id, count, rank}], metadata: {window, refreshed_at, k}}` (200); invalid window → 422.
- **FR2 — View event ingestion.** `POST /v1/events/view` with `{video_id, viewer_id, event_time}` → 202 Accepted; missing fields → 422. `POST /v1/events/view/batch` with up to 500 events → 202.
- **FR3 — Video management.** `POST /v1/videos` with `{title, category?, region?}` → 201 + video; `GET /v1/videos/{video_id}` → 200 or 404.
- **FR4 — Metadata on top-K.** Every `GET /v1/top-k` response includes `metadata: {window, refreshed_at, k}` with the aggregation timestamp.

## 3. Stack & deployment

- Runtime: Python 3.12 + FastAPI + uvicorn
- Datastore: PostgreSQL 16 + Alembic migrations
- Tests: pytest (unit + acceptance via verify/)
- Deploy: Docker Compose (app + postgres)
- Port: 8000 (app), 5432 (postgres)

Design → [System Design: YouTube (v2026.06.30.2)](https://app.notion.com/p/iliazlobin/390d865005a8816a9ba5ec00047880f6)

## 4. Data model

```sql
Video {
  video_id:      uuid PK
  title:         text
  category:      text       ← nullable
  region:        text       ← nullable
  created_at:    timestamp  ← default now()
}

ViewEvent {
  event_id:      uuid PK    ← idempotency key
  video_id:      uuid FK    ← references Video
  viewer_id:     text
  event_time:    timestamp
  created_at:    timestamp  ← default now()
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

## 5. API

- `POST /v1/videos` — register a new video
- `GET /v1/videos/{video_id}` — get video details
- `POST /v1/events/view` — ingest a single view event (fire-and-forget, 202 Accepted)
- `POST /v1/events/view/batch` — ingest up to 500 batched view events
- `GET /v1/top-k?window=hour|day&k=50` — return top-K videos for a tumbling window
- `GET /healthz` — health check

## 6. Test scenarios

- Top-K returns correctly ranked results after ingesting view events
- Top-K with invalid window parameter returns 422
- Batch ingestion handles edge counts (0 events, 500 events, 501 → rejected)
- Video not found returns 404
- Video creation with duplicate fields works (UUIDs are unique)
- Idempotency: re-POST the same event_id is a no-op (ON CONFLICT DO NOTHING)
- Aggregation runs on window boundaries (manually triggered for MVP)
- Empty result set (no views in window) returns empty results, not error

## 7. Module layout

```
src/
  youtube_topk/
    __init__.py
    main.py              # FastAPI app + lifespan
    config.py            # pydantic-settings
    db.py                # async SQLAlchemy engine + session
    routers/
      __init__.py
      videos.py          # /v1/videos
      events.py          # /v1/events
      topk.py            # /v1/top-k
      health.py          # /healthz
    models/
      __init__.py
      video.py           # Video ORM model
      view_event.py      # ViewEvent ORM model
      window_aggregate.py # WindowAggregate ORM model
    schemas/
      __init__.py
      video.py           # Video Pydantic schemas
      event.py           # ViewEvent Pydantic schemas
      topk.py            # TopK response schemas
    services/
      __init__.py
      aggregation.py     # window aggregation logic
  alembic/
    ...
  tests/
    unit/
    functional/
  verify/
    acceptance/
      conftest.py
      test_topk.py
      test_events.py
      test_videos.py
```

## 8. Run

```bash
# Start
docker compose up -d

# Health check
curl http://localhost:8000/healthz

# Run tests
pytest tests/unit/ -v
pytest tests/functional/ -v

# Acceptance
source verify/manifest.env && pytest verify/acceptance/ -v
```
