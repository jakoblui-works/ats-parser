# ats-parser

Taskiq worker for the ATS check.

A Taskiq worker on Redis Streams, made from [worker-template](https://github.com/jakoblui-works/worker-template). It owns the `ats` Postgres schema and its migrations.

## Development
```sh
cp .env.example .env    # fill in the passwords
uv sync
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
uv run alembic upgrade head
uv run taskiq worker app.core.broker:broker --fs-discover --tasks-pattern "app/**/tasks.py"
uv run python -m scripts.send_ping   # with the worker running
```
Tests need Postgres and Garage; the worker needs Redis, S3 and Postgres at startup. Locally, all of them come from the api repo's `compose.dev.yml` stack.

## Template updates
```sh
copier update --trust
```
Commit everything first, then review the result as an ordinary diff. A conflict in `uv.lock` is resolved by running `uv lock`.
