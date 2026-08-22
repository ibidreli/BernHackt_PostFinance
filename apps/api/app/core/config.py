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
