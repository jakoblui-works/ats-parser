# ats-service

Taskiq worker for the ATS check. Made from `worker-template` (Copier); `.copier-answers.yml` records the version.

## Commands
```sh
uv sync
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "<message>"
uv run taskiq worker app.core.broker:broker --fs-discover --tasks-pattern "app/**/tasks.py"
uv run python -m scripts.send_ping     # send a ping task to a running worker
docker build -t ats-service:local .
copier update --trust                  # pull template changes; commit first
```
Tests need Postgres (CI: a `postgres:18` service; locally, the api repo's `compose.dev.yml` stack). They recreate a `ats_test` database.

## Layout
- `app/core/`: settings, broker, database, the declarative `Base`.
- `app/health/`: the `ats.ping.v1` task. Entry points always live in `app/**/tasks.py`.
- `app/storage/`: S3 client.

## Contracts
- **Owns** the `ats` schema. Every table lives in it (`Base` sets the schema), and Alembic only looks at it.
- Task names are `ats.<name>.v<n>`. A contract changes by adding a version, never by editing one in place.

## Gotchas
- Import every models module in `migrations/env.py`, or autogenerate and `alembic check` won't see its tables.
- mypy is strict and covers `app`, `tests`, `migrations`, `scripts`.
