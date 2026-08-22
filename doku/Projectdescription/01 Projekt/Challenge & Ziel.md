---
tags: [projekt]
---

# Challenge & Ziel

Quelle im Repo: `CHALLENGE.md` · Challenge-Seite: [bernhackt.ch/challenges/2026-beyond-the-list](https://www.bernhackt.ch/challenges/2026-beyond-the-list)

## Das Problem laut PostFinance

Digital Banking zeigt Finanztransaktionen primär als **Listen**. Das schafft Transparenz über einzelne Buchungen, aber kaum Kontext: Muster, Veränderungen und finanzielle Entwicklungen bleiben verborgen. Nutzer:innen bekommen Daten, aber wenig Unterstützung, sie zu verstehen und für Entscheidungen zu nutzen.

Gesucht: ein Ansatz, der Finanzdaten in **verständliche, relevante und wertvolle Informationen** verwandelt — Orientierung, Übersicht, fundierte Entscheidungen.

## Die Antwort dieses Projekts

Die App (Arbeitstitel im README: *rhylog*) ersetzt die Liste durch vier ineinandergreifende Sichten — jede beantwortet eine Frage, die sich Nutzer:innen tatsächlich stellen:

1. **"Wie viel kann ich noch ausgeben?"** → [[Zukunftsprognose & Simulation]]: ein ehrlicher Korridor statt einer Punktzahl mit falscher Genauigkeit, ein Engpass-Datum, und Szenarien zum Durchspielen (Abo kündigen, Miete +200).
2. **"Wohin fliesst mein Geld?"** → [[Kategorien-Explorer]]: hierarchisches Circle Packing, Kreisfläche = Franken-Betrag, zoombar bis zur einzelnen Buchung.
3. **"Was hat sich bei meinen Fixkosten verändert?"** → [[Abo-Radar]]: Fixkosten sind nicht fix — neu, teurer, weggefallen auf einen Blick.
4. **"Kann ich mir das leisten?"** → [[Future-Me Chatbot]]: natürlichsprachige Fragen, belastbare Antworten. Das LLM versteht und formuliert; **gerechnet wird deterministisch**.

## Rote Fäden durch alle Features

- **Ehrlichkeit vor Präzision:** Band statt Linie, `assumptions` in jeder Antwort ("woher kommen diese Zahlen?"), bewusst **keine Zins-/Renditeannahme** — vor einer Bank-Jury wäre eine unbelegte Rendite ein Eigentor.
- **Ein Rechenkern:** [[Forecast-Service]] wird von Prognose-UI *und* Chatbot benutzt; kein Feature rechnet doppelt.
- **Pitch-tauglich:** Presets statt Formulare, Animationen unter einer Sekunde, Offline-Fallback für den Chatbot — alles auf den Drei-Minuten-Pitch ausgelegt.
