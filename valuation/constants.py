"""
constants.py

Fixed policy parameters for OT5 / PSE-4 private sector valuation.
These values are established by the approved methodology and
remain fixed for the duration of the project unless formally revised.
"""

# =========================================================
# APPLICATION / GOVERNANCE METADATA
# =========================================================
APP_VERSION = "v1.0.0"
METHODOLOGY_DOC = "docs/ot5_methodology.md"

# =========================================================
# STANDARDIZED HOURLY RATES (USD)
# =========================================================
HOURLY_RATES = {
    "Executive / Senior Leadership": 149,
    "Senior Specialist": 131
}

# =========================================================
# LABOR TIME SCALING
# =========================================================
# Total labor hours = presentation hours × TOTAL_LABOR_MULTIPLIER
# (presentation + prep + follow-up)
TOTAL_LABOR_MULTIPLIER = 3.5

# =========================================================
# TRAVEL ASSUMPTIONS
# =========================================================
# Standardized number of travel days per trip
STANDARD_TRAVEL_DAYS = 2

# Percentage of M&IE applied on travel days
TRAVEL_DAY_MIE_RATE = 0.75
