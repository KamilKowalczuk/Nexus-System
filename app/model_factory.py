# app/model_factory.py
"""
NEXUS MODEL FACTORY — Centralny punkt tworzenia instancji LLM.

Obsługuje 3 providerów:
  🔵 Google Gemini   (langchain-google-genai)
  🟣 Anthropic Claude (langchain-anthropic)
  🟢 DeepSeek        (langchain-deepseek)

Każdy model ma metadane: opis, wspierane role, provider.
Factory automatycznie dobiera provider na podstawie nazwy modelu
i obsługuje fallback do Gemini przy błędach.
"""

import os
import logging
from typing import Type, Optional
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("nexus_model_factory")

# ---------------------------------------------------------------------------
# API KEYS
# ---------------------------------------------------------------------------

_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
_ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# ---------------------------------------------------------------------------
# DEFAULT FALLBACK
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"

# ---------------------------------------------------------------------------
# MODEL REGISTRY
# ---------------------------------------------------------------------------
# Każdy model: (provider, opis PL, lista ról, czy wspiera structured output)
# role: "scout", "researcher", "writer"

MODEL_REGISTRY: dict[str, dict] = {
    # === GOOGLE GEMINI ===
    "gemini-3.1-pro-preview": {
        "provider": "gemini",
        "description": "🔵 Flagowy Gemini — najlepsza jakość, reasoning, kodowanie",
        "roles": ["scout", "researcher", "writer"],
        "structured_output": True,
    },
    "gemini-3.1-flash-lite-preview": {
        "provider": "gemini",
        "description": "🔵 Ultra szybki i tani — idealny do masowych operacji (default)",
        "roles": ["scout", "researcher", "writer"],
        "structured_output": True,
    },
    "gemini-3-flash-preview": {
        "provider": "gemini",
        "description": "🔵 Balans szybkości i jakości — nowa generacja",
        "roles": ["scout", "researcher", "writer"],
        "structured_output": True,
    },
    "gemini-2.5-pro": {
        "provider": "gemini",
        "description": "🔵 Stabilny — zaawansowane rozumowanie i kodowanie",
        "roles": ["scout", "researcher", "writer"],
        "structured_output": True,
    },
    "gemini-2.5-flash": {
        "provider": "gemini",
        "description": "🔵 Stabilny i szybki — production ready",
        "roles": ["scout", "researcher", "writer"],
        "structured_output": True,
    },
    "gemini-2.5-flash-lite": {
        "provider": "gemini",
        "description": "🔵 Najtańszy stabilny model Google",
        "roles": ["scout", "researcher", "writer"],
        "structured_output": True,
    },
    "gemini-2.0-flash": {
        "provider": "gemini",
        "description": "🔵 Legacy — działa, ale deprecation 06/2026",
        "roles": ["scout", "researcher", "writer"],
        "structured_output": True,
    },

    # === ANTHROPIC CLAUDE ===
    # Uwaga: Anthropic używa krótkich ID (bez daty) dla najnowszych modeli
    "claude-opus-4-6": {
        "provider": "anthropic",
        "description": "🟣 Najnowszy flagship Claude 4.6 — agentic tasks, 1M context",
        "roles": ["scout", "researcher", "writer"],
        "structured_output": True,
    },
    "claude-sonnet-4-6": {
        "provider": "anthropic",
        "description": "🟣 Najnowszy balanced Claude 4.6 — coding king, 1M context",
        "roles": ["scout", "researcher", "writer"],
        "structured_output": True,
    },
    "claude-opus-4": {
        "provider": "anthropic",
        "description": "🟣 Claude Opus 4 — złożone zadania, reasoning, analiza",
        "roles": ["scout", "researcher", "writer"],
        "structured_output": True,
    },
    "claude-sonnet-4": {
        "provider": "anthropic",
        "description": "🟣 Claude Sonnet 4 — świetny balans jakości i szybkości",
        "roles": ["scout", "researcher", "writer"],
        "structured_output": True,
    },
    "claude-sonnet-4-5": {
        "provider": "anthropic",
        "description": "🟣 Claude Sonnet 4.5 — previous gen, sprawdzony i stabilny",
        "roles": ["scout", "researcher", "writer"],
        "structured_output": True,
    },
    "claude-haiku-4-5": {
        "provider": "anthropic",
        "description": "🟣 Claude Haiku 4.5 — najszybszy Claude, tani, masowe operacje",
        "roles": ["scout", "researcher", "writer"],
        "structured_output": True,
    },

    # === DEEPSEEK ===
    "deepseek-chat": {
        "provider": "deepseek",
        "description": "🟢 DeepSeek V3.2 — wszechstronny, tani, structured output ✅",
        "roles": ["scout", "researcher", "writer"],
        "structured_output": True,
    },
    "deepseek-reasoner": {
        "provider": "deepseek",
        "description": "🟢 DeepSeek R1 — deep thinking, BEZ structured output ⚠️",
        "roles": ["writer"],  # ONLY writer — no structured output
        "structured_output": False,
    },
}


# ---------------------------------------------------------------------------
# PROVIDER → KEY MAPPING
# ---------------------------------------------------------------------------

_PROVIDER_KEYS = {
    "gemini": _GEMINI_KEY,
    "anthropic": _ANTHROPIC_KEY,
    "deepseek": _DEEPSEEK_KEY,
}


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def get_available_api_keys() -> dict[str, bool]:
    """Zwraca mapę provider → czy klucz jest skonfigurowany."""
    return {
        "gemini": bool(_GEMINI_KEY),
        "anthropic": bool(_ANTHROPIC_KEY),
        "deepseek": bool(_DEEPSEEK_KEY),
    }


def get_available_models(role: str = "all") -> list[dict]:
    """
    Zwraca listę modeli dostępnych dla danej roli.

    Args:
        role: "scout", "researcher", "writer" lub "all"

    Returns:
        Lista dict z kluczami: model_id, provider, description, available, structured_output
    """
    keys = get_available_api_keys()
    result = []

    for model_id, info in MODEL_REGISTRY.items():
        if role != "all" and role not in info["roles"]:
            continue

        provider = info["provider"]
        result.append({
            "model_id": model_id,
            "provider": provider,
            "description": info["description"],
            "available": keys.get(provider, False),
            "structured_output": info["structured_output"],
        })

    return result


def create_llm(
    model_name: str,
    temperature: float = 0.0,
    **kwargs,
):
    """
    Tworzy instancję LLM na podstawie nazwy modelu.

    Args:
        model_name:   ID modelu z MODEL_REGISTRY (np. "gemini-3.1-flash-lite-preview")
        temperature:  Temperatura generowania
        **kwargs:     Dodatkowe parametry (top_p, top_k, max_tokens itp.)

    Returns:
        Instancja BaseChatModel (ChatGoogleGenerativeAI / ChatAnthropic / ChatDeepSeek)

    Raises:
        ValueError: Jeśli model nieznany lub brak klucza API
    """
    info = MODEL_REGISTRY.get(model_name)
    if not info:
        logger.warning(f"[MODEL_FACTORY] Nieznany model '{model_name}', fallback → {DEFAULT_MODEL}")
        model_name = DEFAULT_MODEL
        info = MODEL_REGISTRY[DEFAULT_MODEL]

    provider = info["provider"]
    api_key = _PROVIDER_KEYS.get(provider)

    if not api_key:
        logger.warning(
            f"[MODEL_FACTORY] Brak klucza API dla '{provider}' (model: {model_name}). "
            f"Fallback → {DEFAULT_MODEL}"
        )
        model_name = DEFAULT_MODEL
        info = MODEL_REGISTRY[DEFAULT_MODEL]
        provider = "gemini"
        api_key = _GEMINI_KEY

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Gemini wspiera top_p i top_k
        extra = {}
        if "top_p" in kwargs:
            extra["top_p"] = kwargs.pop("top_p")
        if "top_k" in kwargs:
            extra["top_k"] = kwargs.pop("top_k")

        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            google_api_key=api_key,
            **extra,
        )

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model_name,
            temperature=temperature,
            anthropic_api_key=api_key,
            max_tokens=4096,
        )

    elif provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(
            model=model_name,
            temperature=temperature,
            api_key=api_key,
        )

    else:
        raise ValueError(f"Nieobsługiwany provider: {provider}")


def create_structured_llm(
    model_name: str,
    schema: Type[BaseModel],
    temperature: float = 0.0,
    **kwargs,
):
    """
    Tworzy LLM z wymuszonym structured output (Pydantic).

    Jeśli model nie wspiera structured output (np. deepseek-reasoner),
    rzuca ValueError.

    Args:
        model_name:   ID modelu
        schema:       Klasa Pydantic (np. CompanyResearch, EmailDraft)
        temperature:  Temperatura
        **kwargs:     Dodatkowe parametry

    Returns:
        Runnable z .with_structured_output(schema)
    """
    info = MODEL_REGISTRY.get(model_name, MODEL_REGISTRY[DEFAULT_MODEL])

    if not info.get("structured_output", True):
        logger.warning(
            f"[MODEL_FACTORY] Model '{model_name}' nie wspiera structured output. "
            f"Fallback → {DEFAULT_MODEL}"
        )
        model_name = DEFAULT_MODEL

    llm = create_llm(model_name, temperature, **kwargs)
    return llm.with_structured_output(schema)


def create_llm_with_fallback(
    model_name: str,
    temperature: float = 0.0,
    **kwargs,
):
    """
    Tworzy LLM z automatycznym fallbackiem.

    Próbuje stworzyć model o podanej nazwie.
    Jeśli brak klucza lub błąd — wraca do DEFAULT_MODEL.

    Returns:
        tuple: (llm_instance, actual_model_name)
    """
    try:
        llm = create_llm(model_name, temperature, **kwargs)
        return llm, model_name
    except Exception as e:
        logger.error(
            f"[MODEL_FACTORY] Błąd tworzenia '{model_name}': {e}. "
            f"Fallback → {DEFAULT_MODEL}"
        )
        llm = create_llm(DEFAULT_MODEL, temperature)
        return llm, DEFAULT_MODEL
