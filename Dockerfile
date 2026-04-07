FROM python:3.12-slim-bookworm

# Instalacja uv (najszybszy package manager dla Pythona)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Kopiujemy pliki zależności osobno — warstwa cache Dockera nie przebuduje
# się przy zmianie kodu, tylko gdy zmienią się paczki
COPY pyproject.toml uv.lock ./

# Instalacja zależności używając locked versions (identyczne co lokalnie)
RUN uv pip install --system -r pyproject.toml

# Kopiowanie reszty kodu
COPY . .

# Uruchomienie silnika i dashboardu równocześnie
CMD ["sh", "-c", "python main.py & streamlit run gui/dashboard.py --server.port=8501 --server.address=0.0.0.0"]
