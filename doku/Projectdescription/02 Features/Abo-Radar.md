---
tags: [feature]
status: verworfen
issue: 6
---

> [!important] Aus dem Plan gestrichen (22.08.2026, [[Sollstatus]])
> Der Abo-Radar wird **nicht mehr gebaut** — weder als eigene Seite noch als Backend-Neubau. Die Fixkosten-Sicht lebt als Teilmenge in der Prognose weiter (Liste aus `RecurringPayments`, Kündigungs-Szenarien). Diese Notiz und [[Subscription-Service]] bleiben als Archiv/Referenz erhalten.

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

> [!warning] Backend-Quellcode verloren (Stand 22.08.2026)
> Die Implementierung (`app/api/routes/subscriptions.py`, `app/schemas/subscription.py`, `app/services/subscription_service.py` plus Erweiterungen in `main.py` und `odata/metadata.py`) lag nur **uncommitted** im Arbeitsverzeichnis und wurde nie eingecheckt — die Quelldateien existieren nicht mehr. Übrig ist einzig kompilierter Bytecode in `__pycache__` (`subscription_service.cpython-312.pyc` u. a.). Wiederherstellung per Dekompilierung oder Neubau nach [[Subscription-Service]] ist ein separates Vorhaben; jene Notiz bleibt als Spezifikation gültig.

Geplanter Endpunkt (abweichend vom Issue-Contract `GET /api/v1/subscriptions`): OData-Function **`GET /api/v1/GetSubscriptions`**, die die ganze Seite (Liste + Detail-Buchungen + Kopfzeilen-KPIs) in einem Request liefert. Frontend existiert noch nicht — `apps/web/src/app/pages/abo-radar/` ist ein leeres Verzeichnis ohne Route.
