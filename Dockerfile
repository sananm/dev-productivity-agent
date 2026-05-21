FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for layer caching.
COPY pyproject.toml README.md ./
COPY devagent ./devagent
RUN pip install --upgrade pip && pip install ".[eval]"

COPY eval ./eval
COPY fixtures ./fixtures
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

EXPOSE 8000

# The entrypoint waits for Postgres, migrates, seeds, indexes (first boot only),
# then serves — so `docker compose up` is the whole demo.
CMD ["./docker-entrypoint.sh"]
