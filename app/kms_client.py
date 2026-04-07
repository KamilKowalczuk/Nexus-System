# app/kms_client.py
"""
NEXUS KMS CLIENT — Deszyfrowanie credentiali GCP KMS (Python)

Architektura bezpieczeństwa:
- Szyfrogram (ENCRYPTED:base64...) przechowywany w bazie danych NIGDY nie jest
  odszyfrowany do pliku, logu ani zmiennej trwałej.
- Deszyfrowanie następuje wyłącznie tuż przed użyciem (SMTP connect / IMAP login),
  a wynik żyje wyłącznie w lokalnym zasięgu wywołania (RAM).
- Ten sam Service Account i klucz co w Node.js — jedno źródło prawdy.

Wymagane zmienne środowiskowe (.env):
    GCP_PROJECT_ID, GCP_KMS_LOCATION, GCP_KMS_KEY_RING, GCP_KMS_CRYPTO_KEY,
    GCP_CLIENT_EMAIL, GCP_PRIVATE_KEY
"""

import os
import base64
import logging
from functools import lru_cache

logger = logging.getLogger("nexus_kms")

_ENCRYPTED_PREFIX = "ENCRYPTED:"


def is_encrypted(value: str) -> bool:
    """Zwraca True jeśli wartość jest szyfrogramem KMS (zaczyna się od 'ENCRYPTED:')."""
    return isinstance(value, str) and value.startswith(_ENCRYPTED_PREFIX)


def is_kms_available() -> bool:
    """Sprawdza czy wszystkie zmienne KMS są skonfigurowane."""
    return all([
        os.getenv("GCP_PROJECT_ID"),
        os.getenv("GCP_KMS_KEY_RING"),
        os.getenv("GCP_KMS_CRYPTO_KEY"),
        os.getenv("GCP_CLIENT_EMAIL"),
        os.getenv("GCP_PRIVATE_KEY"),
    ])


@lru_cache(maxsize=1)
def _get_key_name() -> str:
    """Zwraca pełną ścieżkę klucza KMS (buforowane — stała konfiguracja)."""
    project = os.environ["GCP_PROJECT_ID"]
    location = os.getenv("GCP_KMS_LOCATION", "global")
    key_ring = os.environ["GCP_KMS_KEY_RING"]
    crypto_key = os.environ["GCP_KMS_CRYPTO_KEY"]
    
    # Obsługa jeśli klucz zawiera już informację o wersji (backward compat)
    if "cryptoKeyVersions" in crypto_key:
        return f"projects/{project}/locations/{location}/keyRings/{key_ring}/{crypto_key}"
    
    return f"projects/{project}/locations/{location}/keyRings/{key_ring}/cryptoKeys/{crypto_key}"


def _build_kms_client():
    """
    Tworzy klienta KMS z credentialami Service Account z env vars.

    WAŻNE: Używamy REST transport zamiast domyślnego gRPC.
    grpcio inicjalizowany w wątku roboczym (asyncio.to_thread) powoduje SIGSEGV
    z powodu ograniczeń biblioteki C. REST transport działa bezpiecznie w każdym wątku.
    """
    from google.cloud import kms
    from google.oauth2 import service_account
    import re
    import textwrap

    # 1. Pobierz klucz z env, podmień ew. dosłowne \n na nową linię, usuń ewentualne cudzysłowy.
    pk = os.environ["GCP_PRIVATE_KEY"].replace('"', "").replace("\\n", "\n")

    # 2. Jeśli klucz jest podany wpłasko (brak faktycznych znaków nowej linii), napraw strukturę PEM
    if "-----BEGIN" in pk and "\n" not in pk:
        b64_data = re.sub(r"-----.*?-----", "", pk).replace(" ", "")
        lines = ["-----BEGIN PRIVATE KEY-----"]
        lines.extend(textwrap.wrap(b64_data, 64))
        lines.append("-----END PRIVATE KEY-----")
        pk = "\n".join(lines)

    credentials = service_account.Credentials.from_service_account_info(
        {
            "type": "service_account",
            "project_id": os.environ["GCP_PROJECT_ID"],
            "client_email": os.environ["GCP_CLIENT_EMAIL"],
            "private_key": pk,
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        scopes=["https://www.googleapis.com/auth/cloudkms"],
    )

    # REST transport: bezpieczne w wątkach, brak grpcio (który segfaultuje w non-main thread)
    return kms.KeyManagementServiceClient(
        credentials=credentials,
        transport="rest",
    )


def encrypt_credential(plain_value: str) -> str:
    """
    Szyfruje plain-text credentiale przez GCP KMS.

    BEZPIECZEŃSTWO:
    - Jeśli wartość jest już szyfrogramem (ma prefiks ENCRYPTED:), zwraca bez zmian.
    - Jeśli KMS jest niedostępny (brak konfiguracji), zwraca plain-text i loguje ostrzeżenie.
    - Wynik jest zawsze w formacie 'ENCRYPTED:<base64>' gdy KMS dostępny.

    Args:
        plain_value: Hasło lub inny sekret w plain-text.

    Returns:
        Szyfrogram 'ENCRYPTED:<base64>' lub plain-text jeśli KMS niedostępny.
    """
    if not plain_value:
        return plain_value

    if is_encrypted(plain_value):
        return plain_value  # Już zaszyfrowane — nie szyfruj ponownie

    if not is_kms_available():
        logger.warning(
            "[KMS] Brak konfiguracji GCP KMS — hasło zapisane jako plain-text. "
            "Skonfiguruj GCP_PROJECT_ID, GCP_KMS_KEY_RING, GCP_KMS_CRYPTO_KEY, "
            "GCP_CLIENT_EMAIL, GCP_PRIVATE_KEY."
        )
        return plain_value

    try:
        kms_client = _build_kms_client()
        key_name = _get_key_name()

        response = kms_client.encrypt(
            request={
                "name": key_name,
                "plaintext": plain_value.encode("utf-8"),
            }
        )

        ciphertext_b64 = base64.b64encode(response.ciphertext).decode("utf-8")
        return f"{_ENCRYPTED_PREFIX}{ciphertext_b64}"

    except Exception as e:
        logger.error("[KMS] Błąd szyfrowania credentiali: %s", type(e).__name__)
        raise RuntimeError(f"[KMS] Szyfrowanie nie powiodło się: {e}") from e


def decrypt_credential(encrypted_value: str) -> str:
    """
    Deszyfruje wartość zaszyfrowaną przez GCP KMS.

    BEZPIECZEŃSTWO:
    - Wynik (plain-text) NIGDY nie jest logowany ani przechowywany.
    - Caller odpowiada za natychmiastowe użycie i nie trzymanie referencji.
    - Jeśli wartość nie jest szyfrogramem KMS (brak prefiksu), zwraca ją bez zmian
      (obsługa legacy / środowisk testowych bez KMS).

    Args:
        encrypted_value: Szyfrogram w formacie 'ENCRYPTED:<base64>' lub plain-text.

    Returns:
        Odszyfrowany string (plain-text). Nigdy None.

    Raises:
        RuntimeError: Jeśli KMS jest niedostępny, a wartość jest szyfrogramem.
    """
    if not is_encrypted(encrypted_value):
        return encrypted_value  # Plain-text / brak KMS — zwróć as-is

    if not is_kms_available():
        raise RuntimeError(
            "[KMS] Brak konfiguracji GCP KMS. Nie można odszyfrować credentiali. "
            "Sprawdź zmienne: GCP_PROJECT_ID, GCP_KMS_KEY_RING, GCP_KMS_CRYPTO_KEY, "
            "GCP_CLIENT_EMAIL, GCP_PRIVATE_KEY."
        )

    try:
        ciphertext = base64.b64decode(encrypted_value[len(_ENCRYPTED_PREFIX):])
        kms_client = _build_kms_client()
        key_name = _get_key_name()

        response = kms_client.decrypt(
            request={"name": key_name, "ciphertext": ciphertext}
        )

        # Konwersja bytes → str, trim whitespace który KMS czasem dodaje
        plaintext: str = response.plaintext.decode("utf-8").strip()
        return plaintext

    except (ImportError, ModuleNotFoundError):
        raise RuntimeError(
            "[KMS] Biblioteka google-cloud-kms nie jest zainstalowana. "
            "Zainstaluj: uv pip install google-cloud-kms"
        )

    except Exception as e:
        logger.error("[KMS] Błąd deszyfrowania credentiali: %s", type(e).__name__)
        raise RuntimeError(f"[KMS] Deszyfrowanie nie powiodło się: {e}") from e
