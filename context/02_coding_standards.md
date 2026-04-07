# 02. CODING STANDARDS & BEST PRACTICES

Jako inżynier pracujący nad Nexus Engine, masz bezwzględny zakaz pisania kodu prototypowego. Twój kod idzie na produkcję.

## 1. Type Hinting & Pydantic
- Używaj ścisłego typowania w każdej nowej/modyfikowanej funkcji (`def function_name(arg: str) -> dict:`).
- Wykorzystuj `app/schemas.py` (Pydantic v2) do walidacji każdego wejścia i wyjścia z modelu LLM. 
- Zamiast surowych stringów, jeśli to możliwe, używaj struktur danych (np. Enums dla statusów).

## 2. Asynchronous Execution (asyncio)
- Zawsze używaj `async/await` dla operacji I/O (API calls, DB queries).
- Jeśli musisz użyć biblioteki synchronicznej (np. starego SMTP), opakuj ją w `await asyncio.to_thread(func)`.
- Blokowanie Event Loop'a (np. przez `time.sleep()`) to grzech kardynalny. Zawsze używaj `asyncio.sleep()`.

## 3. Error Handling & Logging
- Używaj istniejącego loggera z `main.py` (`logging.getLogger("...")`).
- Nigdy nie używaj pustego `except Exception: pass`. Wyłapuj konkretne wyjątki, a jeśli wyłapujesz ogólne - loguj je za pomocą `logger.error(..., exc_info=True)`.
- Ciche ignorowanie błędów jest zabronione. System ma zapisywać statusy błędów do DB (np. `lead.status = "ERROR"`).

## 4. Refactoring Rules
- Maksymalna długość funkcji to 50-60 linii kodu. Jeśli `run_client_cycle` w `main.py` puchnie, ekstrahuj logikę do prywatnych funkcji pomocniczych.
- Unikaj Hardcodingu. Używaj `.env` dla timeoutów, limitów, kluczy API.
- HTML Sanitization: Regex do czyszczenia HTML (jak w `writer.py`) to zła praktyka produkcyjna. Jeśli modyfikujesz parser HTML, zaproponuj użycie `BeautifulSoup` z biblioteki `bs4` (wymaga dodania do `pyproject.toml`).