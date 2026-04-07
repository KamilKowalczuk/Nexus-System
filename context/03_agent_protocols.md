# 03. AGENT DESIGN PROTOCOLS

## 1. Zero-Hallucination Policy
- Agenci muszą bazować WYŁĄCZNIE na danych dostarczonych w promptach (kontekście ze scrapingu).
- Jeżeli danych brakuje - agent LLM ma pominąć dany fragment (np. pominąć imię w mailu, jeśli go nie znamy), zamiast zmyślać (np. wstawiając [Imię]).
- Mechanizm `Auditor` w `writer.py` jest kluczowy. Zawsze utrzymuj funkcjonalność testującą output pod kątem halucynacji przed zapisem do bazy.

## 2. Token Economy & Prompt Engineering
- Prompt musi być krótki, bezpośredni i strukturalny. 
- Nie grzecznościuj (np. nie dodawaj "Proszę, czy mógłbyś"). Instrukcje mają formę dyrektyw.
- Dla wyjść strukturalnych zawsze używaj `.with_structured_output(PydanticModel)` z Langchain.
- Kontekst wrzucany do LLM (np. surowy Markdown z Firecrawl) musi być ucinany, aby nie wyczerpać limitów tokenów (np. `content_md[:70000]`).

## 3. Resilience in LLM calls
- Każde wywołanie `.invoke()` z LLM musi być zabezpieczone blokiem `try...except`, ponieważ API Google może zwrócić błąd (timeout, safety limits, 503).
- Implementuj mechanizmy fallback (jak w `researcher.py` - spadek do czystego regexu, jeśli LLM zawiedzie).