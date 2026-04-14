# NEXUS TEACHER ENGINE - CORE ARCHITECTURE & ALGORITHMIC SPECIFICATION

## 1. WIZJA I CEL BIZNESOWY (THE "WHY")
Budujemy system **Dynamic AI Alignment** oparty na mechanizmie **RLHF (Reinforcement Learning from Human Feedback)** oraz **Contrastive Prompting**. 
Nasz system agentowy (Researcher + Writer) ma tendencję do "dryfowania" i powtarzania błędów. Zamiast ręcznie edytować prompty w kodzie dla każdej branży, tworzymy "Nauczyciela" (Teacher Agent). 
Nauczyciel asynchronicznie analizuje oceny człowieka (1-5 gwiazdek + komentarze), syntetyzuje je i generuje skondensowaną "Księgę Zasad" (`ClientAlignment`) dla danego klienta. Agenty wykonawcze wstrzykują tę księgę do swoich promptów przed wykonaniem zadania.

## 2. ALGORYTMIKA NAUCZYCIELA (THE SYNTHESIS ENGINE)
Nauczyciel (`app/agents/teacher.py`) NIE JEST prostym skryptem przepisującym komentarze. To zaawansowany LLM, który wykonuje **Algorytm Syntezy Wiedzy**.

Kiedy Nauczyciel zostaje uruchomiony, wykonuje następujące kroki:

### Krok A: Ingestion (Pobranie Kontekstu)
1. Pobiera aktualny `ClientAlignment` (obecne reguły).
2. Pobiera listę nieprzetworzonych `LeadFeedback` (gdzie `is_processed=False`).
3. Rozdziela feedback na dwie ścieżki: `Research_Feedback` i `Writer_Feedback`.

### Krok B: Conflict Resolution & Synthesis (Rozwiązywanie Konfliktów)
Prompt Nauczyciela musi instruować go, jak łączyć stare reguły z nowymi:
- **Deduplikacja:** Jeśli człowiek 3 razy napisał "nie pisz o NFZ", Nauczyciel tworzy jedną, absolutną regułę, a nie trzy osobne zdania.
- **Nadpisywanie:** Jeśli nowa uwaga przeczy starej regule, NOWSZA uwaga (z bieżącego batcha) wygrywa.
- **Kondensacja:** Nauczyciel musi zamienić długie żale człowieka (np. "Znowu ten głupi bot napisał o współpracy, a przecież mówiłem, żeby tak nie robić, to brzmi jak sprzedaż") na dyrektywę systemową (np. `[ZAKAZ]: Bezwzględny zakaz używania słów "współpraca", "oferta" - traktowane jako spam handlowy`).

### Krok C: Contrastive Extraction (Uczenie przez Kontrast)
Nauczyciel analizuje oceny z tabeli `LeadFeedback`:
- **Złoty Standard (Ocena 5):** Nauczyciel bierze `corrected_body` (lub wygenerowany tekst, jeśli nie był poprawiany) i zapisuje w `gold_examples["positive"]`.
- **Czarna Lista (Ocena 1-2):** Nauczyciel bierze tragiczny tekst, zapisuje go w `gold_examples["negative"]` **ORAZ dopisuje jedno zdanie wyjaśnienia**, dlaczego ten tekst jest zły (na podstawie komentarza człowieka).

## 3. LOGIKA WYZWALACZA (BATCH PROCESSING) w `main.py`
Nie możemy uruchamiać Nauczyciela po każdej pojedynczej ocenie, bo przepalimy tokeny i wywołamy chaos (Race Conditions). Stosujemy **30-minutowy Debouncing**.

**Algorytm w `nexus_core_loop`:**
1. Sprawdź, czy są rekordy w `lead_feedback` z `is_processed == False`.
2. Znajdź najnowszą datę `updated_at` wśród tych rekordów.
3. Jeśli `NOW() - max(updated_at) > 30 minut` -> Uruchom `teacher.py`.
4. Po udanej syntezie, oznacz te rekordy jako `is_processed = True`.

## 4. INTEGRACJA Z AGENTAMI (PROMPT INJECTION)
Gdy `app/agents/writer.py` lub `app/agents/researcher.py` rozpoczynają pracę, wykonują:

```python
alignment = session.query(ClientAlignment).filter_by(client_id=client.id).first()
if alignment:
    injected_knowledge = f"""
    === 🧠 DYNAMICZNA WIEDZA I ZASADY KLIENTA (BEZWZGLĘDNY PRIORYTET) ===
    {alignment.writing_guidelines} # dla writera
    
    === UCZ SIĘ PRZEZ KONTRAST ===
    ✅ IDEALNY WZÓR:
    {alignment.gold_examples.get("positive", ["Brak"])[0]}
    
    ❌ ZAKAZANY WZÓR (CZEGO UNIKAĆ):
    {alignment.gold_examples.get("negative", [{"text": "Brak", "reason": ""}])[0]}
    """
    # Dodaj injected_knowledge do SystemMessage


## 1. ZMIANY W BAZIE DANYCH (`app/database.py`)
Należy dodać dwie tabele obsługujące feedback i skonsolidowaną wiedzę.

```python
# Tabela feedbacku dla każdego leada
class LeadFeedback(Base):
    __tablename__ = "lead_feedback"
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), unique=True, nullable=False)
    
    # Oceny (gwiazdki)
    researcher_rating = Column(Integer, nullable=True) # 1-5
    writer_rating = Column(Integer, nullable=True)     # 1-5
    
    # Komentarze
    researcher_comments = Column(Text, nullable=True)
    writer_comments = Column(Text, nullable=True)
    
    # Do logiki 30-minutowego opóźnienia
    updated_at = Column(DateTime, default=_now_pl, onupdate=_now_pl)
    is_processed = Column(Boolean, default=False)

# Tabela Master Rulebook dla Klienta (wynik pracy Nauczyciela)
class ClientAlignment(Base):
    __tablename__ = "client_alignments"
    client_id = Column(Integer, ForeignKey("clients.id"), primary_key=True)
    
    # Skondensowane instrukcje
    research_guidelines = Column(Text, nullable=True)
    writing_guidelines = Column(Text, nullable=True)
    
    # Złote i czarne przykłady (Contrastive Learning)
    gold_examples = Column(JSONB, default={"positive": [], "negative": []})
    
    last_updated = Column(DateTime, default=_now_pl)


Zaktualizuj app/database.py o nowe modele.

Stwórz app/agents/teacher.py z wykorzystaniem create_structured_llm.

Zaimplementuj funkcję run_teacher_loop, która pobiera feedbacki, syntetyzuje je i aktualizuje ClientAlignment.

Dodaj do main.py wywołanie check_and_run_teacher w pętli nexus_core_loop.