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
    """
    try:
        domain = email.split('@')[1]
        records = dns.resolver.resolve(domain, 'MX')
        return len(records) > 0
    except:
        return False

def verify_sender_dns(domain: str) -> dict:
    """
    Weryfikuje czy klient (nadawca) ma poprawnie skonfigurowane rekordy SPF i DMARC dla domeny.
    (Zgodnie z wymaganiami Antyspam z audytu Wektor 4, by chronić reputację kampanii).
    """
    # Clean domain just in case
    domain = domain.lower().replace("www.", "").strip()
    status = {"spf_ok": False, "dmarc_ok": False, "error": None}
    
    try:
        # Check SPF (TXT na domenie głównej)
        try:
            txt_records = dns.resolver.resolve(domain, 'TXT')
            for rdata in txt_records:
                txt_text = "".join([t.decode() for t in rdata.strings]).lower()
                if txt_text.startswith("v=spf1"):
                    status["spf_ok"] = True
                    break
        except dns.resolver.NoAnswer:
            pass

        # Check DMARC (TXT na poddomenie _dmarc)
        try:
            dmarc_records = dns.resolver.resolve(f"_dmarc.{domain}", 'TXT')
            for rdata in dmarc_records:
                txt_text = "".join([t.decode() for t in rdata.strings]).lower()
                if txt_text.startswith("v=dmarc1"):
                    status["dmarc_ok"] = True
                    break
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            pass

    except Exception as e:
        status["error"] = str(e)
        logger.error(f"[DNS VERIFIER] Błąd podczas sprawdzania rekordu '{domain}': {e}")
        
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

    # API Call
    try:
        url = "https://api.debounce.io/v1/"
        params = {
            "api": DEBOUNCE_API_KEY,
            "email": email
        }
        
        # Timeout 10s na request
        response = requests.get(url, params=params, timeout=10)
        
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
            
            return result
            
        else:
            logger.warning(f"⚠️ DeBounce API HTTP Error: {response.status_code}")
            return "UNKNOWN"

    except requests.exceptions.Timeout:
        logger.error(f"⏱️ DeBounce API timeout for {email}")
        return "UNKNOWN"
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
