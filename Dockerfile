FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-dev

COPY ./app ./app

COPY alembic.ini ./
COPY migrations ./migrations

ENV PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --uid 1000 worker
USER worker

CMD ["taskiq", "worker", "app.core.broker:broker", "--fs-discover", "--tasks-pattern", "app/**/tasks.py", "--workers", "1"]
