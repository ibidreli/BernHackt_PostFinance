"""Runtime configuration.

Deliberately plain `os.environ` reads instead of `pydantic-settings` - the
service only has a handful of tunable values and an extra dependency isn't
worth it for a hackathon backend.
"""

from __future__ import annotations

import os
from pathlib import Path

# Path to the bank export CSV. Mounted as a read-only volume in
# docker-compose.yml so the file can be swapped without a rebuild.
CSV_PATH = Path(os.environ.get("CSV_PATH", "/data/data_personal.csv"))
CSV_DELIMITER = os.environ.get("CSV_DELIMITER", ";")
CSV_ENCODING = os.environ.get("CSV_ENCODING", "utf-8-sig")

# Forecast defaults (Feature: Zukunftsprognose & Szenario-Simulation).
# CHF buffer below which a day counts as "tight". Overridable per profile
# later; CHF 0 per issue default.
DEFAULT_BUFFER_CHF = float(os.environ.get("DEFAULT_BUFFER_CHF", "0"))

# Outlier detection threshold: a booking counts as an outlier if it exceeds
# this multiple of its category's median. Kept configurable so it can be
# calibrated against real data (see issue's "offene Fragen").
OUTLIER_MEDIAN_MULTIPLIER = float(os.environ.get("OUTLIER_MEDIAN_MULTIPLIER", "3"))

# Additional absolute floor for the multiplier check above - a booking must
# clear BOTH the multiplier AND this amount to count as an outlier. Without
# it, high-frequency/wide-variance categories (e.g. "Supermärkte", where lots
# of small snack purchases pull the median down to a few CHF) flag ordinary
# larger-than-usual bookings as outliers just because they clear 3x a tiny
# median - verified against the sample data: without this floor, ~12% of all
# supermarket bookings (mostly perfectly normal grocery runs) were wrongly
# excluded from the forecast baseline. CHF 100 is a starting point in the
# spirit of the issue's own outlier examples (Reisen, Velokauf, Steuern -
# all inherently >CHF 100), not a calibrated value.
OUTLIER_MIN_ABSOLUTE_CHF = float(os.environ.get("OUTLIER_MIN_ABSOLUTE_CHF", "100"))

# Minimum number of occurrences in the last 12 months for a category to be
# treated as "regular" rather than an outlier.
OUTLIER_MIN_OCCURRENCES_12M = int(os.environ.get("OUTLIER_MIN_OCCURRENCES_12M", "3"))

# Window used for the median/percentile baseline of variable spending.
VARIABLE_BASELINE_MONTHS = int(os.environ.get("VARIABLE_BASELINE_MONTHS", "6"))

# Alerts (Feature: Auffaelligkeiten). Kept separate from the forecast
# thresholds so the frontend can tune alert sensitivity without changing
# projection behaviour.
ALERT_DUPLICATE_MIN_CHF = float(os.environ.get("ALERT_DUPLICATE_MIN_CHF", "20"))
ALERT_SPIKE_MULTIPLIER = float(os.environ.get("ALERT_SPIKE_MULTIPLIER", "2.0"))
ALERT_SPIKE_MIN_DELTA_CHF = float(os.environ.get("ALERT_SPIKE_MIN_DELTA_CHF", "150"))
ALERT_SPIKE_MIN_MONTHS = int(os.environ.get("ALERT_SPIKE_MIN_MONTHS", "3"))

# --- Future-Me Chatbot (Feature #5) -------------------------------------

# "live": real OpenAI calls. "cached": zero external calls at all - a fixed
# set of demo questions is recognized by pattern-matching (not an LLM call)
# and answered with a canned formulation; `forecast_service` still computes
# real numbers either way, only the *wording* is canned. See
# ASSISTANT_STATUS.md, T9.
ASSISTANT_MODE = os.environ.get("ASSISTANT_MODE", "live")

# Read from apps/api/app/.env via docker-compose's `env_file:` (see
# docker-compose.yml) - never baked into the image, see .dockerignore.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Applies to *each* of the two LLM calls (extraction, formulation)
# individually, not the request as a whole. On timeout the endpoint returns
# an explicit error telling the user something went wrong - deliberately no
# silent template fallback that would look like a normal answer (see
# ASSISTANT_STATUS.md, T9 - this was a specific product decision, not the
# issue's original wording).
ASSISTANT_LLM_TIMEOUT_SECONDS = float(os.environ.get("ASSISTANT_LLM_TIMEOUT_SECONDS", "8"))

# Long-horizon (1y/5y/10y) default assumptions - overridable per-request via
# `assumptions` in the request body. `savings_rate_pct` has no numeric
# default here: `None` means "compute from history", per the issue.
SALARY_GROWTH_DEFAULT_PCT = float(os.environ.get("SALARY_GROWTH_DEFAULT_PCT", "1.0"))
INFLATION_DEFAULT_PCT = float(os.environ.get("INFLATION_DEFAULT_PCT", "1.5"))

# Ab diesem Betrag gilt eine `affordability`-Frage als "grosse Anschaffung"
# (issue: "Grosse Anschaffung ohne Zahlungsart" löst die Bar/Leasing-
# Rückfrage aus, T3). Unkalibrierter Startwert, gleiche Kategorie wie
# OUTLIER_MIN_ABSOLUTE_CHF oben - eine Plausibilitätsgrenze, keine
# fachlich hergeleitete Zahl.
LARGE_PURCHASE_THRESHOLD_CHF = float(os.environ.get("LARGE_PURCHASE_THRESHOLD_CHF", "3000"))

# Puffer-Schwelle for the `tight` state: below this many months of variable
# spending, an otherwise-reachable goal counts as "knapp" instead of "ja".
# Issue's own "offene Frage": explicitly a starting value pending
# calibration against real data, not a settled number - see
# ASSISTANT_STATUS.md.
TIGHT_BUFFER_MONTHS = float(os.environ.get("TIGHT_BUFFER_MONTHS", "3"))
