FROM python:3.12-slim-bookworm

# Instalacja uv (najszybszy package manager dla Pythona)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# postgresql-client — potrzebny do backupów (pg_dump)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Kopiujemy pliki zależności osobno — warstwa cache Dockera nie przebuduje
# się przy zmianie kodu, tylko gdy zmienią się paczki
COPY pyproject.toml uv.lock ./

# Instalacja zależności z locked versions z uv.lock (deterministyczny build)
RUN uv sync --frozen --no-dev

# Kopiowanie reszty kodu
COPY . .

# Uruchamiamy TYLKO dashboard — silnik main.py startowany z GUI przyciskiem "URUCHOM"
# Uruchamianie main.py bezpośrednio z CMD powoduje duplikację procesu (drugi start z GUI).
CMD ["uv", "run", "streamlit", "run", "gui/dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]
