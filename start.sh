#!/bin/bash
set -e

echo "🚀 Uruchamiam Nexus API (FastAPI) na porcie 8000..."
exec uv run uvicorn api:app --host 0.0.0.0 --port 8000