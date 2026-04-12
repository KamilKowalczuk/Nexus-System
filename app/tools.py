# app/tools.py
"""
TOOLS - Utility Functions
NOW WITH: Redis cache for email verification (save $350/mc!)
"""

import os
import re
import logging
import dns.resolver
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv
from app.cache_manager import cache_manager
from app import critical_monitor

load_dotenv()
logger = logging.getLogger("tools")

# API CONFIG
DEBOUNCE_API_KEY = os.getenv("DEBOUNCE_API_KEY")


def normalize_domain(url: str) -> str:
    """Czyści URL do samej domeny."""
    if not url: return ""
    if not url.startswith(("http://", "https://")): url = "http://" + url
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        if domain.startswith("www."): domain = domain[4:]
        return domain.lower()
    except: return ""


def clean_text(text: str) -> str:
    """Usuwa nadmiarowe spacje."""
    if not text: return ""
    return re.sub(r'\s+', ' ', text).strip()


def get_main_domain_url(url: str) -> str:
    """Zwraca czysty URL strony głównej."""
    if not url: return ""
    if not url.startswith(("http://", "https://")): url = "https://" + url
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    except:
        return url


def verify_email_mx(email: str) -> bool:
    """
    Szybka, darmowa weryfikacja DNS/MX.
    Fail-open - jeśli DNS ma czkawkę, przepuszczamy (DeBounce wyłapie).
    """
    try:
        domain = email.split('@')[1]
        res = dns.resolver.Resolver()
        res.nameservers = ['8.8.8.8', '1.1.1.1']
        res.lifetime = 5.0
        records = res.resolve(domain, 'MX')
        return len(records) > 0
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        return False
    except Exception:
        # Timeout lokalnego resolvowania
        return True

def verify_sender_dns(domain: str) -> dict:
    """
    Weryfikuje czy klient (nadawca) ma poprawnie skonfigurowane rekordy SPF i DMARC dla domeny.
    (Zgodnie z wymaganiami Antyspam z audytu Wektor 4, by chronić reputację kampanii).
    """
    # Clean domain just in case
    domain = domain.lower().replace("www.", "").strip()
    status = {"spf_ok": False, "dmarc_ok": False, "error": None}
    
    # Custom robust DNS resolver to avoid 127.0.0.53 timeouts
    res = dns.resolver.Resolver()
    res.nameservers = ['8.8.8.8', '1.1.1.1']
    res.lifetime = 10.0
    res.timeout = 5.0
    
    try:
        # Check SPF (TXT na domenie głównej)
        try:
            txt_records = res.resolve(domain, 'TXT')
            for rdata in txt_records:
                txt_text = "".join([t.decode() for t in rdata.strings]).lower()
                if txt_text.startswith("v=spf1"):
                    status["spf_ok"] = True
                    break
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            pass

        # Check DMARC (TXT na poddomenie _dmarc)
        try:
            dmarc_records = res.resolve(f"_dmarc.{domain}", 'TXT')
            for rdata in dmarc_records:
                txt_text = "".join([t.decode() for t in rdata.strings]).lower()
                if txt_text.startswith("v=dmarc1"):
                    status["dmarc_ok"] = True
                    break
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            pass

    except Exception as e:
        status["error"] = str(e)
        # Błąd resolvera (np. timeout) nie powinien blokować sprzedaży
        status["spf_ok"] = True
        status["dmarc_ok"] = True
        logger.error(f"[DNS VERIFIER] Sieciowy błąd podczas sprawdzania rekordu '{domain}': {e} -> FAIL-OPEN (przepuszczam)")
        
    return status


def verify_email_deep(email: str) -> str:
    """
    ENTERPRISE VERIFICATION z Redis Cache.
    
    Flow:
    1. Check Redis cache (70% hit rate)
    2. If cached → return instantly (<1ms) ✨ SAVE MONEY
    3. If not cached → call DeBounce API → cache result → return
    
    Cache TTL: 7 days (emails don't change validity often)
    
    Returns:
        "OK", "RISKY", "INVALID", "UNKNOWN"
    """
    
    # ==========================================
    # STEP 1: CHECK REDIS CACHE
    # ==========================================
    cached = cache_manager.get_email_verification(email)
    if cached:
        result = cached.get("result", "UNKNOWN")
        logger.info(f"⚡ CACHE HIT: {email} → {result} (saved API call!)")
        return result
    
    logger.debug(f"💸 CACHE MISS: {email} → calling DeBounce API")
    
    # ==========================================
    # STEP 2: NO CACHE - CALL API
    # ==========================================
    
    # Fallback: Jeśli brak klucza API, robimy tylko MX check
    if not DEBOUNCE_API_KEY:
        mx_ok = verify_email_mx(email)
        result = "OK" if mx_ok else "INVALID"
        # Don't cache MX-only checks (less reliable)
        return result

    # API Call with RETRY
    max_retries = 2
    for attempt in range(max_retries):
        try:
            url = "https://api.debounce.io/v1/"
            params = {
                "api": DEBOUNCE_API_KEY,
                "email": email
            }
            
            # Timeout 20s (Docker DNS może lagować)
            response = requests.get(url, params=params, timeout=20)
            
            if response.status_code == 200:
                data = response.json()
                
                # Debugowanie w konsoli (widzisz co się dzieje)
                logger.debug(f"🐛 DeBounce API response: {data}")

                # Pobieramy dane z zagnieżdżonego obiektu lub głównego (Hybryda)
                debounce_data = data.get("debounce", data) # Fallback na root jeśli brak 'debounce'
                
                result_text = str(debounce_data.get("result", "")).lower() # np. "safe to send", "risky"
                code = str(debounce_data.get("code", "0"))
                
                # --- LOGIKA BIZNESOWA (AGRESYWNA SPRZEDAŻ) ---
                
                result = "UNKNOWN"  # Default
                
                # 1. PEWNIAKI
                if "safe" in result_text or code == "1":
                    result = "OK"
                
                # 2. RYZYKOWNE (Catch-all, Role, Spamtrap ale oznaczony jako Risky)
                elif "risky" in result_text:
                    result = "RISKY"
                    
                # 3. SPECJALNE PRZYPADKI (Gdy tekst jest niejasny, patrzymy na kody)
                elif code == "5":
                    result = "RISKY"  # Accept All
                elif code == "6":
                    result = "OK"     # Role-Based (Sales/Info)
                
                # 4. TWARDE ODRZUCENIE
                elif "invalid" in result_text or code in ["2", "3", "8"]:
                    result = "INVALID"
                
                # 5. Spamtrap (groźny)
                elif code == "4":
                    result = "INVALID"
                
                # ==========================================
                # STEP 3: CACHE THE RESULT
                # ==========================================
                cache_manager.set_email_verification(email, result, api="debounce")
                logger.info(f"✅ API call: {email} → {result} (cached for 7 days)")
                critical_monitor.record_success("debounce")
                return result

            else:
                status_code = response.status_code
                resp_text = response.text[:300] if response.text else "EMPTY"
                logger.warning(f"⚠️ DeBounce API HTTP Error: {status_code} | Body: {resp_text}")
                if status_code == 402:
                    # Brak kredytów — natychmiastowy stop, nie czekamy na próg
                    critical_monitor.trigger_stop(
                        api_name="debounce",
                        reason="DeBounce API zwróciło HTTP 402 — wyczerpane kredyty. Wysyłka wstrzymana.",
                        consecutive=1,
                    )
                elif status_code in (401, 403):
                    logger.error(f"🔑 DeBounce AUTH ERROR ({status_code}) — sprawdź DEBOUNCE_API_KEY w .env! Klucz musi mieć 13 znaków.")
                else:
                    critical_monitor.record_failure("debounce")
                return "API_DOWN"

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                logger.warning(f"⏱️ DeBounce timeout (próba {attempt+1}/{max_retries}) — retry za 3s...")
                import time
                time.sleep(3)
                continue
            logger.error(f"⏱️ DeBounce API timeout for {email} (po {max_retries} próbach)")
            critical_monitor.record_failure("debounce")
            # Fallback: MX check zamiast blokowania leada
            logger.info(f"🔄 Fallback MX check dla {email}...")
            mx_ok = verify_email_mx(email)
            return "OK" if mx_ok else "INVALID"
        except Exception as e:
            logger.error(f"❌ DeBounce API error for {email}: {e}")
            # Fallback to MX check
            mx_ok = verify_email_mx(email)
            return "OK" if mx_ok else "INVALID"


def clear_email_cache(email: str = None) -> bool:
    """
    UTILITY: Clear email verification cache.
    
    Args:
        email: Specific email to clear (None = clear all)
    
    Returns:
        True if cleared successfully
    """
    if email:
        # Clear specific email (for testing/debugging)
        key = f"email:verified:{cache_manager._hash(email)}"
        success = cache_manager.redis.delete(key)
        if success:
            logger.info(f"🗑️ Cleared cache for {email}")
        return success
    else:
        # This would require scanning all keys (expensive)
        logger.warning("Clearing ALL email cache not implemented (use Redis CLI)")
        return False


def get_email_cache_stats() -> dict:
    """
    UTILITY: Get email cache statistics.
    
    Returns:
        {"total_cached": 1234, "ttl_avg": 345600}
    """
    keys = cache_manager.redis.keys("email:verified:*")
    
    if not keys:
        return {"total_cached": 0}
    
    # Sample TTLs from first 10 keys
    ttls = []
    for key in keys[:10]:
        ttl = cache_manager.redis.ttl(key)
        if ttl > 0:
            ttls.append(ttl)
    
    avg_ttl = sum(ttls) // len(ttls) if ttls else 0
    
    return {
        "total_cached": len(keys),
        "ttl_avg_seconds": avg_ttl,
        "ttl_avg_days": round(avg_ttl / 86400, 1) if avg_ttl > 0 else 0
    }
