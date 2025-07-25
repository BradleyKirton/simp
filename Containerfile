FROM docker.io/unit:python3.13-slim AS build
ENV UV_COMPILE_BYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN uv venv /.venv
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

COPY pyproject.toml uv.lock /
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

FROM docker.io/unit:python3.13-slim

WORKDIR /app

COPY --from=build /.venv /app/.venv
COPY core /app/core
COPY config /app/config
COPY .python-version manage.py /app/

EXPOSE 80