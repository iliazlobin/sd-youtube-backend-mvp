# Kickoff — YouTube MVP Build Plan

Prereqs (do these first):
1. Paste the system design into `docs/system-design.md`.
2. Fill `docs/mvp-scope.md` — especially **Functional Requirements** and **Acceptance Criteria** (these become
   the executable `verify/acceptance/` suite, the contract the whole build is measured against).

Then start the build. **Option A** (paste to the `zen` bot) decomposes from your Build Plan; **Option B**
(CLI) is a fully deterministic generic chain. The dispatcher (60s tick) runs the chain on its own; the
verifier gates each milestone and loops back on failure. You're only needed if a card hard-blocks past retries.

---

## Build Plan — implementation tasks by phase

Stack: Python 3.12 + FastAPI + PostgreSQL 16 + Alembic + Docker Compose.
3 entities, 6 endpoints, 1 aggregation service. No Kafka, no Flink, no Redis.

### Phase 1: Scaffold & Foundation (2 tasks)

> Tier: `[senior]` Project scaffold — repo layout, deps, config, app factory, health endpoint.
> Output: runnable `uvicorn` with `GET /healthz → 200`, empty router mounts ready for wiring.

**1.1 [senior] — Project scaffold: layout, deps, config**
- Create canonical `src/youtube_topk/` layout per `docs/SYSTEM-DESIGN-MVP-STANDARDS.md` §1:
  `main.py`, `config.py`, `db.py`, `routers/`, `models/`, `schemas/`, `services/`
- Write `pyproject.toml` with runtime deps (`fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`,
  `asyncpg`, `pydantic-settings`, `alembic`) + dev extras (`pytest`, `httpx`, `pytest-asyncio`)
- Write `.gitignore` (venvs, `__pycache__`, `.env`, `*.egg-info`, `.pytest_cache`, `*.rdb`)
- Write `.env.example` with `DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/youtube_topk`,
  `APP_PORT=8010`
- Acceptance: `pip install -e .` succeeds; imports `youtube_topk` cleanly

**1.2 [senior] — Config + database + app factory + healthz**
- Write `config.py`: `Settings(BaseSettings)` with `DATABASE_URL` (typed `PostgresDsn`),
  `APP_PORT: int = 8000`, `extra="ignore"`
- Write `db.py`: `create_async_engine` from settings, `async_sessionmaker`, `get_session` async generator
- Write `main.py`: `create_app()` factory with `lifespan` (engine start/dispose), mount routers
  under `/v1` (empty stubs), `GET /healthz` returning `{"status": "ok"}`
- Acceptance: `uvicorn youtube_topk.main:app` starts; `curl localhost:8000/healthz` → 200

---

### Phase 2: Data Model (4 tasks)

> Core data structures — the load-bearing layer. Every downstream task depends on these.
> Tier: `[staff]` for ORM models + migration shape; `[senior]` for Alembic boilerplate.

**2.1 [staff] — Video ORM model** (`models/video.py`)
- `Video`: `video_id` UUID PK (server-generated, `uuid4`), `title` text NOT NULL,
  `category` text nullable, `region` text nullable, `created_at` timestamp server default `now()`
- `__tablename__ = "videos"`
- No business logic; pure ORM mapping

**2.2 [staff] — ViewEvent ORM model** (`models/view_event.py`)
- `ViewEvent`: `event_id` UUID PK (idempotency key, client-supplied), `video_id` UUID FK → videos,
  `viewer_id` text NOT NULL, `event_time` timestamp NOT NULL, `created_at` timestamp server default `now()`
- `__tablename__ = "view_events"`
- No `ON CONFLICT` on the model — that's in the service layer's SQL

**2.3 [staff] — WindowAggregate ORM model** (`models/window_aggregate.py`)
- `WindowAggregate`: `id` serial PK (surrogate), `video_id` UUID FK → videos,
  `window_start` timestamp NOT NULL, `window_end` timestamp NOT NULL, `view_count` integer NOT NULL DEFAULT 0
- `__tablename__ = "window_aggregates"`
- Unique constraint on `(video_id, window_start)` — the UPSERT key. Model this as
  `UniqueConstraint("video_id", "window_start")` on `__table_args__`

**2.4 [senior] — Alembic initial migration**
- `alembic init alembic`; wire `env.py` for async (use `config.py`'s `DATABASE_URL`,
  `target_metadata` from all three models)
- Generate `alembic/versions/001_initial.py` — all three tables:
  `videos` (UUID PK + index on `created_at`),
  `view_events` (UUID PK + FK → videos + index on `(video_id, event_time)` + unique on `event_id`),
  `window_aggregates` (serial PK + FK → videos + unique on `(video_id, window_start)` + index on
  `(window_start, view_count DESC)`)
- Acceptance: `alembic upgrade head` creates all three tables in Postgres

---

### Phase 3: API Contracts — Schemas (3 tasks)

> Public API contract shapes. These define the wire format; routers + services reference them.
> Tier: `[staff]` — API contracts are public surface.

**3.1 [staff] — Video pydantic schemas** (`schemas/video.py`)
- `CreateVideoRequest`: `title: str`, `category: str | None = None`, `region: str | None = None`
- `VideoResponse`: `video_id: UUID`, `title: str`, `category: str | None`, `region: str | None`,
  `created_at: datetime`
- Config: `from_attributes = True`

**3.2 [staff] — Event pydantic schemas** (`schemas/event.py`)
- `ViewEventRequest`: `video_id: UUID`, `viewer_id: str`, `event_time: datetime`
- `BatchViewEventsRequest`: `events: list[ViewEventRequest]`, validate `len(events) <= 500` via
  `@field_validator` raising `ValueError`
- `AcceptedResponse`: `{"status": "accepted", "count": N}` — returned by both single and batch

**3.3 [staff] — Top-K pydantic schemas** (`schemas/topk.py`)
- `TopKResult`: `video_id: UUID`, `title: str`, `view_count: int`, `rank: int`
- `TopKMetadata`: `window: str` (the window param echoed), `refreshed_at: datetime`, `k: int`
- `TopKResponse`: `results: list[TopKResult]`, `metadata: TopKMetadata`
- Query params: `window: Literal["hour", "day"]`, `k: int = 50` (validated range 1–100)

---

### Phase 4: Routers — HTTP Layer (4 tasks)

> Thin HTTP layer only: parse request, call service, serialize response. No business logic, no SQL.
> Tier: `[senior]` — CRUD glue and wiring.

**4.1 [senior] — Video router** (`routers/videos.py`)
- `POST /v1/videos` → parse `CreateVideoRequest`, generate `video_id` (UUID4), insert via service,
  return 201 + `VideoResponse`
- `GET /v1/videos/{video_id}` → lookup via service, return 200 + `VideoResponse` or 404
- Router prefix: `"/v1/videos"`, tags: `["videos"]`

**4.2 [senior] — Event router** (`routers/events.py`)
- `POST /v1/events/view` → parse `ViewEventRequest`, call `ingest_view_event()` service,
  return 202 + `AcceptedResponse(count=1)`
- `POST /v1/events/view/batch` → parse `BatchViewEventsRequest`, validate ≤500 events (422 on >500),
  call `ingest_view_events_batch()`, return 202 + `AcceptedResponse(count=N)`
- Router prefix: `"/v1/events"`, tags: `["events"]`

**4.3 [senior] — Top-K router** (`routers/topk.py`)
- `GET /v1/top-k` → parse `window` + `k` query params (422 on invalid window),
  compute window boundaries from current time (most recent completed window),
  call `get_top_k()`, return 200 + `TopKResponse`
- Router prefix: `"/v1/top-k"`, tags: `["top-k"]`

**4.4 [senior] — Health router** (`routers/health.py`)
- `GET /healthz` → 200 `{"status": "ok"}`
- No prefix; mount on root during `create_app()`

---

### Phase 5: Business Logic — Services (3 tasks)

> Core algorithms and data access. The load-bearing code the spec calls for.
> Tier: `[staff]` — aggregation logic, idempotent ingestion, UPSERT patterns.

**5.1 [staff] — Video service** (`services/videos.py`)
- `create_video(db, data: CreateVideoRequest) -> Video` — generate UUID, INSERT, return ORM object
- `get_video(db, video_id: UUID) -> Video | None` — SELECT by PK
- Straightforward CRUD; delegate to SQLAlchemy

**5.2 [staff] — Idempotent event ingestion service** (`services/events.py`)
- `ingest_view_event(db, event: ViewEventRequest) -> None`:
  ```sql
  INSERT INTO view_events (event_id, video_id, viewer_id, event_time)
  VALUES (:event_id, :video_id, :viewer_id, :event_time)
  ON CONFLICT (event_id) DO NOTHING
  ```
  Use raw SQL (or SQLAlchemy `insert().on_conflict_do_nothing()`) — this IS the core semantics.
  Return count of rows inserted (1 = new, 0 = duplicate). No error on duplicate — it's a no-op.
- `ingest_view_events_batch(db, events: list[ViewEventRequest]) -> int`:
  Same `ON CONFLICT DO NOTHING` INSERT, iterating or using `executemany`.
  Return count of rows actually inserted (may be < len(events) due to duplicates).
- Acceptance: fire same `event_id` twice → second call returns `count=0` for that event, no 409 error.
  Batch with mixed new/dup events → returns count of only new inserts.

**5.3 [staff] — Window aggregation service** (`services/aggregation.py`)
- `compute_window_boundaries(window: str, reference_time: datetime | None = None) -> tuple[datetime, datetime]`:
  - `"hour"`: floor `reference_time` to current hour boundary; window_start = that, window_end = +1 hour
  - `"day"`: floor to midnight UTC; window_start = that, window_end = +24 hours
  - MVP semantics: return the *most recently completed* window (not the current incomplete one).
    So at 14:35, the "hour" window is 13:00–14:00; the "day" window is yesterday midnight–today midnight.
- `aggregate_window(db, window_start: datetime, window_end: datetime) -> None`:
  ```sql
  INSERT INTO window_aggregates (video_id, window_start, window_end, view_count)
  SELECT video_id, :window_start, :window_end, COUNT(*) as view_count
  FROM view_events
  WHERE event_time >= :window_start AND event_time < :window_end
  GROUP BY video_id
  ON CONFLICT (video_id, window_start) DO UPDATE
  SET view_count = window_aggregates.view_count + EXCLUDED.view_count,
      window_end = EXCLUDED.window_end
  ```
  Called on-demand (manual trigger for MVP) or from a background task / scheduled endpoint.
  The UPSERT ensures rerunning the same window is idempotent — counts accumulate correctly.
- `get_top_k(db, window_start: datetime, window_end: datetime, k: int) -> list`:
  ```sql
  SELECT wa.video_id, v.title, wa.view_count
  FROM window_aggregates wa
  JOIN videos v ON v.video_id = wa.video_id
  WHERE wa.window_start = :window_start AND wa.window_end = :window_end
  ORDER BY wa.view_count DESC
  LIMIT :k
  ```
  Return results with computed rank (1-indexed from the sorted list). Empty result set → empty list, not error.
- `get_window_count(db, video_id: UUID, window_start: datetime) -> int`:
  Fallback query for a single video in a window — used by `GET /v1/videos/{video_id}/count` if needed
  (out of scope for MVP but the interface is cheap to expose).

---

### Phase 6: Docker & Deployment (3 tasks)

> Tier: `[senior]` — config, compose, documentation.

**6.1 [senior] — Multi-stage Dockerfile**
- `FROM python:3.12-slim AS builder`: `python -m venv /opt/venv`, `pip install .`
- `FROM python:3.12-slim`: `COPY --from=builder /opt/venv /opt/venv`,
  `ENV PATH="/opt/venv/bin:$PATH"`, `COPY src/ /app/src/`, `COPY alembic/ /app/alembic/`,
  `COPY alembic.ini /app/`, `WORKDIR /app`
- `CMD ["uvicorn", "youtube_topk.main:app", "--host", "0.0.0.0", "--port", "8000"]`
- Key: venv copy, not `--target` — preserves console entry-point scripts (uvicorn, alembic) on PATH

**6.2 [senior] — docker-compose.yml**
- Service `db`: `image: postgres:16`, env `POSTGRES_USER/PASSWORD/DB`, healthcheck `pg_isready`
- Service `app`: `build: .`, port `"${APP_PORT:-8010}:8000"`, `depends_on: { db: { condition: service_healthy } }`,
  env `DATABASE_URL`, healthcheck `curl -f http://localhost:8000/healthz`
- DB port NOT published to host — only app port. Compose network for inter-service comms.

**6.3 [senior] — DEPLOY.md**
- Clean checkout → `docker compose up -d --build` → `alembic upgrade head` → working
- Migration run command: `docker compose run --rm app alembic upgrade head`
- Smoke test: `curl http://localhost:$APP_PORT/healthz`
- Teardown: `docker compose down -v`

---

### Phase 7: Tests (3 task groups)

> Tier: `[senior]` — test fixtures, fixtures, CRUD tests.
> Acceptance cases emitted by architect are the fixed contract; tier is architect's scope.

**7.1 [senior] — White-box unit tests** (`tests/unit/`)
- `test_models.py` — verify ORM table creation, FK constraints
- `test_video_service.py` — create + get, 404 on missing
- `test_event_service.py` — single ingest, batch ingest, idempotency (re-POST same event_id),
  batch edge counts (0, 500, mixed dup/new)
- `test_aggregation.py` — window boundary computation (hour/day), aggregate + top-K query,
  empty window → empty results, UPSERT rerun idempotency

**7.2 [senior] — White-box integration tests** (`tests/functional/`)
- `conftest.py` — test DB with `create_all` + `drop_all` per module, async test client (`httpx.AsyncClient`
  via `ASGITransport` or `TestClient`)
- `test_video_endpoints.py` — HTTP-level: POST 201, GET 200, GET 404
- `test_event_endpoints.py` — POST 202, batch 202, batch >500 → 422, missing fields → 422
- `test_topk_endpoint.py` — valid window → 200 + results, invalid window → 422,
  empty window → 200 + empty results, metadata correctness

**7.3 [architect] — Black-box acceptance tests** (`verify/acceptance/`)
- One file per functional requirement, named `test_fr<N>_<slug>.py`:
  - `test_fr1_topk_by_window.py` — `GET /v1/top-k?window=hour&k=10` returns ranked results
    with metadata after ingesting view events + running aggregation
  - `test_fr2_event_ingestion.py` — single + batch POST 202, idempotency on duplicate event_id,
    batch >500 → 422
  - `test_fr3_video_crud.py` — POST 201, GET 200, GET 404
  - `test_fr4_metadata.py` — Top-K response includes `{window, refreshed_at, k}` metadata
- **Black-box only**: use `httpx` against `API_BASE_URL` (from env), no app imports.
  Each test seeds data via the API, triggers aggregation if needed, then asserts response shapes.
- These are the fixed contract — the verifier gates on them. Do NOT edit/loosen/skip.

---

### Phase 8: Polish & Handoff (2 tasks)

> Tier: `[senior]` — documentation, manifest.

**8.1 [senior] — README.md**
- What it is (YouTube Top-K leaderboard MVP)
- Stack (Python 3.12, FastAPI, PostgreSQL 16, Docker Compose)
- Quickstart: `docker compose up -d --build && docker compose run --rm app alembic upgrade head`
- API table: 6 endpoints with methods, paths, status codes, brief descriptions
- Architecture diagram (ASCII or reference to `docs/system-design.md`)

**8.2 [senior] — verify/manifest.env**
- `MODE`, `PORT`, `BOARD="projects"`, `UP`, `DOWN`, `READY`, `LOGS`, `TEST_DEPS`, `ACCEPTANCE`
- Format per `e2e-verify init` convention: multi-word values single-quoted
- `TEST_DEPS='httpx pytest'` (black-box only — no app deps)

---

## Task-to-tier summary

| Phase | Tasks | Tier |
|-------|-------|------|
| 1. Scaffold & Foundation | 2 | [senior] |
| 2. Data Model | 4 | 3× [staff], 1× [senior] |
| 3. API Contracts — Schemas | 3 | [staff] |
| 4. Routers — HTTP Layer | 4 | [senior] |
| 5. Business Logic — Services | 3 | [staff] |
| 6. Docker & Deployment | 3 | [senior] |
| 7. Tests | 3 groups | [senior] (+ architect for acceptance) |
| 8. Polish & Handoff | 2 | [senior] |

**Total: ~21 tasks** (16 senior, 6 staff, plus architect-owned acceptance). The staff tasks are the
load-bearing ~20%: data model, idempotent ingestion, window aggregation, and API contracts.

---

## Option A — paste this to the zen bot

> Start the **YouTube MVP** build on the **`projects`** kanban board. First read
> `/root/Hermes/projects/sd-youtube-backend-mvp-v2026.07.01.1/AGENTS.md`, `docs/system-design.md`, and `docs/mvp-scope.md`. Then create the dependency
> chain from `docs/mvp-scope.md` → **Build Plan**: `architect` (design.md + the executable
> `verify/acceptance/` suite, one black-box case per functional requirement) → `senior-engineer`/`staff-engineer`
> build cards → `verifier` (the gate) → `sre` (compose + `verify/manifest.env`) → `writer`. Each card depends
> on the previous and shares `--workspace dir:/root/Hermes/projects/sd-youtube-backend-mvp-v2026.07.01.1`. Make build cards goal-loop. Then let the board
> run — the verifier passes only on pasted evidence and loops back on failure. Message me only on a hard block.
> Reply with the cards you created.

---

## Option B — deterministic generic CLI (run on the Mac host)

```bash
export PATH="$HOME/.local/bin:$PATH"
B="--board projects"
WS="--workspace dir:/root/Hermes/projects/sd-youtube-backend-mvp-v2026.07.01.1"
RD="Read AGENTS.md, docs/system-design.md, and docs/mvp-scope.md first."
jid(){ python3 -c "import sys,json;print(json.load(sys.stdin)['id'])"; }

C1=$(hermes kanban $B create "Architect: design.md + module layout + executable acceptance suite" \
  --assignee architect --goal --goal-max-turns 25 $WS \
  --body "$RD Produce design.md (module/file layout, data flow, API/handler or CLI contracts). Then emit verify/acceptance/ — ONE executable black-box pytest case per Functional Requirement in docs/mvp-scope.md, asserting real input->output (status codes, bodies, error cases, idempotency, concurrency) against the RUNNING system via API_BASE_URL. Do NOT import the app in these cases. Flesh out the Build Plan in docs/mvp-scope.md. No app code yet." --json | jid)

C2=$(hermes kanban $B create "Senior-engineer: scaffold + bring-up + healthz" \
  --assignee senior-engineer --parent $C1 --goal --goal-max-turns 30 --max-retries 3 $WS \
  --body "$RD Implement the scaffold per design.md: repo layout, deps, config/env, docker-compose (if applicable; do NOT hardcode host ports that collide — see AGENTS.md), schema + migrations, a health/seed endpoint or CLI entrypoint. The app/CLI must START and a pytest skeleton must be green. Start it before completing." --json | jid)

C3=$(hermes kanban $B create "Staff-engineer: implement MVP until verify/acceptance passes" \
  --assignee staff-engineer --parent $C2 --goal --goal-max-turns 45 --max-retries 3 $WS \
  --body "$RD Implement the MVP functional requirements per design.md + docs/mvp-scope.md until EVERY case in verify/acceptance/ passes sandbox-native (run the app in-container, reach host services via host.docker.internal or stubs). The acceptance suite is the FIXED contract — make the system satisfy it; do NOT edit/skip/loosen the cases. Paste the passing run." --json | jid)

C4=$(hermes kanban $B create "Verifier: GATE — clean checkout, unit tests + acceptance suite, evidence" \
  --assignee verifier --parent $C3 --max-retries 3 $WS \
  --body "$RD From a CLEAN state: run the white-box unit tests AND the black-box verify/acceptance suite against a locally-run instance. Walk every Acceptance Criterion with pasted, executed evidence. PASS with metadata {\"gate\":\"pass\"} only on full evidence; otherwise BLOCK with the exact failures. Never pass on 'looks right'." --json | jid)

C5=$(hermes kanban $B create "SRE: compose polish + DEPLOY.md + .env.example + verify/manifest.env" \
  --assignee sre --parent $C4 --goal --goal-max-turns 25 $WS \
  --body "$RD Make 'clean checkout -> up -> working' reproducible (DEPLOY.md, .env.example names-only, healthchecks; no colliding host ports). ALSO author verify/manifest.env for the host e2e loop: MODE, an isolated UP/DOWN (overridable \$PORT), a READY check hitting a real endpoint, LOGS, TEST_DEPS (black-box client only), and ACCEPTANCE running verify/acceptance against the live \$PORT. Do not run e2e-verify (host-only) — just write a correct manifest. FORMAT (critical — e2e-verify does \`set -a; . manifest.env\`, so it SOURCES the file): every value containing spaces MUST be single-quoted, e.g. \`UP='docker compose up -d --build'\`, \`READY='curl -sf http://localhost:\$PORT/healthz'\`, \`ACCEPTANCE='API_BASE_URL=\"http://localhost:\$PORT\" \"\$PY\" -m pytest verify/acceptance -q'\` — an UNQUOTED multi-word value gets run as a shell command at source-time, leaving the var EMPTY so e2e silently skips it and FALSELY reports PASS. \`TEST_DEPS\` must be SPACE-separated (\`TEST_DEPS='httpx pytest'\`), never comma-separated (pip runs \`pip install \$TEST_DEPS\`). Match the format \`e2e-verify init\` emits." --json | jid)

C6=$(hermes kanban $B create "Writer: README + MVP synthesis (evidence-backed only)" \
  --assignee writer --parent $C5 --goal --goal-max-turns 20 $WS \
  --body "$RD Write README.md (what it is, quickstart, architecture, API/CLI summary) and a short synthesis tracing every claim to a real artifact. Document only commands that appear, passing, in the verifier's evidence." --json | jid)

echo "Created chain: C1=$C1 C2=$C2 C3=$C3 C4=$C4 C5=$C5 C6=$C6"
```

---

## Turn on the host e2e acceptance loop (after the chain is green)
`e2e-verify` is host-only (not in the sandbox), so the owner runs this once the build is green:

```bash
~/Hermes/bin/e2e-verify register /root/Hermes/projects/sd-youtube-backend-mvp-v2026.07.01.1   # join the shared 30m acceptance cron
~/Hermes/bin/e2e-verify run /root/Hermes/projects/sd-youtube-backend-mvp-v2026.07.01.1         # confirm green now; red -> self-files fix cards to projects
```

From then on the shared cron `E2E Verifier (all projects)` re-runs the full acceptance suite against the live
system every 30m and self-files the bounded fix→reverify loop on any regression.

---

## Watch & steer
- `hermes kanban --board projects stats` · `watch` · `comment <id> "<note>"` · `block`/`unblock`/`reassign`
- Dashboard `/kanban`. Pause everything: `hermes gateway stop` (resume: `start`).
