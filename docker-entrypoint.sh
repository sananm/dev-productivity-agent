#!/bin/sh
# API container entrypoint: wait for Postgres, set up the schema + data, then serve.
# Idempotent — safe to restart; it only re-indexes when the vector table is empty.
set -e

echo "[entrypoint] waiting for postgres..."
until python -c "import os,psycopg; psycopg.connect(os.environ['DATABASE_URL']).close()" 2>/dev/null; do
  sleep 2
done
echo "[entrypoint] postgres reachable"

echo "[entrypoint] applying schema + checkpoint tables"
python -m devagent.db.migrate

echo "[entrypoint] seeding evaluation cases"
python -m eval.cases
python -m eval.generate || echo "[entrypoint] case generation skipped"

ALREADY=$(python - <<'PY' 2>/dev/null || echo 0
from devagent.db.migrate import vector_table_exists
from devagent.db.session import fetch_one
print(fetch_one("SELECT count(*) c FROM data_vector_nodes")["c"] if vector_table_exists() else 0)
PY
)
if [ "$ALREADY" = "0" ]; then
  echo "[entrypoint] indexing ${DEFAULT_REPO:-psf/requests} (first boot)"
  python -m devagent.cli.app index "${DEFAULT_REPO:-psf/requests}"
else
  echo "[entrypoint] index already has $ALREADY chunks — skipping ingest"
fi

echo "[entrypoint] starting API on :8000"
exec uvicorn devagent.api.main:app --host 0.0.0.0 --port 8000
