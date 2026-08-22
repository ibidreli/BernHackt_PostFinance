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

**Nachtrag — Pitch-Fix:** Die oben beschriebene Quartals-/Jahres-Zufallserkennung wurde konkret vor dem Pitch behoben (`_detect_interval`: höhere Mindest-Vorkommenzahl + Mehrheits-Plausibilitätsprüfung der einzelnen Lücken, gilt jetzt auch für `monthly`). Details, inkl. zwei dabei selbst gefundener Über-/Unterkorrekturen: siehe T7-Abschnitt unten.

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

**Stand:** Fertig — `monthly_category_stats` (T5) und `BalanceRepository` (T6, neu) implementiert und gegen den echten Datensatz verifiziert.

**Bugs:**
- **Gefunden & gefixt:** Die ursprüngliche T1-Sortierung (`sort by date`) behielt bei mehreren Buchungen desselben Tages stillschweigend die Datei-Reihenfolge (newest-first) statt sie umzudrehen — dadurch landeten z. B. zwei Buchungen vom 25.08.2022 in der falschen Reihenfolge. Fix: Liste vor dem stabilen Sort umkehren, damit gleiche Tage in chronologischer Reihenfolge landen.
- **Untersucht, nicht gefixt (siehe Grenzen):** `Valuta` (Wertstellung) kann vor `Datum` (Buchungsdatum) liegen — als Sekundär-Sortierschlüssel deshalb nicht zuverlässig für die exakte Sub-Tages-Reihenfolge.
- **Pauschales Duplikat-Entfernen ausprobiert und wieder verworfen:** 32 Gruppen exakt identischer Zeilen in der CSV. Für manche (z. B. eine 3-fach gelistete SBB-Zahlung) ist Löschen korrekt, für mindestens eine (zwei identische "OXYMORON BAAR"-Buchungen) beweist die Saldo-Rekonstruktion aber, dass beide real sind. Keine Spalte unterscheidet die Fälle → Dedup verworfen, nicht umgesetzt.

**Grenzen:**
- Sub-Tages-Reihenfolge mehrerer Buchungen am selben Tag ist aus den Quelldaten **nicht zuverlässig rekonstruierbar** (weder `Datum`+Dateireihenfolge noch `Valuta` sind durchgehend korrekt) — betrifft aber nicht den eingehaltenen Vertrag: `Balance.as_of()` nimmt einen `date`-Parameter (keine Uhrzeit) und ist auf **Tages-Granularität verifiziert exakt** (1312 von 1312 Kalendertagen mit echtem Saldo-Checkpoint, 0 Abweichungen).
- `monthly_category_stats`: Kategorie-Median wird einmalig über alle verfügbaren Monate berechnet, keine gewichtete Berücksichtigung von "wie weit zurück" ein Monat liegt.
- Kein Caching - `monthly_category_stats` wird bei jedem Aufruf neu berechnet (für 5303 Transaktionen unkritisch, aber bei jedem Forecast-Request eine neue Aggregation).

**Erweiterungen:**
- Falls Sub-Tages-Genauigkeit später doch gebraucht wird (z. B. Intraday-Chart): würde eine echte Buchungssequenznummer in den Rohdaten brauchen, die aktuell nicht existiert.
- Gewichtete/exponentiell abklingende Monats-Gewichtung für `monthly_category_stats`, falls "neuere Monate zählen mehr" gewünscht ist.

---

## T7 — `services/forecast_service.py`

**Stand:** Fertig — `forecast()` (alle 4 Horizonte) und `simulate()` (alle 4 Eingriffstypen, einzeln und kombiniert) implementiert und gegen den echten Datensatz verifiziert. Zusammen mit T8 gebaut (siehe dort), da der Service dessen Pydantic-Schemas direkt zurückgibt statt eine doppelte interne Repräsentation zu pflegen.

**Bugs:**
- **Gefunden & gefixt:** `tight_date.days_before_salary` wurde negativ bei Horizonten >30 Tage, weil der beim `as_of` berechnete Lohntermin verwendet wurde statt des Lohntermins, der auf das Engpass-Datum selbst folgt (bei 90d/365d liegt der nächste Lohn oft schon vor dem Engpass). Fix: Lohntermin wird relativ zum Engpass-Datum neu berechnet.
- **Gefunden & gefixt (der wichtigste Fund):** `recurring_id` war als reiner Merchant-String definiert — aber `RecurringPayment.merchant` ist **nicht eindeutig** (13 Merchant-Strings wie "LASTSCHRIFT", "PAYPAL", "MIGROS" bezeichnen je 2-4 verschiedene Recurring-Payment-Gruppen mit unterschiedlicher Kategorie/Flow). Beim Testen von `simulate()` löschte das Canceln von Netflix stillschweigend auch eine völlig unabhängige "LASTSCHRIFT"-Zahlung, weil beide beim Dict-Aufbau denselben Schlüssel teilten. Fix: neue `recurring_payment_id()`-Funktion in T3, die Merchant+Kategorie+Flow zu einer eindeutigen ID kombiniert; überall als `recurring_id` verwendet.
- **Gefunden & gefixt:** `one_off`-Anpassungen mit positivem `amount_chf` wurden als Einnahme statt Ausgabe behandelt — ein simulierter Autokauf für CHF 30'000 hat den Saldo erhöht statt gesenkt. Fix: `amount_chf` ist bei `one_off` immer eine positive Ausgaben-Magnitude (passend zum Issue-Beispiel "Auto"), keine Vorzeichen-Kodierung mehr.

**Grenzen:**
- **"Kantine halbieren"-Preset nicht abbildbar** (Rückfrage gestellt, vom Team bestätigt: bleibt bei den 4 spezifizierten Eingriffstypen, kein 5. Typ). Das Issue nennt es als dritten Demo-Preset ("Anpassung der variablen Kategorie"), aber keiner der vier spezifizierten Eingriffstypen (`cancel_recurring`, `adjust_recurring`, `add_recurring`, `one_off`) erlaubt eine Topf-2-Kategorie-Anpassung. Kantine-Besuche landen als hochfrequente, variable Ausgaben in Topf 2, nicht als erkannter Rhythmus in Topf 1.
- **Band wächst linear über die Zeit** (Tagesrate × Tage), nicht mit abgeschwächter Zeitskalierung (z. B. Wurzel-Skalierung wie bei einem Random Walk). Ehrlich, aber bei 365 Tagen ergibt sich ein sehr breites Band (im Test: CHF -5807 bis +10046) - spiegelt die tatsächliche Kategorie-Varianz der Daten wider, könnte aber in der UI unruhig wirken.
- **Vorzeichen-Konvention für `diff` bewusst abweichend vom Issue-Beispiel:** Die Beispiel-JSON zeigt `"monthly_chf": -20.90` für ein Szenario, das nach "251 mehr" (positiv) klingt. Wir verwenden durchgehend "positiv = Verbesserung" (Saldo-Verbesserung, mehr Puffer-Tage), konsistent mit `tight_date_shift_days`, statt die mehrdeutige Beispielzahl zu treffen.
- `diff.cumulative_series` geht von identischen Daten in Baseline- und Szenario-Serie aus (`zip`) - gilt für alle drei Demo-Presets und den one_off-Anwendungsfall, aber nicht allgemein, falls ein Eingriff den Lohn selbst verändert (würde `horizon_end` verschieben).
- Kategorie-Median für Perzentil-Summierung geht von Unabhängigkeit zwischen Kategorien aus (siehe Moduldocstring) - Standard-Vereinfachung, keine Kovarianz-Berechnung.

**Erweiterungen:**
- 5. Eingriffstyp für Topf-2-Kategorie-Anpassungen, falls "Kantine halbieren" wörtlich gebraucht wird.
- `diff.cumulative_series`-Alignment über Datum statt Listenposition, für den allgemeinen Fall unterschiedlicher `horizon_end`.

**Nachtrag — Pitch-Fix "Band bei 365d wirkt nicht kompetent":**
Band-Breite wuchs linear mit der Zeit (Tagesrate × Tage) → bei 365 Tagen Spanne von ~CHF 15'852 (−5807 bis +10046), unglaubwürdig breit. Fix: nur der Erwartungswert wächst weiter linear, die Bandbreite um ihn herum wächst mit `√Monate` statt `Monate` (Zentraler Grenzwertsatz: Streuung einer Summe unabhängiger Monate wächst mit der Wurzel der Anzahl, nicht linear). Reduziert 365d-Spanne auf CHF 4'726 (Faktor ~3.35, nahe am erwarteten √12≈3.46).

**Dabei ein selbst gefundener Bug vor dem Ausliefern:** Reine `√Monate`-Skalierung hätte **kurze** Horizonte (< 1 Monat) breiter statt schmaler gemacht (`√x > x` für `x<1`) — genau die "bis zum nächsten Lohn"-Standardansicht wäre stärker verunsichert worden (Spanne CHF 130 → CHF 428 im Test). Gefixt: Skalierung ist linear bis 1 Monat (matcht die Kalibrierungsgranularität), erst danach `√Monate`-gedämpft, stetig am 1-Monats-Punkt. `next_salary`-Spanne danach wieder bei CHF 134 (praktisch unverändert).

**Nachtrag — Pitch-Fix "Jahresansicht zeigt erfundene Fixkosten":**
`quarterly`/`yearly` bekamen eine höhere Mindest-Vorkommenzahl (4 statt 3) plus eine Prüfung, dass **jede einzelne** Lücke (nicht nur der Median) plausibel ist. Erster Durchlauf: 20 → 12 verdächtige Einträge (u. a. `RATHAUS`) weiterhin sichtbar, weil sie über `monthly` reinrutschten, nicht über `quarterly`/`yearly` — die ursprüngliche Annahme "monthly hat das Problem nicht" war falsch (Gegenbeweis: `RATHAUS` mit Lücken von 7/16/35/49/57/201 Tagen, Median zufällig ~30). Gap-Plausibilitätsprüfung auf `monthly` erweitert.

**Zweiter selbst gefundener Bug vor dem Ausliefern:** "Alle Lücken müssen passen" war zu strikt — Netflix hat 40 Lücken, 39 davon sauber monatlich, **eine einzige** übersprungene Zahlung (61 Tage) reichte, um die komplette Erkennung zu verwerfen (verifiziert). Realistische Abos überspringen gelegentlich einen Zyklus. Fix: Mehrheits-Kriterium (≥80 % der Lücken müssen passen) statt "alle". Ergebnis: 0 verdächtige Einträge, Netflix/Touring/Bankpaket/Spotify/OpenAI/Render.com weiterhin korrekt erkannt.

**Bewusst in Kauf genommen:** `SWISSCOM` (67 % Trefferquote) und `STEUERVERWALTUNG` (43 %) fallen jetzt auf `irregular` zurück und verschwinden aus Topf 1. Geprüft und für plausibel befunden — beide vermischen unter derselben Ersttoken-Gruppierung mehrere unterschiedliche Zahlungsströme (Swisscom: Basisabo + WINGO-Mobile-Zusatz; Steuerverwaltung: Steuerzahlungen UND -rückerstattungen mit unterschiedlicher Rhythmik). `irregular` (→ Topf 2, variable Baseline) ist hier ehrlicher als eine erzwungene, tatsächlich nicht sauber monatliche Fixkosten-Markierung.

---

## QA-Runde nach den Pitch-Fixes (Endpunkte end-to-end gegen `docker compose up`)

**Systematisch gegen die Akzeptanzkriterien der Issue getestet**, nicht nur Stichproben. Ergebnis im Detail:

**✅ Bestätigt korrekt:**
- Alle 4 Horizonte strukturell valide, `series[-1]` immer exakt gleich `free_to_spend` (Konsistenz-Invariante hält).
- Band ist exakt 0-breit an Tag 0 (`as_of`), wächst nur durch variable Ausgaben — Fixkosten verschieben alle drei Kurven gleich, verbreitern nichts.
- `tight_date` verifiziert aus der **unteren** Bandgrenze: am gefundenen Datum war der Erwartungswert noch positiv (CHF 756), nur die untere Grenze war unter dem Puffer (-50) — bestätigt, dass wirklich die pessimistische Kurve zählt.
- Ausreisser sauber ausgeschlossen und in `assumptions.excluded_outliers` benannt (Decathlon, Garmin, Gurtenfestival etc.).
- Alle 4 Eingriffstypen einzeln und kombiniert exakt korrekt (`diff.monthly_chf`/`total_at_horizon_chf` bis auf den Rappen nachgerechnet und bestätigt).
- 6 Fehlerpfade geprüft (kein Saldo, ungültiger Horizont, kaputtes JSON, unbekannter Eingriffstyp, fehlendes Pflichtfeld, unbekannte `recurring_id`) — alle liefern saubere OData-Fehler statt Absturz.
- **Eigener Testfehler dabei gefunden und korrigiert**, bevor er fälschlich als API-Bug gemeldet wurde: Shell-Variablen persistieren nicht zwischen Bash-Aufrufen — ein erster "kombinierter Eingriffe"-Test schlug deshalb fehl (leere `recurring_id`), nicht wegen der API.

**⚠️ Gefunden, noch offen — Akzeptanzkriterium nicht erfüllbar mit dem aktuellen Sample-Datensatz:**
"Die Jahresansicht zeigt 13. Monatslohn, Steuertermine und Quartalsrechnungen als sichtbare Ausschläge" — nach den Pitch-Fixes zeigt die 365d-Ansicht nur noch 7 rein monatliche Positionen, keine Quartals-/Jahres-Ausschläge mehr (vorher: 6 quarterly, teils Fantasie-Treffer wie oben beschrieben).

Tiefer geprüft, ob das nachträglich reparierbar ist: **Nein, mit `data_personal.csv` nicht** - es handelt sich um eine echte Datenlücke, keinen Code-Fehler:
- `STEUERVERWALTUNG`-Buchungen im Datensatz sind tatsächlich chaotisch (Beträge von CHF 20 bis CHF 2500, Abstände von 7 bis 330 Tagen, sogar eine Rückerstattung dazwischengemischt) — kein verstecktes sauberes 3×/Jahr-Muster, das eine bessere Erkennung retten könnte.
- `TOURING` (Lohn) zeigt **keinen** 13.-Monatslohn-Sprung im Dezember (Dez. 2024/2025 sind sogar unterdurchschnittlich, nicht überdurchschnittlich).
- Keine BKW-artige, sauber quartalsweise wiederkehrende Rechnung im gesamten Datensatz gefunden.

**Konsequenz:** Der Algorithmus ist korrekt und würde ein echtes Quartals-/Jahresmuster erkennen (das war ja gerade Zweck der beiden Fixes) — es gibt in diesem konkreten Sample-Datensatz schlicht keins zu finden. Für den Pitch zwei Optionen: (a) auf die "echten" Daten warten/hoffen, dass die eine saubere Quartalsrechnung enthalten, oder (b) eine synthetische Quartalsposition (z. B. eine BKW-artige Buchung) manuell in die Demo-CSV einfügen, bevor der Datensatz geladen wird.

**Kleinere, nicht-fatale Robustheitslücken in `RecurringPayments`:**
- `$select` mit nicht existierendem Feldnamen liefert `null` statt eines Fehlers (z. B. `$select=tippfehlr` → `{"tippfehlr": null}`).
- `$filter` auf ein nicht existierendes Feld liefert eine leere Liste statt eines Fehlers (könnte einen Tippfehler als "keine Treffer" maskieren).

Beides ist harmlos für die Demo (kein Crash, keine falschen Zahlen), aber bei einem Tippfehler in einem Frontend-Query würde man das nicht sofort bemerken.

---

## T8 — `schemas/forecast.py`

**Stand:** Fertig (zusammen mit T7 gebaut) — alle Pydantic-Schemas exakt nach API-Contract, inkl. Discriminated Union für die vier Eingriffstypen (verifiziert: `SimulateRequest` parst alle vier Typen korrekt).

**Grenzen:**
- `recurring_id: str` statt `int` (DB-PK) — konsistent mit der "keine DB"-Entscheidung, siehe T2.
- `Assumptions.notes: list[str]` ist eine Ergänzung über das Issue-Beispiel hinaus (freitextige Edge-Case-Hinweise statt ein Boolean pro Fall) - bewusste, dokumentierte Erweiterung.

---

## T9 — OData-Layer

**Stand:** Fertig — `$filter`/`$select`/`$orderby`/`$top`/`$skip`, OData-Envelope, OData-Error-Format und das statische `$metadata`-CSDL-Dokument implementiert und end-to-end verifiziert (`docker compose up` + curl).

**Bugs:** Keine gefunden.

**Grenzen:**
- `$filter`-Parser ist handgeschrieben (nicht die `odata-query`-Library aus der ursprünglichen Planung) — bewusste Entscheidung, siehe Moduldocstring: das begrenzte Grammatik-Subset (eq/ne/gt/ge/lt/le, and/or/not, Klammern, String/Zahl/Bool/Null) liess sich vollständig selbst verifizieren, statt auf die exakte API einer unbekannten Bibliothek zu wetten. Kein `contains`/`startswith`, keine Arithmetik.
- `$metadata` ist statisch handgeschrieben, nicht aus den Pydantic-Schemas generiert — muss bei Schema-Änderungen manuell nachgezogen werden (im Moduldocstring vermerkt).
- `OData-Version`-Header und Error-Envelope gelten service-weit (auch für `/health`, nicht nur `/api/v1/*`) — bewusst einfach gehalten, siehe Moduldocstring.
- Kein `$batch`, keine Atom/XML-Repräsentation — bewusst ausserhalb des pragmatischen Subsets (siehe frühere OData-Tiefe-Entscheidung).

**Erweiterungen:**
- `$metadata`-Generator aus den Pydantic-Schemas, falls sich der Contract noch oft ändert.
- OData-Funktionen wie `contains`/`startswith` im `$filter`-Parser, falls die Frontend-Suche das braucht.

---

## T10 — `api/routes/forecast.py`

**Stand:** Fertig — alle drei Endpunkte über echte HTTP-Requests verifiziert (`docker compose up` + curl): `GET /api/v1/RecurringPayments` (EntitySet), `GET /api/v1/GetForecast` (Function), `POST /api/v1/Simulate` (Action). (Zum Zeitpunkt von T10 lagen die Routen unter `/odata`; seit Commit `24ba87e` ist der Mount `/api/v1`.)

**Bugs:** Keine gefunden.

**Grenzen:**
- `GetForecast` nutzt Query-Parameter (`?horizon=30d`) statt der strengen OData-Klammer-Syntax (`GetForecast(horizon='30d')`) — bewusste Abweichung fürs pragmatische Subset, hält Swagger UI nutzbar (im Moduldocstring begründet).
- `recurring_id` (z. B. `"NETFLIX.COM::Wohnen::expense"`) ist kein "schönes" API-Feld, sondern die interne Eindeutigkeits-ID aus T7 direkt durchgereicht — funktional korrekt und verifiziert, aber für ein Frontend-Dropdown müsste man eher `merchant` anzeigen und `recurring_id` im Hintergrund mitführen.
- `NoBalanceAvailableError` wird auf HTTP 409 gemappt (State-Konflikt) statt 404/400 — Interpretationsentscheidung, da es kein fehlendes Client-Input-Problem ist, sondern ein fehlender Serverzustand.

**Erweiterungen:**
- Bound Functions/Actions direkt auf der EntitySet-Route (`/RecurringPayments('id')/...`), falls später gebraucht.
- `recurring_id` im Frontend hinter einem lesbaren Label verstecken, falls die rohe ID stört.

---

## T11 — Dokumentation

**Stand:** Fertig — `API.md` (Endpunkt-Referenz), Swagger jetzt mit echten Response-Schemas statt generischem `dict` für `GetForecast`/`Simulate`, `$metadata` schon aus T9 fertig, `README.md` verlinkt beides.

**Bugs:**
- **Gefunden & gefixt:** `ForecastEnvelope`/`SimulateEnvelope` (neue typisierte Schemas, damit Swagger die echte Antwortform statt `dict` zeigt) liessen sich beim ersten Versuch nicht laden: `NextSalary.date: date = Field(...)` kollidierte mit `from __future__ import annotations` — ein bekannter Pydantic-Stolperstein, wenn Feldname und Typname identisch sind (`date: date`) und gleichzeitig `Field(...)` verwendet wird. Fix: bei diesem einen Feld auf reine Annotation ohne `Field()` zurückgestellt, Beschreibung stattdessen in den Docstring.

**Grenzen:**
- `GET /api/v1/RecurringPayments` bleibt bewusst ohne `response_model` (also ohne strikt typisiertes Swagger-Schema) — `$select` kann auf ein beliebiges Feld-Subset projizieren, ein festes Pydantic-Schema würde bei Verwendung von `$select` an der eigenen Validierung scheitern. Stattdessen ausführliche Swagger-`description` mit Beispielen.
- **Gefunden & gefixt (nach T11, beim gemeinsamen Testen):** `amount_history` war standardmässig in jedem `RecurringPayments`-Listeneintrag enthalten — bei einem Merchant mit 196 Verlaufseinträgen machte das 88 % der Payload einer 10-Item-Antwort aus (25.4 KB → 2.8 KB nach dem Fix). Kein Bug im engeren Sinne, aber kein guter Default für einen Listen-Endpunkt. Fix: `amount_history` nur noch enthalten, wenn explizit per `$select` angefordert (`_DEFAULT_SELECT` in `app/api/routes/forecast.py`).
- `$metadata` (CSDL) und `API.md` können bei Schema-Änderungen auseinanderlaufen, da beide von Hand gepflegt werden (siehe T9-Grenzen).

**Erweiterungen:**
- OpenAPI-Beispiel-Responses (`response_model` deckt nur die Struktur ab, keine Beispielwerte) für noch bessere Swagger-Doku.
