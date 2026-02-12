import streamlit as st
import re
import requests
import urllib.parse
from datetime import datetime, date
from io import BytesIO
from PyPDF2 import PdfReader

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(page_title="OT5 Valuation Dashboard", layout="wide")
st.title("OT5 / PSE-4 Private Sector Contribution Dashboard")
st.caption("Agenda-based valuation • Trip-level allocation • Engagement-linked reporting")

# =========================================================
# AIRTABLE CONFIG
# =========================================================
try:
    AIRTABLE_TOKEN = st.secrets["AIRTABLE_TOKEN"]
    AIRTABLE_BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
    AIRTABLE_OT5_TABLE = st.secrets["AIRTABLE_OT5_TABLE"]
except:
    st.error("Missing Airtable secrets.")
    st.stop()

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(AIRTABLE_OT5_TABLE)}"

# =========================================================
# CONSTANTS
# =========================================================
HOURLY_RATES = {
    "Executive / Senior Leadership": 149,
    "Senior Specialist": 131
}

LABOR_MULTIPLIER = 3.5
AIRFARE_BANDS = {
    "Domestic": 550,
    "Regional": 700,
    "Intercontinental": 1400
}

# =========================================================
# LOAD REFERENCE TABLES
# =========================================================
@st.cache_data
def load_reference_table(table_name, primary_field):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(table_name)}"
    records = []
    offset = None

    while True:
        params = {"offset": offset} if offset else {}
        r = requests.get(url, headers=HEADERS, params=params)
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    return {
        rec["fields"].get(primary_field): rec["id"]
        for rec in records
        if rec["fields"].get(primary_field)
    }

@st.cache_data
def load_workshops_with_workstream():
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote('Workshop Reference List')}"
    records = []
    offset = None

    while True:
        params = {"offset": offset} if offset else {}
        r = requests.get(url, headers=HEADERS, params=params)
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    workshop_dict = {}

    for rec in records:
        workshop_name = rec["fields"].get("Workshop")
        workstream_link = rec["fields"].get("Workstream")

        if workshop_name:
            workshop_dict[workshop_name] = {
                "id": rec["id"],
                "workstream_id": workstream_link[0] if workstream_link else None
            }

    return workshop_dict

economy_dict = load_reference_table("Economy Reference List", "Economy")
firm_dict = load_reference_table("OT4 Private Sector Firms", "Firm")
workshop_dict = load_workshops_with_workstream()

# =========================================================
# HELPERS
# =========================================================
def calculate_labor(category, hours):
    total_hours = round(hours * LABOR_MULTIPLIER, 2)
    return round(total_hours * HOURLY_RATES[category], 2)

def derive_fy(d):
    fy = d.year + 1 if d.month >= 10 else d.year
    return f"FY{str(fy)[-2:]}"

# =========================================================
# SECTION A: SPEAKER
# =========================================================
st.header("A. Speaker Information")

speaker_name = st.text_input("Speaker Name")
presentation_hours = st.number_input("Total Presentation Hours", min_value=0.0, step=0.25)

category = st.selectbox("Speaker Category", list(HOURLY_RATES.keys()))

labor_total = calculate_labor(category, presentation_hours)

# =========================================================
# SECTION B: TRIP
# =========================================================
st.header("B. Trip-Level Travel")

trip_type = st.selectbox("Trip Type", list(AIRFARE_BANDS.keys()))
airfare = AIRFARE_BANDS[trip_type]

travel_start = st.date_input("Travel Start Date")
travel_end = st.date_input("Travel End Date")

lodging_rate = st.number_input("Lodging Rate (USD)", min_value=0.0)

days = (travel_end - travel_start).days + 1
nights = max(days - 1, 0)
travel_total = airfare + (lodging_rate * nights)

# =========================================================
# SECTION C: ENGAGEMENTS
# =========================================================
st.header("C. Engagement Allocation")

engagements_selected = st.multiselect(
    "Select Engagement(s)",
    sorted(workshop_dict.keys())
)

num_engagements = len(engagements_selected) if engagements_selected else 1
travel_per_engagement = round(travel_total / num_engagements, 2)

st.info(f"Travel will be split evenly across {num_engagements} engagement(s).")

# Auto-display derived workstreams
derived_workstreams = set()

for e in engagements_selected:
    ws_id = workshop_dict[e]["workstream_id"]
    if ws_id:
        derived_workstreams.add(ws_id)

st.write("Derived Workstream(s):")
st.write(derived_workstreams if derived_workstreams else "None Linked")

# =========================================================
# SECTION D: CLASSIFICATION
# =========================================================
st.header("D. Classification")

firm_name = st.selectbox("Firm", sorted(firm_dict.keys()))
host_economy = st.selectbox("Economy", sorted(economy_dict.keys()))
resource_origin = st.selectbox(
    "Resource Origin",
    ["U.S.-based", "Host Country-based", "Third Country-based"]
)

fiscal_year = derive_fy(travel_start)

# =========================================================
# SECTION E: REVIEW
# =========================================================
st.header("E. Review & Submit")

col1, col2 = st.columns(2)

with col1:
    st.metric("Total Labor (Trip)", f"${labor_total:,.2f}")
    st.metric("Travel per Engagement", f"${travel_per_engagement:,.2f}")

with col2:
    total_per_engagement = labor_total + travel_per_engagement
    st.metric("Total per Engagement", f"${total_per_engagement:,.2f}")
    st.metric("Fiscal Year", fiscal_year)

# =========================================================
# SUBMIT
# =========================================================
if st.checkbox("I confirm this OT5 allocation is correct"):
    if st.button("Submit OT5 Records"):

        for e in engagements_selected:

            payload = {
                "fields": {
                    "Amount": total_per_engagement,
                    "Contribution Date": travel_start.isoformat(),
                    "Fiscal Year": fiscal_year,
                    "Resource Type": "In-kind",
                    "Resource Origin": resource_origin,
                    "Economy": [economy_dict[host_economy]],
                    "Firm": [firm_dict[firm_name]],
                    "Engagement": [workshop_dict[e]["id"]],
                    "Workstream": [workshop_dict[e]["workstream_id"]]
                }
            }

            requests.post(AIRTABLE_URL, headers=HEADERS, json=payload)

        st.success("OT5 records successfully created.")
