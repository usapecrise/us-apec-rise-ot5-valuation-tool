import streamlit as st
from datetime import date
from dotenv import load_dotenv
import os

load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")

# =========================================================
# APPLICATION METADATA
# =========================================================
APP_VERSION = "v1.0.0"
METHODOLOGY_DOC = "docs/ot5_methodology.md"

# =========================================================
# STREAMLIT CONFIG
# =========================================================
st.set_page_config(
    page_title="OT5 / PSE-4 Valuation Tool",
    layout="centered"
)

st.title("OT5 / PSE-4 Private Sector Valuation Tool")
st.caption(
    f"OT5 Valuation Tool {APP_VERSION} — implements {METHODOLOGY_DOC}"
)

st.divider()

# =========================================================
# POLICY CONSTANTS (FIXED FOR PROJECT LIFE)
# =========================================================
HOURLY_RATES = {
    "Executive / Senior Leadership": 149,
    "Senior Specialist": 131
}

TOTAL_LABOR_MULTIPLIER = 3.5        # Prep (2x) + Follow-up (0.5x) + Presentation (1x)
STANDARD_TRAVEL_DAYS = 2            # Outbound + return
TRAVEL_DAY_MIE_RATE = 0.75          # 75% M&IE on travel days

# =========================================================
# CALCULATION FUNCTIONS
# =========================================================
def calculate_labor(category: str, presentation_hours: float):
    hourly_rate = HOURLY_RATES[category]
    total_labor_hours = presentation_hours * TOTAL_LABOR_MULTIPLIER
    labor_value = hourly_rate * total_labor_hours

    return {
        "hourly_rate": hourly_rate,
        "presentation_hours": presentation_hours,
        "total_labor_hours": total_labor_hours,
        "labor_value": round(labor_value, 2)
    }


def calculate_travel(
    airfare: float,
    lodging_rate: float,
    mie_rate: float,
    start_date: date,
    end_date: date,
    workshops_on_trip: int
):
    days = (end_date - start_date).days + 1
    nights = max(days - 1, 0)

    lodging_cost = lodging_rate * nights
    mie_full_days = mie_rate * max(days - STANDARD_TRAVEL_DAYS, 0)
    mie_travel_days = mie_rate * TRAVEL_DAY_MIE_RATE * STANDARD_TRAVEL_DAYS

    total_travel_cost = airfare + lodging_cost + mie_full_days + mie_travel_days
    allocated_travel = total_travel_cost / workshops_on_trip

    return {
        "days": days,
        "nights": nights,
        "lodging_cost": round(lodging_cost, 2),
        "mie_full_days": round(mie_full_days, 2),
        "mie_travel_days": round(mie_travel_days, 2),
        "total_travel_cost": round(total_travel_cost, 2),
        "allocated_travel": round(allocated_travel, 2)
    }

# =========================================================
# STREAMLIT CONFIG
# =========================================================
st.set_page_config(
    page_title="OT5 / PSE-4 Valuation Tool",
    layout="centered"
)

st.title("OT5 / PSE-4 Private Sector Valuation Tool")
st.caption(
    f"OT5 Valuation Tool {APP_VERSION} — implements {METHODOLOGY_DOC}"
)

st.divider()

# =========================================================
# SPEAKER DETAILS
# =========================================================
st.subheader("Speaker Details")

speaker_name = st.text_input("Speaker Name")
organization = st.text_input("Organization")

category = st.selectbox(
    "Professional Category",
    options=list(HOURLY_RATES.keys()),
    help="Final category assignment is a staff determination."
)

presentation_hours = st.number_input(
    "Total Presentation Hours (sum of all sessions)",
    min_value=0.0,
    step=0.25
)

# =========================================================
# LABOR VALUATION
# =========================================================
labor = calculate_labor(category, presentation_hours)

st.divider()
st.subheader("Labor Valuation")

st.write(f"**Hourly Rate:** ${labor['hourly_rate']}")
st.write(f"**Total Labor Hours:** {labor['total_labor_hours']}")
st.write(f"**Labor Contribution:** ${labor['labor_value']:,.2f}")

# =========================================================
# TRAVEL VALUATION
# =========================================================
st.divider()
st.subheader("Travel Valuation")

travel_eligible = st.checkbox(
    "Travel was privately funded and eligible for OT5 valuation",
    help="Do not include travel reimbursed by USG or another donor."
)

allocated_travel_value = 0.0
travel_details = None

if travel_eligible:
    airfare = st.number_input(
        "Estimated Round-Trip Airfare (USD)",
        min_value=0.0
    )

    lodging_rate = st.number_input(
        "DOS Lodging Rate per Night (USD)",
        min_value=0.0
    )

    mie_rate = st.number_input(
        "DOS M&IE Rate per Day (USD)",
        min_value=0.0
    )

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Trip Start Date")
    with col2:
        end_date = st.date_input("Trip End Date")

    workshops_on_trip = st.number_input(
        "Number of US APEC–RISE Workshops on This Trip",
        min_value=1,
        step=1
    )

    travel_details = calculate_travel(
        airfare,
        lodging_rate,
        mie_rate,
        start_date,
        end_date,
        workshops_on_trip
    )

    allocated_travel_value = travel_details["allocated_travel"]

    st.write(f"**Total Travel Cost:** ${travel_details['total_travel_cost']:,.2f}")
    st.write(
        f"**Allocated Travel per Workshop:** "
        f"${allocated_travel_value:,.2f}"
    )

# =========================================================
# TOTAL OT5 VALUE
# =========================================================
st.divider()
st.subheader("Total OT5 Contribution")

total_ot5_value = labor["labor_value"] + allocated_travel_value

st.metric(
    label="Total OT5 Value (USD)",
    value=f"${total_ot5_value:,.2f}"
)

# =========================================================
# DOCUMENTATION & NOTES
# =========================================================
st.divider()
st.subheader("Documentation and Notes")

category_rationale = st.text_area(
    "Category Assignment Rationale",
    help="Brief justification based on title, experience, or bio."
)

documentation_links = st.text_area(
    "Documentation Links",
    help="Agenda, LinkedIn profile, CV, Kayak fare screenshot, DOS per diem source."
)

# =========================================================
# DATA QUALITY GUARDRAILS
# =========================================================
st.divider()
st.subheader("Data Quality Checks")

warnings = []

if presentation_hours == 0:
    warnings.append("Presentation hours are zero.")

if travel_eligible:
    if airfare == 0:
        warnings.append("Travel marked eligible but airfare is zero.")
    if start_date == end_date:
        warnings.append("Trip duration is one day; verify travel dates.")

if not category_rationale.strip():
    warnings.append("Category assignment rationale is missing.")

if not documentation_links.strip():
    warnings.append("Documentation links are missing.")

if warnings:
    for w in warnings:
        st.warning(w)
else:
    st.success("All required inputs appear complete.")

st.caption(
    "Values generated by this tool should be entered into the "
    "Airtable ‘OT5 Private Sector Resources’ table as the system of record."
