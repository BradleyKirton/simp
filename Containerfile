FROM docker.io/unit:python3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock .python-version /app/

RUN uv sync

COPY config /app/config
COPY manage.py /app/manage.py

EXPOSE 80