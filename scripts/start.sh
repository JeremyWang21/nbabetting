#!/bin/bash
# Entrypoint for production: run migrations then start the app.
set -e

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting uvicorn..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 1
