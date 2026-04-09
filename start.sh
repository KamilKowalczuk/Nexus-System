# #!/bin/bash
# # Uruchamiamy FastAPI w tle
# uv run uvicorn api:app --host 0.0.0.0 --port 8000 &
# PID_API=$!

# # # Uruchamiamy Streamlit na pierwszym planie (tymczasowo aż nowy panel przejmie 100% funkcji)
# # uv run streamlit run gui/dashboard.py --server.port=8501 --server.address=0.0.0.0

# # Oczekujemy na proces w tle w razie błędu
# wait $PID_API

#!/bin/bash

echo "🚀 Uruchamiam Nexus API (FastAPI) na porcie 8000..."
uv run uvicorn api:app --host 0.0.0.0 --port 8000 &

echo "📊 Uruchamiam Nexus Dashboard (Streamlit) na porcie 8501..."
uv run streamlit run gui/dashboard.py --server.port=8501 --server.address=0.0.0.0 &

# Czekamy na wszystkie procesy w tle, aby kontener nie zakończył pracy
wait