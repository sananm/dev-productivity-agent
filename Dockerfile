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

EXPOSE 8000

CMD ["uvicorn", "devagent.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
