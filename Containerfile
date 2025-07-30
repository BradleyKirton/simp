FROM docker.io/unit:python3.13-slim AS build
ENV UV_COMPILE_BYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock /

RUN uv venv /.venv
RUN uv sync

FROM docker.io/unit:python3.13-slim

WORKDIR /app

COPY --from=build /.venv /app/.venv
COPY config /app/config
COPY core /app/core
COPY db /app/db
COPY templates /app/templates
COPY .python-version manage.py /app/

EXPOSE 80