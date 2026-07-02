# Design — YouTube Top-K Leaderboard MVP

## 1. What this system is

A minimal Top-K leaderboard backend in the style of YouTube's "most-watched" surface: a
single FastAPI service backed by PostgreSQL that ingests video view events and answers
"what were the most-watched videos" for tumbling **hour** and **day** windows.

The MVP deliberately implements only the batch/relational path of the full Top-K design:
no Kafka, no Flink, no Redis, no Space-Saving sketch. View events are written straight to
PostgreSQL, aggregated into per-window counts with an idempotent UPSERT, and served with a
plain `ORDER BY view_count DESC LIMIT k` query. This proves the data model, window
semantics, and API contract before any streaming infrastructure is introduced.

**In scope**

- View event ingestion — single (`POST /v1/events/view`) and batch up to 500 events
  (`POST /v1/events/view/batch`), both fire-and-forget with `202 Accepted`
- Video registration and lookup (`POST /v1/videos`, `GET /v1/videos/{video_id}`)
- Tumbling-window aggregation (hour, day) computed in PostgreSQL
- Top-K query with response metadata (`GET /v1/top-k?window=hour|day&k=50`)

**Out of scope (by design)**

- Sliding/trending windows, per-region and per-category leaderboards
- Streaming infrastructure (Kafka, Flink, Redis) and approximate counting sketches
- Bot filtering, authentication, rate limiting
- A built-in scheduler — aggregation is invoked explicitly (see §3)

## 2. Architecture

```
Client ──HTTP──▶ FastAPI app (uvicorn, container port 8000; host port 8010 via compose)
                   ├── routers/videos.py    POST/GET /v1/videos
                   ├── routers/events.py    POST /v1/events/view[, /batch]
                   ├── routers/topk.py      GET /v1/top-k
                   └── routers/health.py    GET /healthz
                          │ async SQLAlchemy (asyncpg)
                          ▼
                 PostgreSQL 16 (Alembic-migrated)
                   ├── videos              video metadata
                   ├── view_events         raw events, PK event_id = idempotency key
                   └── window_aggregates   per-(video, window) counts, UNIQUE(video_id, window_start)
```

- **Runtime:** Python 3.12, FastAPI + uvicorn, async SQLAlchemy sessions
  (`src/youtube_topk/db.py`), pydantic-settings configuration (`src/youtube_topk/config.py`).
- **Layering:** routers (HTTP + validation via Pydantic schemas) → services
  (`services/videos.py`, `services/events.py`, `services/aggregation.py`) → ORM models
  (`models/`). Schemas live in `src/youtube_topk/schemas/`.
- **Persistence:** PostgreSQL 16 with Alembic migrations (`alembic/versions/001_initial.py`).
  SQLite (`sqlite+aiosqlite://`) is supported as a dev/test convenience; the app lifespan
  also runs `create_all` so a fresh SQLite database works without migrations.
- **Deployment:** Docker Compose — `app` + `db` services, app published on host port
  `${APP_PORT:-8010}`, Postgres not published to the host. See `DEPLOY.md`.

## 3. Key design decisions

- **Idempotent ingestion.** `event_id` (client-supplied UUID) is the primary key of
  `view_events`; inserts use `ON CONFLICT (event_id) DO NOTHING`, so re-posting the same
  event is a no-op. Ingestion endpoints return `202 Accepted` with an inserted count —
  fire-and-forget semantics matching the eventual streaming design.
- **Tumbling windows, most-recently-completed.** `compute_window_boundaries()`
  (`src/youtube_topk/services/aggregation.py`) floors the reference time to the hour /
  UTC midnight and returns the *previous completed* window, so reads never serve a
  partially-filled window.
- **Idempotent aggregation via UPSERT.** `aggregate_window()` groups `view_events` by
  video inside the window boundaries and writes counts with
  `INSERT … ON CONFLICT (video_id, window_start) DO UPDATE SET view_count = :view_count`
  (replace semantics). Re-running aggregation for the same window converges to the same
  state — safe for retries and reconciliation.
- **Explicit aggregation trigger.** No cron or scheduler ships with the MVP;
  `aggregate_window` is called from a script or scheduled job. This keeps the MVP a pure
  request/response service and makes window state fully deterministic in tests.
- **Read path is a single indexed query.** `GET /v1/top-k` reads `window_aggregates`
  directly (`ORDER BY view_count DESC LIMIT k`, k capped at 100) joined to `videos` for
  titles. No in-memory ranking structures or cache layer.
- **Pure PostgreSQL over streaming.** The relational path is the fallback/reconciliation
  path of the full design promoted to the primary path — the cheapest correct
  implementation of the FR set, and the baseline against which streaming components can
  later be measured.

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

Schema is owned by Alembic (`alembic/versions/001_initial.py`); ORM models mirror it in
`src/youtube_topk/models/`.

## 5. API summary

| Method | Path                     | Status | Description                                        |
|--------|--------------------------|--------|----------------------------------------------------|
| POST   | `/v1/videos`             | 201    | Register a video `{title, category?, region?}`     |
| GET    | `/v1/videos/{video_id}`  | 200/404| Get video details                                  |
| POST   | `/v1/events/view`        | 202    | Ingest one view event `{event_id, video_id, viewer_id, event_time}` |
| POST   | `/v1/events/view/batch`  | 202    | Ingest up to 500 events (`>500 → 422`)             |
| GET    | `/v1/top-k`              | 200    | `?window=hour\|day&k=50` (k 1–100) → ranked results + `metadata {window, refreshed_at, k}`; invalid window → 422 |
| GET    | `/healthz`               | 200    | Health check                                       |

Full request/response examples live in `README.md`.

## 6. Functional requirements → acceptance tests

Each FR from `SPEC.md` is verified by a dedicated black-box acceptance suite under
`verify/acceptance/`, run against the live app over HTTP (`API_BASE_URL`):

| FR | Requirement | Acceptance suite | Cases |
|----|-------------|------------------|-------|
| FR1 | Top-K by time window — `GET /v1/top-k?window=hour\|day&k` returns ranked `{video_id, count, rank}` + metadata; invalid window → 422 | `verify/acceptance/test_fr1_topk_by_window.py` | `test_fr1_topk_by_window_hour` (ingest → query → shape + metadata), `test_fr1_topk_invalid_window_422` |
| FR2 | View event ingestion — single + batch ≤500, 202 Accepted, idempotent by `event_id`, missing fields → 422 | `verify/acceptance/test_fr2_event_ingestion.py` | `test_fr2_single_event_202`, `test_fr2_batch_event_202`, `test_fr2_batch_over_500_rejected`, `test_fr2_idempotency` |
| FR3 | Video management — `POST /v1/videos` → 201; `GET /v1/videos/{id}` → 200 or 404 | `verify/acceptance/test_fr3_video_crud.py` | `test_fr3_create_video_201`, `test_fr3_get_video_200`, `test_fr3_get_video_404` |
| FR4 | Metadata on top-K — every response carries `metadata {window, refreshed_at, k}` | `verify/acceptance/test_fr4_metadata.py` | `test_fr4_metadata_present` |

`verify/manifest.env` defines how the stack is brought up for acceptance runs
(docker compose, port 8010, health-gated).

## 7. Test scenarios

Three layers, from in-process to black-box:

- **Unit — `tests/unit/`** (SQLite in-memory, no external services):
  window-boundary math for hour/day including midnight/month/new-year edges
  (`test_aggregation.py`), aggregate-then-query and UPSERT re-run idempotency,
  empty-window → empty results, event ingestion idempotency / mixed duplicate batches /
  empty batch (`test_event_service.py`), video CRUD (`test_video_service.py`), and model
  constraints — FK enforcement, `UNIQUE(video_id, window_start)` (`test_models.py`).
  Service-level suites also run at `tests/test_aggregation.py`,
  `tests/test_event_service.py`, `tests/test_video_service.py`.
- **Functional — `tests/functional/`** (against live PostgreSQL via `DATABASE_URL`):
  endpoint behavior end-to-end in-process — video 201/200/404, single + batch ingestion
  202, batch >500 → 422, missing fields → 422, top-k 200/422/empty-result handling.
- **Acceptance — `verify/acceptance/`** (black-box HTTP against a running app):
  the FR1–FR4 suites mapped in §6.

Covered scenarios include: correctly ranked top-K after ingestion; invalid window → 422;
batch edge counts (0, 500, 501-rejected); video not found → 404; duplicate `event_id`
re-POST is a no-op; UPSERT re-run yields identical aggregates; empty windows return empty
results rather than errors.

## 8. Test results

Continuous verification runs on GitHub Actions — **run on every push + daily** (each
workflow also triggers on pull requests and a daily cron schedule):

[![CI](https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/ci.yml/badge.svg)](https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/ci.yml)
[![Functional](https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/functional.yml/badge.svg)](https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/functional.yml)
[![Lint](https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/lint.yml/badge.svg)](https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/lint.yml)

| Workflow | Live results | What it runs |
|----------|--------------|--------------|
| CI | https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/ci.yml | Unit tests (`tests/unit/`), then boots the app against a PostgreSQL 16 service, runs migrations, health-gates, and executes the FR1–FR4 acceptance suites (`verify/acceptance/`) |
| Functional | https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/functional.yml | `tests/functional/` against a PostgreSQL 16 service with migrations applied |
| Lint | https://github.com/iliazlobin/sd-youtube-backend-mvp/actions/workflows/lint.yml | Ruff (rules E, F, I, B, UP, N, W) |
