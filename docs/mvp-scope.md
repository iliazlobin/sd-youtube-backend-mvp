# YouTube Top-K MVP — Scope

Variant: **mvp** (core FRs only — smallest thing that works)

## In scope

- **FR1 — Top-K by time window.** Return top-K videos by view count for a given tumbling window (hour, day). `GET /v1/top-k?window=hour|day&k=50` returns a ranked list of {video_id, count, rank} with a `refreshed_at` timestamp.
- **FR2 — Tumbling windows.** Support hour and day granularity. Views are aggregated into tumbling windows; queries read the most recent completed window.
- **FR4 — Metadata.** Each response carries `{window, refreshed_at, k}` metadata.
- **Event ingestion.** `POST /v1/events/view` accepts a single view event {video_id, viewer_id, event_time} and returns 202 Accepted. Batch endpoint `POST /v1/events/view/batch` accepts up to 500 events.
- **Video registration.** `POST /v1/videos` and `GET /v1/videos/{id}` — simple CRUD for videos.

## Out of scope

- Sliding/trending windows (FR3 — real-time "hot right now")
- Per-region and per-category top-K (FR5)
- Full fault tolerance with Kafka + Flink (FR6 — MVP uses a simpler PostgreSQL-backed aggregation)
- Space-Saving sketch (MVP uses exact counting via PostgreSQL)
- Bot filtering
- Redis caching layer (MVP serves directly from PostgreSQL)
- Authentication / rate limiting

## MVP architecture (simplified from the design)

- **Ingestion:** FastAPI endpoints accept view events → write to PostgreSQL `view_events` table
- **Aggregation:** PostgreSQL materialized view or scheduled aggregation (hourly `window_aggregates` table, populated by a background task / cron within the FastAPI app)
- **Query:** `GET /v1/top-k` reads from `window_aggregates` with `ORDER BY view_count DESC LIMIT k`
- **No Kafka, no Flink, no Redis** — the MVP uses the design's batch reconciliation path (PostgreSQL) as the primary path
