import streamlit as st
import re
import requests
import urllib.parse
from datetime import datetime, date
from io import BytesIO
from PyPDF2 import PdfReader

# =========================================================
# STREAMLIT CONFIG
# =========================================================
st.set_page_config(page_title="OT5 Valuation Tool", layout="wide")
st.title("OT5 / PSE-4 Private Sector Contribution Tool")

# =========================================================
# AIRTABLE SECRETS
# =========================================================
try:
    AIRTABLE_TOKEN = st.secrets["AIRTABLE_TOKEN"]
    AIRTABLE_BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
    AIRTABLE_TABLE = st.secrets["AIRTABLE_OT5_TABLE"]
except:
    st.error("Missing Airtable secrets.")
    st.stop()

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(AIRTABLE_TABLE)}"

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
# REGION MATRIX (APEC)
# =========================================================
REGION_MATRIX = {
    "United States": "North America",
    "Canada": "North America",
    "Mexico": "North America",
    "Australia": "Oceania",
    "New Zealand": "Oceania",
    "Japan": "East Asia",
    "Korea": "East Asia",
    "China": "East Asia",
    "Hong Kong": "East Asia",
    "Chinese Taipei": "East Asia",
    "Singapore": "Southeast Asia",
    "Malaysia": "Southeast Asia",
    "Thailand": "Southeast Asia",
    "Indonesia": "Southeast Asia",
    "Philippines": "Southeast Asia",
    "Viet Nam": "Southeast Asia",
    "Brunei": "Southeast Asia",
    "Chile": "South America",
    "Peru": "South America",
    "Papua New Guinea": "Oceania",
    "Russia": "North Asia"
}

# =========================================================
# LOAD AIRTABLE TABLES
# =========================================================
@st.cache_data
def load_table(table_name):
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
    return records

economy_records = load_table("Economy Reference List")
firm_records = load_table("OT4 Private Sector Firms")
workshop_records = load_table("Workshop Reference List")

economy_table = {r["fields"]["Economy"]: r for r in economy_records}
firm_table = {r["fields"]["Firm"]: r for r in firm_records}
workshop_table = {r["fields"]["Workshop"]: r for r in workshop_records}

# =========================================================
# HELPERS
# =========================================================
def extract_hours_from_pdf(file, speaker):
    reader = PdfReader(BytesIO(file.read()))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    pattern = r"(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})"
    matches = list(re.finditer(pattern, text))
    total = 0.0

    for i, m in enumerate(matches):
        start, end = m.groups()
        block_start = m.end()
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[block_start:block_end]

        if speaker.lower() in block.lower():
            s = datetime.strptime(start, "%H:%M")
            e = datetime.strptime(end, "%H:%M")
            total += (e - s).seconds / 3600

    return round(total, 2)

def calculate_labor(category, hours):
    total_hours = hours * LABOR_MULTIPLIER
    return round(total_hours * HOURLY_RATES[category], 2)

def calculate_airfare(origin, host):
    if not origin or not host:
        return AIRFARE_BANDS["Intercontinental"]

    if origin == host:
        return AIRFARE_BANDS["Domestic"]

    if REGION_MATRIX.get(origin) == REGION_MATRIX.get(host):
        return AIRFARE_BANDS["Regional"]

    return AIRFARE_BANDS["Intercontinental"]

# =========================================================
# A. SPEAKER & LOE
# =========================================================
st.header("A. Speaker & Level of Effort")

col1, col2 = st.columns(2)

with col1:
    speaker_name = st.text_input("Speaker Name")

with col2:
    agenda_file = st.file_uploader("Upload Agenda (PDF)", type=["pdf"])

if speaker_name and agenda_file:
    auto_hours = extract_hours_from_pdf(agenda_file, speaker_name)
else:
    auto_hours = 0.0

presentation_hours = st.number_input(
    "Presentation Hours",
    value=float(auto_hours),
    step=0.25
)

category = st.selectbox(
    "Seniority Category",
    list(HOURLY_RATES.keys())
)

labor_value = calculate_labor(category, presentation_hours)

# =========================================================
# B. TRAVEL
# =========================================================
st.header("B. Travel")

col3, col4 = st.columns(2)

with col3:
    firm_name = st.selectbox("Firm", sorted(firm_table.keys()))

with col4:
    host_economy = st.selectbox("Host Economy", sorted(economy_table.keys()))

# Dereference Firm → Economy
firm_link = firm_table[firm_name]["fields"].get("Economy", [])
if firm_link:
    firm_economy_id = firm_link[0]
    firm_origin = next(
        (name for name, r in economy_table.items() if r["id"] == firm_economy_id),
        None
    )
else:
    firm_origin = None

auto_airfare = calculate_airfare(firm_origin, host_economy)

override = st.checkbox("Override airfare")
if override:
    airfare = st.number_input("Airfare Amount", min_value=0.0)
else:
    airfare = auto_airfare
    st.info(f"Auto-calculated airfare: ${airfare:,.0f}")

travel_start = st.date_input("Travel Start Date")
travel_end = st.date_input("Travel End Date")

lodging_rate = st.number_input("Lodging Rate (per night)", min_value=0.0)
mie_rate = st.number_input("M&IE Rate (per day)", min_value=0.0)

days = (travel_end - travel_start).days + 1
nights = max(days - 1, 0)

travel_value = airfare + (lodging_rate * nights) + (mie_rate * days)

# =========================================================
# C. ENGAGEMENT
# =========================================================
st.header("C. Engagement")

engagement = st.selectbox("Engagement (Workshop)", sorted(workshop_table.keys()))

linked_ws = workshop_table[engagement]["fields"].get("Workstream", [])

if linked_ws:
    ws_id = linked_ws[0]
    workstream_name = next(
        (r["fields"]["Workstream"]
         for r in load_table("Workstream Reference List")
         if r["id"] == ws_id),
        None
    )
    st.success(f"Workstream: {workstream_name}")
else:
    workstream_name = None

# =========================================================
# D. REVIEW
# =========================================================
st.header("D. Review")

total_value = labor_value + travel_value
fiscal_year = f"FY{str(date.today().year + 1)[-2:]}"

col5, col6 = st.columns(2)

col5.metric("Labor Contribution", f"${labor_value:,.2f}")
col5.metric("Travel Contribution", f"${travel_value:,.2f}")

col6.metric("Total OT5 Value", f"${total_value:,.2f}")
col6.metric("Fiscal Year", fiscal_year)

# =========================================================
# SUBMIT
# =========================================================
if st.checkbox("I confirm this OT5 contribution estimate is correct"):
    if st.button("Submit OT5 Record to Airtable"):

        payload = {
            "fields": {
                "Amount": total_value,
                "Contribution Date": date.today().isoformat(),
                "Fiscal Year": fiscal_year,
                "Economy": [economy_table[host_economy]["id"]],
                "Firm": [firm_table[firm_name]["id"]],
                "Engagement": [workshop_table[engagement]["id"]]
            }
        }

        r = requests.post(AIRTABLE_URL, headers=HEADERS, json=payload)

        if r.status_code in [200, 201]:
            st.success("OT5 record successfully created.")
        else:
            st.error(f"Airtable submission failed ({r.status_code})")
            st.json(r.json())
