import streamlit as st
import re
import requests
import urllib.parse
from datetime import datetime, date
from io import BytesIO
from PyPDF2 import PdfReader
import math

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(page_title="OT5 Valuation Tool", layout="centered")

st.title("OT5 / PSE-4 Private Sector Contribution Tool")
st.caption("Agenda-based labor valuation · Region-based airfare · Multi-event allocation")

# =========================================================
# AIRTABLE CONFIG
# =========================================================
try:
    AIRTABLE_TOKEN = st.secrets["AIRTABLE_TOKEN"]
    AIRTABLE_BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
    AIRTABLE_TABLE = st.secrets["AIRTABLE_OT5_TABLE"]
except Exception:
    st.error("Missing Airtable secrets.")
    st.stop()

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

def airtable_url(table_name):
    return f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(table_name)}"

# =========================================================
# CONSTANTS
# =========================================================
HOURLY_RATES = {
    "Executive / Senior Leadership": 149,
    "Senior Specialist": 131
}

LABOR_MULTIPLIER = 3.5
TRAVEL_DAY_MIE_FACTOR = 0.75
STANDARD_TRAVEL_DAYS = 2

REGION_MATRIX = {
    "North America": 700,
    "Latin America": 900,
    "Asia-Pacific": 1400,
    "Oceania": 1500
}

ECONOMY_REGION = {
    "Australia": "Oceania",
    "Chile": "Latin America",
    "Mexico": "Latin America",
    "United States": "North America",
    "Japan": "Asia-Pacific",
    "Viet Nam": "Asia-Pacific"
}

VALID_FYS = ["FY25", "FY26", "FY27", "FY28", "FY29", "FY30"]

# =========================================================
# LOAD REFERENCE TABLES
# =========================================================
@st.cache_data
def load_reference_table(table_name, primary_field):
    url = airtable_url(table_name)
    records = []
    offset = None

    while True:
        params = {"offset": offset} if offset else {}
        r = requests.get(url, headers=HEADERS, params=params)
        if r.status_code != 200:
            raise Exception(r.text)

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

economy_dict = load_reference_table("Economy Reference List", "Economy")
firm_dict = load_reference_table("OT4 Private Sector Firms", "Firm")
workstream_dict = load_reference_table("Workstream Reference List", "Workstream")
engagement_dict = load_reference_table("Workshop Reference List", "Workshop")

# =========================================================
# SECTION A – SPEAKER & LOE (AUTO)
# =========================================================
st.header("A. Speaker & Level of Effort")

speaker_name = st.text_input("Speaker Name")

agenda_file = st.file_uploader("Upload Agenda PDF", type=["pdf"])

auto_hours = 0.0

if agenda_file and speaker_name:
    reader = PdfReader(BytesIO(agenda_file.read()))
    agenda_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    pattern = r"(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})"
    matches = list(re.finditer(pattern, agenda_text))

    for i, m in enumerate(matches):
        start_t, end_t = m.groups()
        block_start = m.end()
        block_end = matches[i+1].start() if i+1 < len(matches) else len(agenda_text)
        block = agenda_text[block_start:block_end].lower()

        if speaker_name.lower() in block:
            s = datetime.strptime(start_t, "%H:%M")
            e = datetime.strptime(end_t, "%H:%M")
            auto_hours += (e - s).seconds / 3600

auto_hours = float(round(auto_hours, 2))

presentation_hours = st.number_input(
    "Presentation Hours (auto-detected, editable)",
    value=float(auto_hours),
    step=0.25,
    format="%.2f"
)

category = st.selectbox("Speaker Category", list(HOURLY_RATES.keys()))

labor_value = round(
    presentation_hours * LABOR_MULTIPLIER * HOURLY_RATES[category],
    2
)

# =========================================================
# SECTION B – TRAVEL
# =========================================================
st.header("B. Travel")

host_economy = st.selectbox("Host Economy", sorted(economy_dict.keys()))
home_economy = st.selectbox("Home Economy", sorted(economy_dict.keys()))

region = ECONOMY_REGION.get(host_economy, "Asia-Pacific")
airfare = REGION_MATRIX.get(region, 1200)

travel_start = st.date_input("Travel Start")
travel_end = st.date_input("Travel End")

lodging_rate = st.number_input("DOS Lodging Rate", min_value=0.0)
mie_rate = st.number_input("DOS M&IE Rate", min_value=0.0)

days = (travel_end - travel_start).days + 1
nights = max(days - 1, 0)

lodging_total = lodging_rate * nights
mie_total = mie_rate * days
travel_total = airfare + lodging_total + mie_total

# =========================================================
# SECTION C – MULTI EVENT SPLIT
# =========================================================
st.header("C. Engagement Allocation")

selected_engagements = st.multiselect(
    "Select Engagement(s)",
    sorted(engagement_dict.keys())
)

workstream = st.selectbox(
    "Select Workstream",
    sorted(workstream_dict.keys())
)

num_events = max(len(selected_engagements), 1)

allocated_travel = round(travel_total / num_events, 2)
allocated_labor = round(labor_value / num_events, 2)
allocated_total = round(allocated_travel + allocated_labor, 2)

# =========================================================
# SECTION D – POLICY FIELDS
# =========================================================
st.header("D. Contribution Details")

firm_name = st.selectbox("Firm", sorted(firm_dict.keys()))

resource_origin = st.selectbox(
    "Resource Origin",
    ["U.S.-based", "Host Country-based", "Third Country-based"]
)

fiscal_year = st.selectbox("Fiscal Year", VALID_FYS)

# =========================================================
# DASHBOARD
# =========================================================
st.header("E. Review")

col1, col2 = st.columns(2)

with col1:
    st.metric("Labor Contribution (per event)", f"${allocated_labor:,.2f}")
    st.metric("Travel Contribution (per event)", f"${allocated_travel:,.2f}")

with col2:
    st.metric("Total OT5 Value (per event)", f"${allocated_total:,.2f}")
    st.write(f"Fiscal Year: {fiscal_year}")

# =========================================================
# SUBMIT
# =========================================================
if st.checkbox("I confirm this OT5 estimate is correct"):

    if st.button("Submit OT5 Record(s) to Airtable"):

        for engagement in selected_engagements:

            payload = {
                "fields": {
                    "Amount": allocated_total,
                    "Contribution Date": date.today().isoformat(),
                    "Fiscal Year": fiscal_year,
                    "Resource Type": "In-kind",
                    "Resource Origin": resource_origin,
                    "Economy": [economy_dict[host_economy]],
                    "Firm": [firm_dict[firm_name]],
                    "Engagement": [engagement_dict[engagement]],
                    "Workstream": [workstream_dict[workstream]]
                }
            }

            r = requests.post(
                airtable_url(AIRTABLE_TABLE),
                headers=HEADERS,
                json=payload
            )

            if r.status_code not in [200, 201]:
                st.error(r.json())
                st.stop()

        st.success("OT5 record(s) successfully created.")
