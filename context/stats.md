# 10. SYSTEM ZBIERANIA STATYSTYK DLA PAYLOAD CMS / RESEND

## 1. Kontekst
System działa w modelu "Done-For-You". Klient nie ma panelu. Otrzymuje tylko piękne raporty HTML co 3 dni (wysyłane z Payload CMS przez Resend).
Musimy przygotować bazę danych PostgreSQL (zarządzaną przez SQLAlchemy w Pythonie), aby agregowała dane w sposób łatwy do odczytania przez zewnętrzny backend Payload.

## 2. Zadania dla Claude Code:

### KROK 1: Model Danych (Tabela Logów / Statystyk) w `app/database.py`
Utwórz tabelę `campaign_statistics`.
Zamiast agregować dni, będziemy tworzyć wpisy dzienne, które Payload sobie zsumuje.
Kolumny:
- `id` (Primary Key)
- `client_id` (Relacja do Client)
- `date` (Data, unikalna dla danego client_id)
- `scanned_domains` (Integer, domyślnie 0)
- `rejected_domains` (Integer, domyślnie 0)
- `bounces_prevented` (Integer, domyślnie 0)
- `emails_sent` (Integer, domyślnie 0)
- `replies_received` (Integer, domyślnie 0)

### KROK 2: Klasa Menadżera Statystyk
Stwórz plik `app/stats_manager.py`. Zaimplementuj w nim funkcje aktualizujące statystyki "w locie" (z użyciem klauzuli UPSERT, czyli "wstaw lub zaktualizuj, jeśli wpis z dzisiejszą datą już istnieje"):
- `increment_scanned(session, client_id, count=1)`
- `increment_rejected(session, client_id, count=1)`
- `increment_bounces(session, client_id, count=1)`
- `increment_sent(session, client_id, count=1)`
- `increment_replies(session, client_id, count=1)`

### KROK 3: Integracja z Agentami
Wstrzyknij wywołania funkcji z `stats_manager.py` do odpowiednich miejsc w systemie:
- `app/agents/scout.py` i `researcher.py` (przy skanowaniu i odrzucaniu).
- `app/agents/sender.py` (po udanej wysyłce, oraz przy weryfikacji DeBounce).
- `app/agents/inbox.py` (gdy zarejestrowana zostanie odpowiedź klienta).