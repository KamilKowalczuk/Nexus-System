# 04. CURRENT OBJECTIVES (Dla Claude Code)

W tej sesji re-architektonizujemy system pod kątem bezpieczeństwa prawnego (RODO) i aktualizujemy silniki do najnowszej generacji modeli Google. Wykonaj poniższe kroki w podanej kolejności:

### Krok 1: Aktualizacja Modeli AI (Seria Gemini 3.1)
Zrefaktoryzuj pliki `app/agents/writer.py`, `app/agents/researcher.py` oraz `app/agents/strategy.py` (lub inne wywołujące LLM).
- Dla `writer_llm` i `auditor_llm` zmień model na `gemini-3.1-pro-preview`. Dostosuj parametry temperature, aby zmaksymalizować precyzję.
- W badaniu i scrapingu zmień model na `gemini-3.1-flash-lite-preview`.
Upewnij się, że biblioteka `langchain-google-genai` w `pyproject.toml` jest zaktualizowana do wersji bezproblemowo obsługującej te modele.

### Krok 2: Architektura RODO (Moduł Bezpieczeństwa)
Stwórz plik `app/rodo_manager.py`. Zaimplementuj w nim funkcje:
1. `generate_rodo_footer(client_data, prospect_domain)` - generującą obowiązkową stopkę informacyjną dla kampanii cold mailowych (uzasadniony interes prawny).
2. `anonymize_lead(session, lead_id)` - funkcję realizującą "prawo do zapomnienia", która fizycznie usuwa dane osobowe z bazy i hashuje adres e-mail.
Zintegruj `generate_rodo_footer` z końcowym procesem formowania wiadomości HTML w `writer.py`.

### Krok 3: Monolit Funkcjonalności i Silnik Asynchroniczny
Przejrzyj cały `main.py`. Wprowadź:
- Blokadę wysyłki (opt-out list z bazy danych), sprawdzaną na najwcześniejszym etapie, przed wywołaniem narzędzia wysyłającego.
- Przebuduj kolosalną funkcję `run_client_cycle` na mniejsze, atomowe, prywatne asynchroniczne funkcje (np. `_handle_drafts`, `_handle_research`). Zadbaj o bezpieczną obsługę kolejek Redis i rate limitów.

### Krok 4: Utrzymanie GUI w WebStacku
Skup się na plikach w folderze `gui` (Streamlit). Upewnij się, że kod nie ma żadnych zaszłości związanych z aplikacjami desktopowymi (PySide6/Qt). Oczyść dashboard z wycieków wrażliwych danych (np. kluczy z .env) na ekran i zoptymalizuj widoki.

Rozpocznij analizę od Kroku 1 i zaproponuj kod.