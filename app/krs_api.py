import httpx
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger("krs_api")

def _get_krs_from_nip_wl(nip: str) -> Optional[dict]:
    """
    Krok 1: Wyszukiwanie spółki w publicznym Wykazie Podatników VAT (MF) by zdobyć numer KRS i Nazwę.
    Działa bez Auth, wymaga daty z dzisiaj.
    """
    clean_nip = nip.replace("-", "").strip()
    if not clean_nip.isdigit() or len(clean_nip) != 10:
        logger.error(f"[KRS API] NIP {nip} jest nieprawidłowy.")
        return None

    date_str = datetime.today().strftime('%Y-%m-%d')
    url = f"https://wl-api.mf.gov.pl/api/search/nip/{clean_nip}?date={date_str}"
    
    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.get(url)
            if res.status_code == 200:
                data = res.json()
                subject = data.get("result", {}).get("subject")
                if subject:
                    return {
                        "name": subject.get("name"),
                        "nip": subject.get("nip"),
                        "regon": subject.get("regon"),
                        "krs": subject.get("krs"),
                        "address": subject.get("workingAddress") or subject.get("residenceAddress")
                    }
            elif res.status_code == 429:
                logger.error("[KRS API] Rate limit na Wykazie Podatników (WL API).")
            else:
                logger.error(f"[KRS API] Błąd WL API: {res.status_code}")
    except Exception as e:
        logger.error(f"[KRS API] Wyjątek połączenia WL API: {e}")
    
    return None

def _get_details_from_krs_ms(krs: str) -> Optional[dict]:
    """
    Krok 2: Odpytanie oficjalnego API KRS MS o Sąd Rejonowy i Kapitał Zakładowy.
    """
    if not krs:
        return None
        
    url = f"https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/{krs}?rejestr=P&format=json"
    
    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.get(url)
            if res.status_code == 200:
                data = res.json()
                try:
                    naglowek = data['odpis']['naglowekA']
                    
                    # --- SŁOWNIK SĄDÓW KRS ---
                    court_map = {
                        "LU.VI": "Sąd Rejonowy Lublin-Wschód w Lublinie z siedzibą w Świdniku, VI Wydział Gospodarczy KRS",
                        "WA.XII": "Sąd Rejonowy dla m.st. Warszawy w Warszawie, XII Wydział Gospodarczy KRS",
                        "WA.XIII": "Sąd Rejonowy dla m.st. Warszawy w Warszawie, XIII Wydział Gospodarczy KRS",
                        "WA.XIV": "Sąd Rejonowy dla m.st. Warszawy w Warszawie, XIV Wydział Gospodarczy KRS",
                        "BI.XII": "Sąd Rejonowy w Białymstoku, XII Wydział Gospodarczy KRS",
                        "BB.VIII": "Sąd Rejonowy w Bielsku-Białej, VIII Wydział Gospodarczy KRS",
                        "BY.XIII": "Sąd Rejonowy w Bydgoszczy, XIII Wydział Gospodarczy KRS",
                        "CZ.XVII": "Sąd Rejonowy w Częstochowie, XVII Wydział Gospodarczy KRS",
                        "GD.VII": "Sąd Rejonowy Gdańsk-Północ w Gdańsku, VII Wydział Gospodarczy KRS",
                        "GD.VIII": "Sąd Rejonowy Gdańsk-Północ w Gdańsku, VIII Wydział Gospodarczy KRS",
                        "GL.X": "Sąd Rejonowy w Gliwicach, X Wydział Gospodarczy KRS",
                        "KA.VIII": "Sąd Rejonowy Katowice-Wschód w Katowicach, VIII Wydział Gospodarczy KRS",
                        "KI.X": "Sąd Rejonowy w Kielcech, X Wydział Gospodarczy KRS",
                        "KO.IX": "Sąd Rejonowy w Koszalinie, IX Wydział Gospodarczy KRS",
                        "KR.XI": "Sąd Rejonowy dla Krakowa-Śródmieścia w Krakowie, XI Wydział Gospodarczy KRS",
                        "KR.XII": "Sąd Rejonowy dla Krakowa-Śródmieścia w Krakowie, XII Wydział Gospodarczy KRS",
                        "LD.XX": "Sąd Rejonowy dla Łodzi Śródmieścia w Łodzi, XX Wydział Gospodarczy KRS",
                        "OL.VIII": "Sąd Rejonowy w Olsztynie, VIII Wydział Gospodarczy KRS",
                        "OP.VIII": "Sąd Rejonowy w Opolu, VIII Wydział Gospodarczy KRS",
                        "PO.VIII": "Sąd Rejonowy Poznań - Nowe Miasto i Wilda w Poznaniu, VIII Wydział Gospodarczy KRS",
                        "PO.IX": "Sąd Rejonowy Poznań - Nowe Miasto i Wilda w Poznaniu, IX Wydział Gospodarczy KRS",
                        "RZ.XII": "Sąd Rejonowy w Rzeszowie, XII Wydział Gospodarczy KRS",
                        "SZ.XIII": "Sąd Rejonowy Szczecin-Centrum w Szczecinie, XIII Wydział Gospodarczy KRS",
                        "TO.VII": "Sąd Rejonowy w Toruniu, VII Wydział Gospodarczy KRS",
                        "WR.VI": "Sąd Rejonowy dla Wrocławia Fabrycznej we Wrocławiu, VI Wydział Gospodarczy KRS",
                        "WR.IX": "Sąd Rejonowy dla Wrocławia Fabrycznej we Wrocławiu, IX Wydział Gospodarczy KRS",
                        "ZG.VIII": "Sąd Rejonowy w Zielonej Górze, VIII Wydział Gospodarczy KRS"
                    }
                    
                    sygnatura = naglowek.get('sygnaturaAktSprawyDotyczacejOstatniegoWpisu', '')
                    sad_oficjalny = naglowek.get('oznaczenieSaduDokonujacegoOstatniegoWpisu', '')
                    
                    sad = "Brak danych Sądu Rejonowego"
                    
                    # 1. Próba odszyfrowania z sygnatury (najdokładniejsze)
                    prefixmatch = False
                    for prefix, full_name in court_map.items():
                        if sygnatura.startswith(prefix):
                            sad = full_name
                            prefixmatch = True
                            break
                            
                    # 2. Jeśli się nie udało z prefiksu, bierzemy opis z API (jeśli nie jest to "SYSTEM")
                    if not prefixmatch:
                        if sad_oficjalny and sad_oficjalny.upper() != "SYSTEM":
                            # Ładne formatowanie "SĄD REJONOWY..." na "Sąd Rejonowy..."
                            if sad_oficjalny.isupper():
                                sad = sad_oficjalny.title()
                                sad = sad.replace("Wydział", "Wydział").replace("Krs", "KRS")
                            else:
                                sad = sad_oficjalny
                        elif "Sąd" in naglowek.get('sad', ''):
                            sad = naglowek.get('sad')
                    
                    # Kapitał zakładowy (Dział 1)
                    dzial1 = data['odpis']['dane'].get('dzial1', {})
                    kapital_obj = dzial1.get('kapital', {})
                    if isinstance(kapital_obj, list) and len(kapital_obj) > 0:
                        kapital_obj = kapital_obj[0]
                    kapital = kapital_obj.get('wysokoscKapitaluZakladowego', {}).get('wartosc', '0,00')
                    
                    # Pełna firma, adres, organy i identyfikatory
                    dane_podmiotu = dzial1.get('danePodmiotu', {})
                    nazwa = dane_podmiotu.get('nazwa', '')
                    identyfikatory = dane_podmiotu.get('identyfikatory', {})
                    nip = identyfikatory.get('nip', '')
                    regon_raw = identyfikatory.get('regon', '')
                    # REGON: standardowe 9 znaków (KRS zwraca 14-znakowy z zerami na końcu)
                    regon = regon_raw[:9] if len(regon_raw) > 9 else regon_raw
                    
                    siedziba = dzial1.get('siedzibaIAdres', {}).get('adres', {})
                    adres = "Brak adresu"
                    if siedziba:
                        ulica = siedziba.get('ulica', '')
                        nr_domu = siedziba.get('nrDomu', '')
                        nr_lokalu = siedziba.get('nrLokalu', '')
                        kod = siedziba.get('kodPocztowy', '')
                        miasto = siedziba.get('miejscowosc', '')
                        
                        if ulica:
                            adres = f"ul. {ulica} {nr_domu}"
                        elif nr_domu:
                            adres = f"{miasto} {nr_domu}"
                        else:
                            adres = miasto
                        
                        if nr_lokalu:
                            adres += f"/{nr_lokalu}"
                        
                        adres = f"{adres}, {kod} {miasto}".strip(", ")
                    
                    return {
                        "sad_rejonowy": sad,
                        "kapital_zakladowy": kapital,
                        "nazwa_krs": nazwa,
                        "nip_krs": nip,
                        "regon_krs": regon,
                        "adres_krs": adres
                    }
                except KeyError as e:
                    logger.error(f"[KRS API] Błąd parsowania payloadu z KRS MS: Brakuje struktury {e}")
            else:
                logger.error(f"[KRS API] Błąd KRS MS: {res.status_code}")
    except Exception as e:
        logger.error(f"[KRS API] Wyjątek połączenia KRS MS: {e}")
        
    return None

def generate_full_legal_footer(nip_or_krs: str) -> Dict[str, str]:
    """
    Funkcja orkiestrator. Kombinuje dane z obu rządowych API w jeden pełny pakiet dla KSH.
    Zwraca słownik ułatwiający formatowanie HTML.
    Jeśli wprowadzono KRS zamiast NIP (lub firma nie widnieje na WL), próbuje wyciągnąć co się da z KRS MS.
    """
    input_val = nip_or_krs.replace("-", "").strip()
    result = {
        "success": False,
        "name": "", "nip": "", "regon": "", "krs": "", "address": "",
        "sad_rejonowy": "", "kapital_zakladowy": "", "error_message": ""
    }
    
    basic_data = _get_krs_from_nip_wl(input_val)
    
    # Fallback jeśli WL nic nie znajdzie (np. firma medyczna zwolniona z VAT) lub podano bezpośrednio KRS
    if not basic_data:
        if input_val.startswith("0") and len(input_val) == 10:
            logger.info("[KRS API] WL zwróciło None. Traktuję wpis jako bezpośredni nr KRS.")
            result["krs"] = input_val
        else:
            logger.info("[KRS API] Próbuje użyć wartości jako KRS pomimo, że nie zaczyna się od '0'.")
            result["krs"] = input_val
    else:
        result.update(basic_data)
        
    # Pobierz Dział 1 z MS
    if result.get("krs"):
        advanced_data = _get_details_from_krs_ms(result["krs"])
        if advanced_data:
            # Uzupełnij luki w podstawowych danych, jeśli WL API zawiodło
            if not result.get("name") and advanced_data.get("nazwa_krs"):
                result["name"] = advanced_data["nazwa_krs"].title()
            if not result.get("nip") and advanced_data.get("nip_krs"):
                result["nip"] = advanced_data["nip_krs"]
            if not result.get("regon") and advanced_data.get("regon_krs"):
                result["regon"] = advanced_data["regon_krs"]
            if not result.get("address") and advanced_data.get("adres_krs"):
                result["address"] = advanced_data["adres_krs"]
            
            result["sad_rejonowy"] = advanced_data.get("sad_rejonowy", "Brak danych")
            result["kapital_zakladowy"] = advanced_data.get("kapital_zakladowy", "Brak")
            result["success"] = True
        else:
            result["error_message"] = "Nie znaleziono firmy po nr NIP w Wykazie (Biała Lista) ani w bazie KRS po podanym numerze."
            result["success"] = False
    else:
        result["error_message"] = "Firma widnieje w Wykazie Podatników, ale nie ma przypisanego numeru KRS (Prawdopodobnie JDG lub s.c.). Stopka spółki prawa handlowego może być niedostępna."
        
    return result
