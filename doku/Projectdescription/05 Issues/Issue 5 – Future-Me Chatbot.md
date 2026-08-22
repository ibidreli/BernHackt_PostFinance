---
tags: [issue, ai]
status: in-arbeit
issue: 5
---

# Issue #5 — Future-Me Chatbot (Szenario-Assistent)

[GitHub #5](https://github.com/ibidreli/BernHackt_PostFinance/issues/5) · **open** · Labels: `feature`, `frontend`, `backend`, `ai`, `priority:medium` · Epic: Beyond the List – Assistenz · Abhängigkeit: Prognose ([[Issue 4 – Zukunftsprognose]]) muss laufen — der Bot rechnet nicht selbst · Feature-Note: [[Future-Me Chatbot]]

## Kern der Spec

Drei Fragetypen (`affordability`, `what_if`, `time_to_goal`), alles andere höflich abgelehnt. Vier Horizonte inkl. `present` als annahmefreiem Vertrauensanker. Dreistufige Antwortlogik `yes`/`tight`/`no_unless` mit Fehlbetrag, nötigem Monatsbetrag und Hebeln aus **variablen** Kategorien. Maximal eine Rückfrage, mit Button-Optionen aus einem festen Katalog (Bar/Leasing, Zeitpunkt, einmalig/monatlich). Drei feste Chart-Typen — das Modell wählt, generiert nicht. Sichtbare, veränderbare Annahmen (Lohnwachstum/Inflation/Sparquote); Ton nüchtern, Beträge > 1 Jahr auf CHF 100 gerundet; Prompts versioniert unter `prompts/`. Offline-Fallback `ASSISTANT_MODE=cached`. Wichtigste Absicherung: **Beträge im Antworttext werden automatisch gegen `facts` geprüft** — kein LLM-generierter Betrag erreicht die Nutzer:innen.

API: `POST /api/v1/assistant/ask` (Antwort mit `intent`, `status`, `facts`, `levers`, `chart`, `assumptions_used`, `clarification`, `source`) + `GET /api/v1/assistant/suggestions`.

## Umsetzungsstand

Die **LLM-Implementierung ist auf `main` gemergt** (PR #12, 22.08.2026; Status-Log `STATUS_FEATURE_NR_5_BACKEND.md`, T0–T13): echte OpenAI-Anbindung mit Structured Outputs, `ASSISTANT_MODE=cached` als Offline-Fallback, Zahlenabgleich (`verification_service`), Konversations-State pro `conversation_id`. Die zwischenzeitliche regelbasierte Zweit-Implementierung von `origin/feature/prognosis` wurde beim Merge verworfen — ihre Testdatei `tests/test_assistant.py` entfiel mit; Verifikation läuft über `inspect_*`-Skripte. Das Frontend wurde am 22.08. auf die neuen Endpunkte umgestellt. Vier team-abgestimmte Abweichungen: Timeout ohne stillen Fallback, "Kantine halbieren" → `unsupported`, Folgefragen im Scope, `potential_chf` = historisches Minimum. Details: [[Assistant-Pipeline]], [[Future-Me Chatbot]].

## Offene Fragen aus dem Issue

Kalibrierung der `tight`-Schwelle (3 Monatsausgaben) an echten Daten; Leasing-Modellierung (vereinfacht als monatliche Zahlung, dokumentiert); Folgefragen (inzwischen positiv entschieden); `potential_chf`-Berechnung (entschieden: historisches Minimum).
