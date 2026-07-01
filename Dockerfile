# ---- builder stage ----
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1

COPY pyproject.toml ./
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir .

# ---- runtime stage ----
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"

COPY --from=builder /opt/venv /opt/venv
COPY src/ /app/src/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/

WORKDIR /app

EXPOSE 8000

CMD ["uvicorn", "youtube_topk.main:app", "--host", "0.0.0.0", "--port", "8000"]
