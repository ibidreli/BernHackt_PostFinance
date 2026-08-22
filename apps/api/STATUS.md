<!-- Title: Status — Zukunftsprognose & Szenario-Simulation (Backend) -->

# Status: Zukunftsprognose & Szenario-Simulation (Backend)

Lebendes Dokument: pro Teilschritt (T0–T11) ein Satz Stand, plus **Bugs** (gefunden & Status), **Grenzen** (bewusst nicht gelöst) und **Erweiterungen** (mögliche nächste Schritte). Wird nach jedem T aktualisiert, nicht nur am Ende geschrieben.

---

## T0 — FastAPI-Grundgerüst

**Stand:** Fertig — `docker compose up` startet die API ohne manuelle Schritte, verifiziert über `/health`.

**Bugs:** Keine gefunden.

**Grenzen:**
- Config nur über `os.environ` (kein `pydantic-settings`) — bewusst simpel für die Handvoll Werte, die es gibt.
- Keine echte DB-Migration, weil keine DB — Abweichung vom Issue-Datenmodell, dokumentiert in `README.md`.
- Fehlt/ist die CSV beim Start defekt, crasht der Container hart (Exception im Lifespan-Hook) ohne freundliche Fehlermeldung.

**Erweiterungen:**
- Graceful Error-Handling + klare Fehlermeldung, falls CSV beim Start fehlt oder nicht parsebar ist.
- Docker-`HEALTHCHECK`-Direktive für Orchestrierung.
- Lint/Type-Check-Setup (aktuell kein ruff/mypy konfiguriert).

---

## T1 — CSV-Ingestion & Normalisierung

**Stand:** Fertig — alle 5303 Zeilen der Sample-CSV normalisiert, Merchant-Extraktion gegen den vollständigen echten Datensatz verifiziert.

**Bugs:**
- **Gefunden & gefixt:** `GELD SENDEN`-Buchungen (Sender- *und* Empfänger-Telefonnummer im Text) liessen durch einen Greedy-Regex `"AN TELEFON-NR. ..."` im extrahierten Merchant-Namen stehen. Fix: konsumierender Regex, der alle `TELEFON-NR.`-Token vor der Capture-Gruppe verschluckt.

**Grenzen:**
- Merchant-Extraktion ist regelbasiert (Regex-Kaskade), kein ML/Fuzzy-Matching — ~9–10 % der Zeilen laufen über einen generischen Fallback (funktioniert gut, ist aber nicht Template-genau).
- ~15 Zeilen (0.3 %) bei `LASTSCHRIFT`, wo eine vermittelnde Bank (UBS, Raiffeisen, Hypothekarbank) vor der IBAN steht: Extraktion liefert die Bank statt des eigentlichen Zahlungsempfängers.
- Merchant-Namensvarianz (z. B. 3 Netflix-Textvarianten) wird in T1 selbst **nicht** kanonisiert — nur für Gruppierungszwecke in T3 gelöst, `Transaction.merchant` bleibt roh.
- `is_transfer` wird nicht erkannt (bewusste Produktentscheidung) — Kandidatensignale (`Finanzen // Sonstige Geldtransfers`, `Überträge`) sind dokumentiert, aber nicht verdrahtet.
- 3 Zeilen ohne Kategorie werden auf `None`/`None` gemappt statt klassifiziert.
- Malformte Zeilen (weder Gutschrift noch Lastschrift, oder beides) werden **still** übersprungen — kein Logging/Zähler, falls das bei echten Daten mal vorkommt.

**Erweiterungen:**
- Bank-vor-IBAN-Fälle bei `LASTSCHRIFT` sauberer parsen.
- `is_transfer`-Erkennung kalibrieren, sobald echte Daten da sind.
- Rückerstattungen (`Rückerstattungen`-Kategorie) explizit von Einnahmen-Prognose ausschliessen.
- Zähler/Log für übersprungene malformte Zeilen.

---

## T2 — Datenmodelle (`models/balance.py`, `models/recurring_payment.py`)

**Stand:** Fertig — beide Pydantic-Modelle instanziiert und als JSON serialisiert verifiziert.

**Bugs:** Keine gefunden.

**Grenzen:**
- Kein `id`/`account_id`/`merchant_id`/`category_id` als DB-Keys (keine DB, ein fest verdrahtetes Konto) — Abweichung vom Issue-Datenmodell, im Code dokumentiert.
- `amount_chf` ist `float`, nicht `Decimal` wie im Issue spezifiziert — Konsistenz mit der pandas-basierten Pipeline aus T1 war wichtiger als Spec-Treue; Rundungsrisiko bei CHF-Beträgen mit 2 Nachkommastellen in der Praxis vernachlässigbar.

**Erweiterungen:**
- Bei Bedarf auf `Decimal` umstellen (würde Änderungen durch T1/T5-Pipeline nach sich ziehen).
- `Balance.source` um weitere Quellen erweitern, falls später doch mehrere Konten/Import-Pfade dazukommen.

---

## T3 — Recurring-Payment-Erkennung

**Stand:** Fertig — 197 wiederkehrende Zahlungen erkannt, Lohntag (Tag 25) gegen den echten Datensatz verifiziert.

**Bugs:**
- **Gefunden & gefixt:** Gleicher-Tag-Häufungen (z. B. Krankenkasse mit mehreren Buchungen am selben Tag) erzeugten 0-Tage-Lücken und verzerrten die Intervall-Erkennung. Fix: Buchungen am selben Tag pro Gruppe werden vor der Gap-Berechnung zusammengefasst.
- **Gefunden & gefixt:** `detect_salary_day` berücksichtigte `is_active` nicht und hätte einen seit Mitte 2024 inaktiven Arbeitgeber (`MIGROS-GENOSSENSCHAFTS-BUND`, historisch grösster Betrag) statt der aktuellen, aktiven Lohnquelle (`TOURING`) gewählt. Fix: zusätzlicher `is_active`-Filter.

**Grenzen:**
- Merchant-Gruppierung nur über erstes Token + Kategorie, kein Fuzzy-/Amount-Clustering — Risiko von Falsch-Zusammenführungen bei kurzen, generischen ersten Tokens.
- Quartals-/Jahres-Erkennung bei genau 3 Vorkommen kann Zufall statt echter Rhythmus sein — im echten Datensatz bei ein paar Kleinbetrags-Merchants beobachtet.
- Krankenkasse (CSS) wird trotz Betragsschwankungen als `irregular` erkannt, obwohl das Issue Krankenkasse explizit in Topf 1 verortet — muss in T4 über einen Kategorie-Override aufgefangen werden.
- Kein Vertrauens-/Konfidenz-Wert pro erkannter Recurring Payment, nur die binäre Intervall-Klassifikation.

**Erweiterungen:**
- Amount-Ähnlichkeits-Clustering für robustere Gruppierung.
- Konfidenz-Score statt harter Intervall-Klassifikation.
- Kategorie-basierte Overrides für bekannte Fixkosten-Typen (Krankenkasse, Steuern, BKW, 13. Monatslohn) — direkte Vorarbeit für T4.

---

## T4 — Drei-Topf-Klassifikation

**Stand:** Fertig — alle 5303 Transaktionen klassifiziert (446 fix, 4604 variabel, 253 Ausreisser), gegen den echten Datensatz verifiziert.

**Bugs:**
- **Gefunden & gefixt:** Die naive "Buchung > 3× Kategorie-Median"-Regel aus dem Issue flaggte 237 von 2008 Supermarkt-Buchungen (12 %) fälschlich als Ausreisser, weil viele Kleinstbeträge (Snacks) den Kategorie-Median auf CHF 6 drücken — schon ein normaler CHF-40-Wocheneinkauf lag über der 3×-Schwelle. Fix: zusätzliche absolute Mindestschwelle (`OUTLIER_MIN_ABSOLUTE_CHF`, Default CHF 100), beide Bedingungen müssen erfüllt sein. Reduziert Supermarkt-Ausreisser von 237 auf 1, Gesamt-Ausreisser von 653 auf 253.

**Grenzen:**
- `OUTLIER_MIN_ABSOLUTE_CHF = 100` ist ein plausibler Startwert (an den Issue-Beispielen Reisen/Velokauf/Steuern orientiert), keine kalibrierte Zahl — wie `OUTLIER_MEDIAN_MULTIPLIER` explizit für die Samstags-Kalibrierung an echten Daten gedacht.
- Kategorie-Median für die Ausreisser-Prüfung wird einmalig über alle (inkl. potenzieller Ausreisser) Transaktionen berechnet, keine iterative Neuberechnung — bei einer Kategorie mit vielen echten Ausreissern könnte das die eigene Schwelle verzerren.
- **Konkret beobachtete Folge der T3-Gruppierungs-Grenze:** "PULVER DANIEL & JUDITH" zahlt 5× CHF 950 in klar monatlichem Rhythmus, wird aber wegen der Ersttoken-Gruppierung mit anderen Familienmitgliedern (u. a. "PULVER ELIAS") unter demselben Schlüssel zusammengelegt, verliert dadurch den erkennbaren Rhythmus und landet einzeln bei den Ausreissern statt in Topf 1. Bewusst nicht gefixt (siehe T3-Grenzen), hier nur als reales Beispiel bestätigt.
- Einige der 31 Topf-1-Merchants sind Zufallstreffer aus der bereits in T3 dokumentierten Kleine-Stichprobe-Grenze (z. B. `AVEC`, `VOLG`, `HOTEL`, `PETER`) — keine neue Baustelle, nur hier sichtbar geworden.

**Erweiterungen:**
- Iterative/robuste Median-Berechnung (z. B. erst Ausreisser grob entfernen, dann Median neu berechnen).
- Kategorie-spezifische statt globaler Schwellenwerte, falls sich einzelne Kategorien nach Kalibrierung als weiterhin schlecht getroffen erweisen.

---

## T5/T6 — Repositories (`transaction_repository.py`, `balance_repository.py`)

**Stand:** Teilweise — `transaction_repository.py` existiert bereits aus T1 (Normalisierung), Median-/Perzentil-Methoden und `balance_repository.py` fehlen noch.

---

## T7 — `services/forecast_service.py`

**Stand:** Noch nicht begonnen.

---

## T8 — `schemas/forecast.py`

**Stand:** Noch nicht begonnen.

---

## T9 — OData-Layer

**Stand:** Noch nicht begonnen — Architektur-Entscheidung steht bereits fest: pragmatisches OData-Subset, `RecurringPayments` als EntitySet, `GetForecast` als Function, `Simulate` als Action.

---

## T10 — `api/routes/forecast.py`

**Stand:** Noch nicht begonnen.

---

## T11 — Dokumentation

**Stand:** Teilweise — `README.md` enthält Run-Anleitung (`docker compose up`, lokales Setup, Inspect-Tools), `API.md` und das `$metadata`-CSDL-Dokument fehlen noch.
