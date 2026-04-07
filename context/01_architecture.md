# 01. ARCHITECTURE & TECH STACK OVERVIEW

## 1. System Identity
Nazwa Projektu: Agent Titan Bot (Nexus Engine v3.0)
Typ: Asynchroniczny, wielowątkowy system agentowy B2B (High-Value Autonomous Agents).

## 2. Tech Stack (Google AI Ecosystem)
- **Language:** Python >= 3.12
- **Integracja AI:** `langchain-google-genai`
- **Zwiad i Ekstrakcja Danych:** `gemini-3.1-flash-lite-preview` - używany w zwiadzie do taniej i błyskawicznej analizy kodu HTML (Firecrawl).
- **Copywriting i Weryfikacja (Auditor):** `gemini-3.1-pro-preview` - używany do generowania bezbłędnych, pozbawionych halucynacji maili i rygorystycznej kontroli logicznej.
- **Database:** PostgreSQL (SQLAlchemy ORM), NocoDB jako GUI.
- **Frontend/Dashboard:** Streamlit (ekosystem webowy).
- **Cache & Message Broker:** Redis.

## 3. Core Components & RODO (GDPR) Constraint
System operuje w Unii Europejskiej. RODO to fundament:
- **`app/rodo_manager.py` (Nowy komponent):** Moduł zarządzający klauzulami informacyjnymi, czarną listą domen i anonimizacją danych.
- **`app/agents/writer.py`:** Generuje treść maili przy pomocy Gemini 3.1 Pro i obowiązkowo integruje dynamiczną stopkę RODO na końcu działania.