---
tags: [backend, algorithmus]
---

# Recurring-Detection

Code: `app/services/recurring_detection.py` · Basis für [[Drei-Töpfe-Klassifikation]], [[Forecast-Service]], [[Abo-Radar]]

## Wie wiederkehrende Zahlungen erkannt werden

1. **Gruppierung** aller Transaktionen nach `(erstes Merchant-Token, category_main, flow)`.
2. **Same-Day-Collapse:** mehrere Buchungen derselben Gruppe am selben Tag werden zusammengefasst (Bug-Fix: Krankenkassen-Mehrfachbuchungen erzeugten 0-Tage-Lücken und verzerrten die Intervall-Erkennung).
3. **Intervall-Klassifikation** aus den Lücken zwischen Vorkommen: Median-Lücke gegen die Bereiche monthly (25–35 d), quarterly (80–100 d), yearly (340–390 d) — **plus** eine Plausibilitätsprüfung: **≥ 80 % der einzelnen Lücken** müssen im Bereich liegen, mit höheren Mindest-Vorkommenszahlen für quarterly/yearly (4 statt 3). Was nicht passt → `irregular`.
4. **`is_active`:** keine Buchung seit 2 Intervallen → inaktiv.
5. **`amount_history`:** ein Eintrag pro Betragsänderung (z. B. Netflix 20.90 → 21.90).
6. **Lohn-Erkennung:** grösste **aktive** monatliche Einnahme; daraus der Lohntag (im Datensatz: Tag 25). Bug-Fix: ohne `is_active`-Filter hätte ein seit 2024 inaktiver Arbeitgeber (historisch grösster Betrag) gewonnen.

Ergebnis auf dem Sample-Datensatz: **197 wiederkehrende Zahlungen**.

## Die Pitch-Fix-Geschichte (lehrreich)

Vor dem Pitch zeigte die Jahresansicht "erfundene Fixkosten" — Zufalls-Treffer wie `RATHAUS` (Lücken 7/16/35/49/57/201 Tage, Median zufällig ~30) rutschten als `monthly` durch. Zwei Iterationen:

1. **"Jede Lücke muss passen"** war zu strikt: Netflix hat 40 Lücken, 39 sauber monatlich — **eine** übersprungene Zahlung (61 d) verwarf die ganze Erkennung. Realistische Abos überspringen mal einen Zyklus.
2. **Mehrheitskriterium ≥ 80 %** ist die finale Regel: 0 verdächtige Einträge, Netflix/Spotify/Touring/Bankpaket weiterhin korrekt erkannt.

Bewusst in Kauf genommen: `SWISSCOM` (67 % Trefferquote) und `STEUERVERWALTUNG` (43 %) fallen auf `irregular` zurück — beide vermischen unter derselben Ersttoken-Gruppierung mehrere echte Zahlungsströme (Swisscom: Basisabo + WINGO; Steuern: Zahlungen **und** Rückerstattungen). `irregular` ist hier ehrlicher als eine erzwungene Fixkosten-Markierung.

## `recurring_payment_id()`

Baut die eindeutige ID `merchant::category_main::flow`. Hintergrund ist der wichtigste gefundene Bug des Projekts: 13 Merchant-Strings ("LASTSCHRIFT", "PAYPAL", "MIGROS" …) bezeichnen je 2–4 verschiedene Zahlungsgruppen — mit dem Merchant-Namen als Schlüssel löschte "Netflix kündigen" in der Simulation stillschweigend eine fremde LASTSCHRIFT-Zahlung mit. Siehe [[Glossar]].

## Bekannte Grenzen

- Gruppierung nur über erstes Token + Kategorie, kein Fuzzy-/Betrags-Clustering — Falsch-Zusammenführungen bei generischen Tokens möglich (dokumentiertes Beispiel: "PULVER DANIEL & JUDITH", 5× CHF 950 sauber monatlich, wird mit anderen "PULVER"-Familienmitgliedern zusammengelegt und verliert den Rhythmus).
- Kein Konfidenz-Score, nur die binäre Intervall-Klassifikation.
- Krankenkasse (CSS) wird wegen Betragsschwankungen `irregular`, obwohl das Issue sie in Topf 1 verortet.
