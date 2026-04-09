FROM python:3.12-slim-bookworm

# Instalacja uv (najszybszy package manager dla Pythona)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# postgresql-client-17 — Railway ma PostgreSQL 17.x, pg_dump MUSI mieć tą samą wersję
# Bez tego backupy mają 0 bajtów (pg_dump: error: aborting because of server version mismatch)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-17 \
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
CMD ["./start.sh"]
