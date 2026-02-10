import streamlit as st
import requests
from datetime import date
from dotenv import load_dotenv
import os

# =========================================================
# ENVIRONMENT
# =========================================================
load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_OT5_TABLE = os.getenv("AIRTABLE_OT5_TABLE")

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json"
}

# =========================================================
# APP METADATA
# =========================================================
APP_VERSION = "v1.0.0"
INDICATOR_ID = "OT5"

# =========================================================
# CONSTANTS (POLICY-LOCKED)
# =========================================================
HOURLY_RATES = {
    "Executive / Senior Leadership": 149,
    "Senior Specialist": 131
}

LABOR_MULTIPLIER = 3.5
STANDARD_TRAVEL_DAYS = 2
TRAVEL_DAY_MIE_FACTOR = 0.75

RESOURCE_TYPE = "In-kind"

FAO_OPTIONS = [
    "Peace and Security",
    "Democracy",
    "Human Rights and Governance",
    "Health",
    "Education",
    "Economic Growth (Other)",
    "Agriculture and Food Security",
    "Water, Sanitation, and Hygiene",
    "Water Management",
    "Gender",
    "Youth",
    "Inclusive Development"
]

# =========================================================
# HELPERS
# =========================================================
@st.cache_data(ttl=3600)
def fetch_airtable_options(table_name):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}"
    options = set()
    offset = None

    while True:
        params = {"offset": offset} if offset else {}
        r = requests.get(url, headers=HEADERS, params=params)
        r.raise_for_status()
        data = r.json()

        for record in data["records"]:
            value = next(iter(record["fields"].values()), None)
            if value:
                options.add(value)

        offset = data.get("offset")
        if not offset:
            break

    return sorted(options)


def derive_usg_fiscal_year(d):
    return d.year + 1 if d.month >= 10 else d.year


def derive_resource_origin(firm_economy, assistance_location):
    if firm_economy == "United States":
        return "U.S.-based"
    if firm_economy == assistance_location:
        return "Host Country-based"
    return "Third Country-based"


def calculate_labor(category, presentation_hours):
    return round(HOURLY_RATES[category] * presentation_hours * LABOR_MULTIPLIER, 2)


def calculate_travel(airfare, lodging_rate, mie_rate, start, end, workshops):
    days = (end - start).days + 1
    nights = max(days - 1, 0)

    lodging = lodging_rate * nights
    mie_full = mie_rate * max(days - STANDARD_TRAVEL_DAYS, 0)
    mie_travel = mie_rate * TRAVEL_DAY_MIE_FACTOR * STANDARD_TRAVEL_DAYS

    total = airfare + lodging + mie_full + mie_travel
    return round(total / workshops, 2)


def submit_to_airtable(payload):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_OT5_TABLE}"
    r = requests.post(url, headers=HEADERS, json={"fields": payload})
    r.raise_for_status()
    return r.json()

# =========================================================
# STREAMLIT CONFIG
# =========================================================
st.set_page_config(
    page_title="OT5 Valuation Tool",
    layout="centered"
)

st.title("OT5 / PSE-4 Private Sector Valuation Tool")
st.caption(f"Version {APP_VERSION} — Indicator {INDICATOR_ID}")
st.divider()

# =========================================================
# DROPDOWN DATA
# =========================================================
economy_options = fetch_airtable_options("Economy Reference List")
workstream_options = fetch_airtable_options("Workstream Reference List")
engagement_options = fetch_airtable_options("Workshop Reference List")

# =========================================================
# A. ELIGIBILITY
# =========================================================
st.subheader("A. Private Sector Eligibility")

eligible = st.checkbox("This contribution is from a private sector entity eligible under OT5.")
if not eligible:
    st.stop()

firm = st.selectbox("Firm", firm_options)
firm_economy = st.selectbox("Firm Home Economy", economy_options)

assistance_location = st.selectbox(
    "Assistance Location (Host Economy)",
    economy_options,
    help="Economy where the activity/workshop took place."
)

resource_origin = derive_resource_origin(firm_economy, assistance_location)
st.markdown(f"**Resource Origin (derived):** {resource_origin}")

st.divider()

# =========================================================
# B. CONTEXT
# =========================================================
st.subheader("B. Contribution Context")

engagement = st.selectbox("Engagement", engagement_options)
workstream = st.selectbox("Workstream", workstream_options)

faos = st.multiselect(
    "U.S. FAOs Addressed",
    FAO_OPTIONS,
    default=["Economic Growth (Other)"]
)

contribution_date = st.date_input("Contribution Date (Agenda Date)")
fiscal_year = f"FY {derive_usg_fiscal_year(contribution_date)}"

st.markdown(f"**Fiscal Year (derived):** {fiscal_year}")

st.divider()

# =========================================================
# C. VALUATION
# =========================================================
st.subheader("C. Valuation")

presentation_hours = st.number_input(
    "Presentation Hours (agenda-based)",
    min_value=0.0,
    step=0.25
)

category = st.selectbox("Professional Category", list(HOURLY_RATES.keys()))
labor_value = calculate_labor(category, presentation_hours)

st.markdown(f"**Labor Contribution:** ${labor_value:,.2f}")

st.markdown("### Travel")

airfare = st.number_input("Airfare (USD)", min_value=0.0)
lodging_rate = st.number_input("Lodging Rate per Night", min_value=0.0)
mie_rate = st.number_input("M&IE Rate per Day", min_value=0.0)

col1, col2 = st.columns(2)
with col1:
    travel_start = st.date_input("Travel Start Date")
with col2:
    travel_end = st.date_input("Travel End Date")

workshops_on_trip = st.number_input(
    "Number of US APEC–RISE Workshops on This Trip",
    min_value=1,
    step=1
)

travel_value = calculate_travel(
    airfare, lodging_rate, mie_rate,
    travel_start, travel_end,
    workshops_on_trip
)

st.markdown(f"**Allocated Travel Contribution:** ${travel_value:,.2f}")

total_ot5 = round(labor_value + travel_value, 2)

st.divider()

# =========================================================
# D. REVIEW & SUBMIT
# =========================================================
st.subheader("D. Review & Submit")

st.metric("Total OT5 Contribution (USD)", f"${total_ot5:,.2f}")

payload = {
    "amount": total_ot5,
    "economy": firm_economy,
    "workstream": workstream,
    "U.S. FAOs addressed": faos,
    "resource type": RESOURCE_TYPE,
    "resource origin": resource_origin,
    "firm": firm,
    "engagement": engagement,
    "indicator id": INDICATOR_ID,
    "fiscal year": fiscal_year,
    "contribution date": contribution_date.isoformat()
}

st.json(payload)

if st.button("Submit to Airtable"):
    try:
        submit_to_airtable(payload)
        st.success("OT5 record successfully submitted to Airtable.")
    except Exception as e:
        st.error(f"Submission failed: {e}")
