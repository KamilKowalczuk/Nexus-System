Wektor 1: Architektura RODO i Izolacja Danych (Tarcza przed UODO)

    Kryptograficzne Prawo do Zapomnienia (Art. 17 RODO): Moduł anonimizujący trwale nadpisuje dane osobowe w tabeli leads (imię, nazwisko, plain-text email).

    Zasolona Blacklista (Tenant Isolation): Tabela opt_outs przechowuje wyłącznie kryptograficzne hashe (SHA-256 + zmienna środowiskowa SALT) dla adresów e-mail oraz domen. Zero danych jawnych.

    Precyzyjny Obowiązek Informacyjny (Art. 14 RODO): Klauzula systemowa wprost wymienia kategorie pozyskanych danych (np. imię, nazwisko, stanowisko, e-mail) oraz wskazuje cel (uzasadniony interes – Art. 6 ust. 1 lit. f).

    Rejestr RKCP i DPIA: Gotowa wewnętrzna dokumentacja: Rejestr Kategorii Czynności Przetwarzania oraz Ocena Skutków dla Ochrony Danych, w 100% spójna z kodem źródłowym.


Wektor 2: Prawo Telekomunikacyjne i UŚUDE (Tarcza przed UOKiK i UKE)

    Kwarantanna Lingwistyczna AI: Prompt generujący wiadomości B2B ma bezwzględny zakaz używania języka sprzedażowego, cenników i sformułowań typu "oferujemy". Wiadomość musi mieć architekturę analitycznego pytania badającego grunt.

    Bramka B2B Only: System ignoruje lub odrzuca domeny typu freemail (@gmail.com, @wp.pl, @yahoo.com). Wysyłka odbywa się wyłącznie w zamkniętym ekosystemie Business-to-Business.

    Hermetyczny Mechanizm Opt-Out: Każda wiadomość zawiera jasną instrukcję rezygnacji (np. "odpowiedz Wypisz" lub link). Odpowiedź jest parsowana przez Agenta Inbox, który automatycznie triggeruje kryptograficzną anonimizację w bazie.


Wektor 3: Infrastruktura i Cyberbezpieczeństwo (Ochrona przed wyciekiem)

    GCP KMS (Key Management Service): Hasła SMTP w tabeli clients są szyfrowane at rest. Deszyfracja następuje wyłącznie w pamięci RAM wewnątrz bloku with smtplib... i zmienna jest natychmiast usuwana (del password) po uwierzytelnieniu sesji.

    Ścisła Izolacja Zapytań (Row-Level Security / ORM): Każde zapytanie do bazy (np. generowanie draftów, wysyłka, statystyki) bezwzględnie filtruje rekordy po client_id lub weryfikuje własność campaign_id.

    Ochrona przed API Abuse (Rate Limiting): Restrykcyjne limity na endpointach zabezpieczają przed atakami siłowymi i wyczerpaniem limitów zapytań do AI / Firecrawl.

Wektor 4: Reputacja Domen i Algorytmy Antyspamowe (Google / Microsoft EOP)

    Zgodność Warstw MIME: Struktura generowanego maila posiada identyczną warstwę informacyjną w formacie text/plain oraz text/html.

    Zabezpieczenie przed Hard Bounce: Bezwzględna weryfikacja istnienia rekordów MX dla domeny docelowej przed wyzwoleniem akcji SMTP.

    Weryfikacja DNS Nadawcy: Walidator systemowy blokuje start kampanii, dopóki Klient nie ustawi poprawnych rekordów SPF, DKIM oraz DMARC na swojej domenie.

    Algorytm Rozgrzewkowy i Dławik (Throttle): Zaimplementowane opóźnienia między wysyłkami (np. losowe 60-300 sekund) oraz ścisłe respektowanie limitów dziennych (daily_limit) z funkcją powolnego, liniowego skalowania (warm-up).

    Czystość Ładunku: Brak załączników w pierwszych wiadomościach cold mail.

Wektor 5: Prawo Spółek Handlowych (KSH)

    Zabezpieczenie Stopki: Automatyczna generacja kompletnej stopki biznesowej (NIP, KRS, Sąd Rejonowy, Kapitał Zakładowy, Pełna nazwa) na podstawie integracji z API KRS/REGON, eliminująca ludzki błąd.