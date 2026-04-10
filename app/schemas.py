from typing import List, Optional
from pydantic import BaseModel, Field

class SearchQuery(BaseModel):
    """Pojedyncze zapytanie wyszukiwania z wyborem źródła danych."""
    query: str = Field(description="Precyzyjne zapytanie do wyszukiwarki. Np. 'Przychodnia near Zamość', 'Software House Kraków'.")
    source: str = Field(
        default="maps",
        description="Źródło danych: 'maps' (Google Maps — firmy lokalne z adresem) lub 'search' (Google Search — firmy online, SaaS, agencje). "
                    "Użyj 'maps' dla firm z fizyczną lokalizacją (kliniki, biura, sklepy). "
                    "Użyj 'search' dla firm czysto online (SaaS, startup, e-commerce, agencje bez biura)."
    )

class StrategyOutput(BaseModel):
    """Struktura wyjściowa Agenta Strategicznego"""
    
    thinking_process: str = Field(
        description="Krótkie uzasadnienie strategii. Dlaczego wybrałeś te słowa kluczowe?"
    )
    
    search_queries: List[SearchQuery] = Field(
        description="Lista 5-10 precyzyjnych zapytań z wyborem źródła (maps/search). Każde zapytanie musi mieć inną LOKALIZACJĘ lub inną BRANŻĘ."
    )
    
    target_locations: List[str] = Field(
        description="Lista miast lub regionów, na których należy się skupić, jeśli dotyczy."
    )

class CompanyResearch(BaseModel):
    """Wynik analizy strony WWW firmy (Titan Enterprise Edition)"""
    
    data_currency_analysis: str = Field(
        description="Analiza aktualności danych na stronie. Przed zebraniem jakichkolwiek faktów zbadaj copyright w stopce, "
                    "daty najnowszych aktualności, postów lub wpisów na blogu. Oceń, czy domena jest wciąż żywa i aktualizowana "
                    "w bieżącym roku. Jeśli firma wygląda na 'martwą' (np. ostatnie newsy z przed 2 lat), wyraźnie to zaznacz."
    )
    
    company_name: str = Field(description="Oficjalna nazwa firmy zidentyfikowana na stronie.")
    
    summary: str = Field(
        description="Krótkie, menedżerskie podsumowanie co firma robi (max 2 zdania). Skup się na modelu biznesowym."
    )
    
    target_audience: str = Field(
        description="Kto jest ich idealnym klientem (ICP)? Np. 'e-commerce', 'banki', 'małe firmy budowlane'."
    )
    
    key_products: List[str] = Field(
        description="Główne produkty lub usługi oferowane przez firmę."
    )
    
    tech_stack: List[str] = Field(
        description="Wykryte technologie, języki programowania, frameworki (np. Python, React, AWS, HubSpot)."
    )
    
    decision_makers: List[str] = Field(
        description="Lista kluczowych osób w formacie 'Imie Nazwisko (Rola)'. Szukaj: CEO, CTO, Founder, Head of Sales. "
                    "WAŻNE: Pobieraj TYLKO osoby z sekcji Zespół/Team/O nas. NIGDY nie zgaduj. Jeśli nie ma sekcji zespołu — puste."
    )

    verified_contact_name: Optional[str] = Field(
        default=None,
        description="Imię decydenta WYŁĄCZNIE jeśli spełnione SĄ OBA warunki jednocześnie: "
                    "(1) imię znalezione w sekcji Zespół/Team/O nas/About Us, "
                    "(2) na tej samej stronie lub stronie kontakt widnieje email który PASUJE do tej osoby (imię.nazwisko@ lub pierwsza litera+nazwisko@). "
                    "Jeśli choć jeden warunek nie jest spełniony — zostaw NULL. "
                    "Wpisuj TYLKO imię (np. 'Renata'), nigdy nazwisko ani rolę."
    )

    contact_emails: List[str] = Field(
        description="Lista adresów email znalezionych na stronie (np. contact@..., hello@..., sales@...)."
    )
    
    hiring_signals: List[str] = Field(
        description="Kogo aktualnie zatrudniają? (np. 'Szukają Senior Python Dev', 'Rekrutują Sales Managera'). "
                    "To kluczowy sygnał o budżecie i potrzebach."
    )
    
    icebreaker: str = Field(
        description="MOST między obserwacją na stronie a ofertą nadawcy. "
                    "To NIE JEST 'najciekawszy fakt'. To fakt NAJBARDZIEJ POWIĄZANY z tym co nadawca oferuje. "
                    "Schemat: (1) obserwacja ze strony (2) jak łączy się z ofertą nadawcy (3) gotowe zdanie. "
                    "OPARTE WYŁĄCZNIE NA AKTUALNYCH DANYCH. Bezwzględny zakaz starych programów/dotacji. "
                    "Jeśli ŻADEN fakt nie wiąże się z ofertą nadawcy → wpisz 'Brak'."
    )
    
    pain_points_or_opportunities: List[str] = Field(
        description="2-3 punkty zaczepienia do sprzedaży. Np. 'Szukają handlowców (potrzeba leadów)', "
                    "'Mają przestarzałą stronę (potrzeba redesignu)'."
    )

    critical_business_signals: List[str] = Field(
        default_factory=list,
        description="SYGNAŁY KRYTYCZNE ze strony, które mogą wpłynąć na decyzję o kontakcie. "
                    "Np. 'Wstrzymanie zapisów nowych pacjentów', 'Firma w likwidacji', "
                    "'Zawieszenie działalności', 'Brak kontraktu NFZ'. "
                    "Jeśli brak takich sygnałów → pusta lista."
    )

class EmailDraft(BaseModel):
    """Wygenerowany Draft Maila"""
    subject: str = Field(description="Temat wiadomości (krótki, intrygujący, max 5-7 słów).")
    body: str = Field(description="Treść maila w formacie HTML (używaj <p>, <b>, <br>).")
    rationale: str = Field(description="Dlaczego napisałeś to w ten sposób? Wyjaśnij strategię.")

class AuditResult(BaseModel):
    """Wynik kontroli jakości (Hallucination Killer)"""
    passed: bool = Field(description="Czy mail przeszedł test prawdy? True/False")
    feedback: str = Field(description="Jeśli False - co trzeba poprawić? Jeśli True - wpisz 'OK'.")
    hallucinations_detected: List[str] = Field(description="Lista faktów, które nie zgadzają się z danymi firmy.")

class ReplyAnalysis(BaseModel):
    """Analiza odpowiedzi od klienta"""
    is_interested: bool = Field(description="Czy klient wyraża chęć rozmowy/współpracy?")
    sentiment: str = Field(description="POSITIVE, NEGATIVE, lub NEUTRAL")
    summary: str = Field(description="Jednozdaniowe streszczenie intencji klienta.")
    suggested_action: str = Field(description="Co powinien zrobić człowiek? Np. 'Wyślij Calendly', 'Odpuść', 'Odpowiedz na pytanie X'.")