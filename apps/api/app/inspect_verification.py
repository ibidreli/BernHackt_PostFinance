"""Ad-hoc verification for T10 (verification_service). Run via:

    docker compose run --rm api python -m app.inspect_verification
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from app.data.data_personal import load_raw_transactions
from app.repositories.balance_repository import BalanceRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.assistant import AssistantAskRequest, AssistantFacts, Lever
from app.services.assistant_service import ask
from app.services.classification import classify_transactions
from app.services.conversation_state import ConversationStore
from app.services.recurring_detection import detect_recurring_payments
from app.services.verification_service import verify_answer_text

raw = load_raw_transactions()
repo = TransactionRepository.from_raw(raw)
balance_repo = BalanceRepository(repo.all())
recurring = detect_recurring_payments(repo.all())
classifications = classify_transactions(repo.all(), recurring)


def line(title: str) -> None:
    print(f"\n=== {title} ===")


# --- 1. Der historische Bug: reproduziert und verifiziert, dass er JETZT gefangen wird ---
line("1. Historischer Bug: 'CHF 1' für buffer_after_months=1.1 (Monate!)")
facts = AssistantFacts(target_chf=10000.0, projected_chf=12445.1, buffer_after_months=1.1, wait_months=19)
bad_text = "Das Ziel ist knapp erreichbar. Der Restpuffer beträgt nur CHF 1."
ok = verify_answer_text(bad_text, facts, [], "5y")
print(f"'{bad_text}' -> verify_answer_text = {ok}")
assert ok is False, "Der historische Bug MUSS jetzt erkannt werden"
print("OK: der historische Bug wird jetzt zuverlässig erkannt")

# --- 2. Korrekter Text (gleiche facts) sollte durchgehen ------------------
line("2. Korrekter Text (gleiche facts, richtige Einheit)")
good_text = "Das Ziel ist knapp erreichbar. Der Puffer liegt bei rund einem Monat, du müsstest noch 19 Monate warten."
ok2 = verify_answer_text(good_text, facts, [], "5y")
print(f"'{good_text}' -> verify_answer_text = {ok2}")
assert ok2 is True
print("OK: korrekter Text besteht die Prüfung")

# --- 3. Erfundene CHF-Zahl wird erkannt -----------------------------------
line("3. Erfundene CHF-Zahl (nicht in facts)")
invented_text = "Du hast CHF 99'999 zur Verfügung."
ok3 = verify_answer_text(invented_text, facts, [], "5y")
print(f"'{invented_text}' -> verify_answer_text = {ok3}")
assert ok3 is False
print("OK: erfundene Zahl wird erkannt")

# --- 4. Rundung auf 100 bei 5y/10y wird toleriert -------------------------
line("4. Gerundete Zahl bei 5y wird toleriert (facts=12445.1 -> Text nennt 12400)")
rounded_text = "Du hast voraussichtlich CHF 12'400 zur Verfügung."
ok4 = verify_answer_text(rounded_text, facts, [], "5y")
print(f"'{rounded_text}' -> verify_answer_text = {ok4}")
assert ok4 is True
# Aber bei present/1y (keine Rundung erlaubt) sollte dieselbe Abweichung auffallen:
ok4b = verify_answer_text(rounded_text, facts, [], "present")
print(f"gleicher Text bei horizon=present -> verify_answer_text = {ok4b}")
assert ok4b is False
print("OK: Rundungstoleranz greift nur bei 5y/10y, nicht bei present/1y")

# --- 5. Hebel-Zahlen werden korrekt erkannt -------------------------------
line("5. Hebel-Beträge werden als gültig erkannt")
lever = Lever(category="Gastronomie", monthly_avg_chf=267.22, potential_chf=129.67)
lever_text = "Ein möglicher Hebel: bei Gastronomie liegt das Potenzial bei CHF 130."
ok5 = verify_answer_text(lever_text, facts, [lever], "present")
print(f"'{lever_text}' -> verify_answer_text = {ok5}")
assert ok5 is True
print("OK: Hebel-Beträge werden korrekt als gültig erkannt")

# --- 6. Echter End-to-End-Test: LLM-Text wird künstlich kaputt gemacht ---
line("6. End-to-End: formulate_answer() liefert absichtlich falschen Text -> Fallback greift")
with patch("app.services.assistant_service.formulate_answer", return_value="Du hast CHF 12'345'678 zur Verfügung, was für immer reicht."):
    store = ConversationStore()
    req = AssistantAskRequest(message="Was wäre, wenn ich Netflix kündige?", horizon="5y")
    resp = ask(req, repo.all(), recurring, classifications, balance_repo, store, as_of=date(2026, 8, 22), mode="live")
    print(f"answer: {resp.answer}")
    assert "12'345'678" not in resp.answer, "Der erfundene Betrag darf NICHT im finalen Text landen"
    assert resp.source == "live", "source bleibt 'live' - die Berechnung war live, nur der Text kam aus dem Template"
print("OK: erfundener Text wurde verworfen, Fallback auf Template lieferte eine korrekte Antwort")

# --- 7. Regressionstest: echte LLM-Antworten sollten NICHT fälschlich verworfen werden ---
line("7. Regressionstest: 5 echte Fragen, LLM-Text darf nicht grundlos verworfen werden")
import logging  # noqa: E402

rejected = []
handler_logs = []

class _CaptureHandler(logging.Handler):
    def emit(self, record):
        handler_logs.append(record.getMessage())

logger = logging.getLogger("app.services.assistant_service")
logger.addHandler(_CaptureHandler())
logger.setLevel(logging.WARNING)

questions = [
    ("Kann ich mir in 5 Jahren ein Auto für 30000 leisten?", "present"),
    ("Was wäre, wenn ich Netflix kündige?", "5y"),
    ("Wann habe ich 10000 zusammen?", "5y"),
    ("Was wäre, wenn ich monatlich 50 mehr für Fitness ausgebe?", "1y"),
    ("Kann ich mir jetzt Kopfhörer für 300 leisten?", "present"),
]
for msg, horizon in questions:
    store = ConversationStore()
    req = AssistantAskRequest(message=msg, horizon=horizon)
    resp = ask(req, repo.all(), recurring, classifications, balance_repo, store, as_of=date(2026, 8, 22), mode="live")
    print(f"'{msg}' -> status={resp.status}")

print(f"\nFallback-Warnungen während der 5 echten Fragen: {len(handler_logs)}")
for log in handler_logs:
    print(" -", log)
print("(0 ist der Idealfall - jede Warnung hier verdient manuelle Prüfung, ist aber kein automatischer Fehlschlag,")
print(" da echte LLM-Formulierungen gelegentlich legitim vom Zahlenabgleich abweichen können, z.B. durch Rundung)")

print("\nAlle Checks bestanden.")
