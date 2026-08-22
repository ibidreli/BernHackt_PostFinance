# API-Dokumentation: Future-Me Chatbot

Kompakte Referenz für die zwei Endpunkte. Details/Bugs/Entscheidungen: [STATUS_FEATURE_NR_5_BACKEND.md](STATUS_FEATURE_NR_5_BACKEND.md). Für die Prognose-Endpunkte, auf denen dieses Feature aufbaut: [API.md](API.md).

## Grundlagen

- **REST, nicht OData** — bewusste Abweichung vom Rest der API, folgt dem Issue-Contract wörtlich. Läuft trotzdem unter `/api/v1`.
- **Zwei LLM-Calls, nie Rohtransaktionen.** Extraktion sieht nur die Frage, Formulierung nur das fertige Ergebnis. Gerechnet wird ausschliesslich über `forecast_service`.
- **Fehlerformat identisch zu Feature 4:** `{"error": {"code", "message"}}` (service-weite Middleware).
- **Interaktiv testen:** `/docs` (Swagger UI).

## `POST /api/v1/assistant/ask`

```bash
curl -X POST "http://localhost:8000/api/v1/assistant/ask" \
  -H "Content-Type: application/json" \
  -d '{"message": "Kann ich mir in 5 Jahren ein Auto für 30000 leisten?", "horizon": "5y"}'
```

**Request:** `message` (1–1000 Zeichen), `horizon` (`present`|`1y`|`5y`|`10y`, Default `present`), `assumptions` (`salary_growth_pct`/`inflation_pct`/`savings_rate_pct`, alle optional), `context` (`conversation_id`, `pending_clarification`).

**Response:** `intent` (`affordability`|`what_if`|`time_to_goal`|`unsupported`), `status` (`yes`|`tight`|`no_unless`|`needs_clarification`|`unsupported` — **nie ein blosses Ja/Nein**), `answer` (Text), `facts`, `levers` (max. 3, nur variable Kategorien), `chart` (einer von drei festen Typen), `assumptions_used`, `clarification`, `source` (`live`|`cached`).

**Drei unterstützte Fragetypen**, alles andere → `unsupported` mit Nennung der drei Typen:

| Intent | Beispiel |
|---|---|
| `affordability` | "Kann ich mir ein Auto für 30000 leisten?" |
| `what_if` | "Was wäre, wenn ich Netflix kündige?" (nur cancel/adjust/add/one_off — keine Kategorie-Prozent-Änderung) |
| `time_to_goal` | "Wann habe ich 20000 zusammen?" |

**Rückfrage-Flow:** `status=needs_clarification` liefert `answer` = die Frage selbst, `clarification.options` als Buttons, `facts=null`. Antwort im nächsten Request mit gleicher `context.conversation_id` (+ optional `pending_clarification`) schicken — löst deterministisch auf, kein zweiter LLM-Call. Maximal eine Rückfrage pro Anfrage.

**Horizont:** Der Text gewinnt über den Umschalter ("in 5 Jahren" bei `horizon=present` im Request → Antwort nutzt trotzdem 5y).

**Fehler:** `409` kein Saldo verfügbar · `504` LLM-Timeout (8s, `AssistantLLMTimeoutError.stage` sagt welcher der beiden Calls) · `502` sonstiger LLM-Fehler. Kein stiller Fallback bei Timeout — bewusste Abweichung vom Issue, siehe STATUS.

## `GET /api/v1/assistant/suggestions`

```bash
curl "http://localhost:8000/api/v1/assistant/suggestions?horizon=5y"
```

Drei vorformulierte Fragen als Chips, je nach `horizon`. Kein LLM-Call.

## `ASSISTANT_MODE=cached` (Offline-Fallback)

Zero externe API-Calls: 5 fest hinterlegte Demo-Fragen (`app/services/cache_service.py`), exaktes Text-Matching (kein Fuzzy-Match — bewusst als kontrollierter Demo-Fallback deklariert, nicht als allgemeine Offline-NLU). `forecast_service` rechnet dabei **echt**, nur die Formulierung kommt aus einem Template statt vom Modell. `source` im Response zeigt `"cached"`.

Die 5 Fragen (auch als `unsupported`-Hinweis gelistet, falls eine andere Frage kommt):
- "Kann ich mir in 5 Jahren ein Auto für 30000 leisten?"
- "Was wäre, wenn ich Netflix kündige?"
- "Wann habe ich 20000 zusammen?"
- "Kann ich mir jetzt Kopfhörer für 300 leisten?"
- "Was wäre, wenn ich monatlich 50 mehr für Fitness ausgebe?"

## Zahlenabgleich (T10)

Jede live formulierte Antwort wird gegen `facts` geprüft (typgebunden: CHF-Zahlen gegen CHF-Fakten, Monats-Zahlen gegen Monats-Fakten). Bei Abweichung greift automatisch dieselbe Template-Formulierung wie im `cached`-Modus — für den Client unsichtbar, `source` bleibt `"live"`.

## Bekannte Grenzen, kurz

Vollständige Liste: [STATUS_FEATURE_NR_5_BACKEND.md](STATUS_FEATURE_NR_5_BACKEND.md). Die wichtigsten:

- Kein automatisiertes Eval-Set für die Prompts.
- LLM-Nichtdeterminismus bei Folgefragen (kann Horizont/Intent zwischen Läufen leicht unterschiedlich interpretieren).
- `payment_type_relevant` (Bar/Leasing-Rückfrage nur bei sinnvollen Fällen) ist eine Modell-Heuristik, kein fester Regelsatz — Grenzfälle wie "Hochzeit" bleiben unpräzise.
