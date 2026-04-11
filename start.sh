# #!/bin/bash

echo "🚀 Uruchamiam Nexus API (FastAPI) na porcie 8000..."
uv run uvicorn api:app --host 0.0.0.0 --port 8000 &

# Czekamy na wszystkie procesy w tle, aby kontener nie zakończył pracy
wait