# System-Prompts (Future-Me Chatbot, Feature #5)

Beide LLM-Calls im [Architektur-Diagramm](../../STATUS_FEATURE_NR_5_BACKEND.md) haben ihren eigenen, hier versionierten System-Prompt - **nicht inline im Code**, wie im Issue gefordert ("Die technische Jury wird danach fragen").

| Datei | LLM-Call | Geladen von | Gebaut in |
|---|---|---|---|
| `intent_extraction_v1.md` | #1 - Extraktion (Frage → strukturierte Parameter) | `app/services/intent_service.py` | T3 |
| `answer_formulation_v1.md` | #2 - Formulierung (fertiges Ergebnis → Text) | `app/services/formulation_service.py` | T7 |

## Prinzip

Beide Prompts sind bewusst rollenbeschränkt:

- **Extraktion** sieht nur die Nutzerfrage (+ optional einen Kontext-Digest für Folgefragen) und liefert strukturierte Parameter nach festem JSON-Schema (Structured Outputs). Sie trifft **keine** inhaltliche Entscheidung, rechnet nichts, formuliert keine Rückfrage-Texte - die sind fest im Code (`intent_service._FIXED_CLARIFICATIONS`) hinterlegt, nicht vom Modell erfunden.
- **Formulierung** sieht nur das bereits fertig berechnete Ergebnisobjekt (`status`/`facts`/`levers`/`assumptions_used`) - nie eine Rohtransaktion, nie den Rechenweg. Sie entscheidet nichts neu, sondern baut Text aus Zahlen, die schon feststehen.

Beide Modelle sind also strikt getrennt von `forecast_service` (der einzigen Stelle, die tatsächlich rechnet) - siehe Kernsatz aus dem Issue: *"Ein Sprachmodell darf bei Geld nicht rechnen."*

## Versionierung

Dateiname trägt eine Versionsnummer (`_v1`, künftig `_v2`, ...). **Solange eine Version im aktiven Einsatz ist** (auch mit mehreren Korrekturen während der Entwicklung, siehe unten), wird sie in-place bearbeitet - kein Versionssprung pro Tippfehler-Fix. Ein neuer Versionssprung ist für einen **inhaltlich bedeutsamen** Wechsel gedacht (z. B. ein grundlegend anderer Ton, ein neues Antwortformat) - dann bleibt die alte Datei zur Nachvollziehbarkeit im Repo liegen, referenziert von Code und STATUS-Doc wird auf die neue Version umgestellt.

`intent_extraction_v1.md` und `answer_formulation_v1.md` wurden während der Entwicklung (T3/T7) mehrfach überarbeitet, nachdem Live-Tests gegen die echte OpenAI-API konkrete Probleme zeigten - alle in [STATUS_FEATURE_NR_5_BACKEND.md](../../STATUS_FEATURE_NR_5_BACKEND.md) dokumentiert:

- **Extraktion:** `payment_type_relevant`-Feld nachgezogen, nachdem "Weltreise" fälschlich die Bar/Leasing-Rückfrage auslöste (T8).
- **Formulierung:** `adjustment_description`-Feld nachgezogen, nachdem eine Netflix-Kündigung als "Erhöhung" beschrieben wurde; Einheiten-Klarstellung für `buffer_after_months` (Monate, nicht CHF); Anweisung, die interne `"Hauptkategorie // Unterkategorie"`-Schreibweise natürlich umzuformulieren (alle T7).

## Bekannte Grenzen

- Kein automatisiertes Eval-Set - die Verifikation ist die Menge der in `app/inspect_intent.py`/`app/inspect_assistant.py` live gegen die echte API getesteten Fragen, kein systematisches Prompt-Testing-Framework.
- Grenzfälle bleiben nicht perfekt: z. B. löst "Kann ich mir eine Hochzeit für 20'000 leisten?" weiterhin die Bar/Leasing-Rückfrage aus (`payment_type_relevant=true`), obwohl das genauso grenzwertig ist wie eine Reise - das Modell zieht die Linie nicht immer exakt dort, wo ein Mensch sie ziehen würde.
