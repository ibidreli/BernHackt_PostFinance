---
tags: [backend]
---

# OData-Layer

Code: `app/odata/` (`envelope.py`, `query.py`, `metadata.py`) · Verwendung: [[API-Referenz]]

Die API spricht **OData v4 als pragmatisches, handverifiziertes Subset** — bewusst selbst gebaut statt eine Library zu nehmen: das begrenzte Grammatik-Subset liess sich vollständig selbst verifizieren, statt auf die exakte API einer unbekannten Bibliothek zu wetten.

**Mount-Pfad:** `/api/v1` (vormals `/odata`) — reine URL-Umbenennung, `SERVICE_ROOT` in `envelope.py`. Die OData-Semantik selbst (Envelope, `OData-Version`-Header, `$metadata`, Fehlerformat, `$filter`/`$select`/`$top`/`$skip`) bleibt unverändert; nur der Pfad, unter dem sie erreichbar ist, folgt jetzt der gleichen `/api/v1`-Konvention wie [[Future-Me Chatbot]]s `/api/v1/assistant/...`.

## `envelope.py`

- `odata_collection()` / `odata_single()` bauen die `@odata.context`-Envelopes.
- `ODataVersionMiddleware` stempelt `OData-Version: 4.0` auf jede Antwort (bewusst service-weit, auch `/health`).
- `install_odata_error_handlers()` konvertiert alle FastAPI-Fehler ins OData-JSON-Format `{"error": {"code", "message", "details"}}`.

## `query.py` — der `$filter`-Parser

Handgeschriebener Tokenizer + rekursiver Abstiegs-Parser: `eq ne gt ge lt le`, `and/or/not`, Klammern, Literale String/Zahl/Bool/Null. Dazu `$select`, `$orderby`, `$top`, `$skip`; `apply_query_options()` wendet alles auf die Objektliste an. **Nicht** unterstützt: `contains`/`startswith`, Arithmetik, `$batch`, Atom/XML.

## `metadata.py` — das CSDL-Dokument

Statisch handgeschriebenes XML für `GET /api/v1/$metadata`: EntityType `RecurringPayment`, Complex Types, `GetForecast`-Function, `Simulate`-Action, EntityContainer — plus (uncommitted) die `Subscription*`-Typen und die `GetSubscriptions`-Function für den [[Abo-Radar]]. **Muss bei Schema-Änderungen manuell nachgezogen werden** (nicht aus den Pydantic-Schemas generiert) — bekannte Drift-Gefahr, im Moduldocstring vermerkt.

## Bewusste Pragmatismen

- `GetForecast` nutzt Query-Parameter (`?horizon=30d`) statt der strengen OData-Klammer-Syntax `GetForecast(horizon='30d')` — hält die Swagger UI benutzbar.
- `$select`/`$filter` auf nicht existierende Felder liefern `null` bzw. leere Liste statt eines Fehlers — harmlos, kann aber Tippfehler in Frontend-Queries maskieren ([[Projektstatus]]).
