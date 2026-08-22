---
tags: [feature]
status: in-arbeit
issue: 6
---

# Abo-Radar

Spec: [[Issue 6 – Abo-Radar]] · Backend: [[Subscription-Service]] · baut auf [[Recurring-Detection]] auf

## Die Idee

**Fixkosten sind nicht fix.** Der Abo-Radar zeigt auf einer eigenen Seite, welche wiederkehrenden Zahlungen es gibt und wie sie sich über 12 Monate verändert haben — neu dazugekommen, teurer geworden, weggefallen. Bewusst eine eigene View statt Teil des [[Kategorien-Explorer]]s: Abo-Veränderungen sind eine Zeitachse, kein Baum.

## Kernvisualisierung

Eine Zeile pro Abo, ein horizontaler 12-Monats-Balken — in zwei Sekunden lesbar:

```
Netflix   ████████████▓▓▓▓▓▓▓▓      20.90 → 21.90 (ab Juli)
iCloud    ████████████████          endet im August
Spotify             ▓▓▓▓▓▓▓▓        neu ab Juni · 12.95
Miete     ████████████████████      unverändert · 1'820.00
```

Balken = Zahlung erfolgte; Farbwechsel = Preisänderung; frühes Ende = weggefallen; späterer Start = neu. Sortierung: Veränderungen zuerst, dann Unveränderte, jeweils absteigend nach Betrag.

**Kopfzeile** mit drei Kennzahlen (Fixkosten/Monat, Anzahl Veränderungen, Jahresmehrkosten) plus dem Pitch-Satz: *"Bis zum 11. jedes Monats arbeitest du für deine Fixkosten"* (Fixkostenanteil am Monatseinkommen, auf Kalendertage umgelegt).

## Statuslogik (die eigentliche Fachlichkeit)

`ended` / `new` / `variable` / `increased` / `decreased` / `unchanged` — mit dokumentierter **Präzedenz**: `variable` wird **vor** `increased` geprüft (Variationskoeffizient > 10 %), damit eine schwankende Stromrechnung (BKW 192/220/210) nie als Preiserhöhung gemeldet wird. Fehlalarme kosten Vertrauen. Micro-Charges (< CHF 5) landen in einer eingeklappten Gruppe "Testabos und Kleinbeträge". Details: [[Subscription-Service]].

## Status

Backend ist implementiert, liegt aber **uncommitted auf `main`**: `app/api/routes/subscriptions.py`, `app/schemas/subscription.py`, `app/services/subscription_service.py` plus Erweiterungen in `main.py` und `odata/metadata.py`. Abweichend vom Issue-Contract (`GET /api/v1/subscriptions`) ist der Endpunkt als OData-Function **`GET /api/v1/GetSubscriptions`** umgesetzt und liefert die ganze Seite (Liste + Detail-Buchungen + Kopfzeilen-KPIs) in einem Request. Frontend existiert noch nicht.
