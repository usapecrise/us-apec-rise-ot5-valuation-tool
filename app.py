import streamlit as st
import re
import requests
import urllib.parse
from datetime import datetime, date
from io import BytesIO
from PyPDF2 import PdfReader

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(page_title="OT5 Valuation Tool", layout="centered")
st.title("OT5 / PSE-4 Private Sector Contribution Tool")
st.caption("Agenda-based labor valuation • Region airfare matrix • Multi-engagement allocation")

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

def airtable_url(table):
    return f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(table)}"

# =========================================================
# CONSTANTS
# =========================================================
HOURLY_RATES = {
    "Executive / Senior Leadership": 149,
    "Senior Specialist": 131
}

LABOR_MULTIPLIER = 3.5

# =========================================================
# REGION MATRIX
# =========================================================
ECONOMY_REGION = {
    "United States": "North America",
    "Canada": "North America",
    "Mexico": "North America",
    "Chile": "Latin America",
    "Peru": "Latin America",
    "Japan": "Northeast Asia",
    "Korea": "Northeast Asia",
    "China": "Northeast Asia",
    "Chinese Taipei": "Northeast Asia",
    "Hong Kong": "Northeast Asia",
    "Singapore": "Southeast Asia",
    "Malaysia": "Southeast Asia",
    "Thailand": "Southeast Asia",
    "Vietnam": "Southeast Asia",
    "Philippines": "Southeast Asia",
    "Indonesia": "Southeast Asia",
    "Brunei": "Southeast Asia",
    "Australia": "Oceania",
    "New Zealand": "Oceania",
    "Papua New Guinea": "Oceania",
    "Russia": "Russia"
}

REGION_BANDS = {
    ("North America", "North America"): 550,
    ("North America", "Latin America"): 700,
    ("North America", "Northeast Asia"): 1400,
    ("North America", "Southeast Asia"): 1400,
    ("North America", "Oceania"): 1500,
    ("Latin America", "Latin America"): 600,
    ("Northeast Asia", "Northeast Asia"): 600,
    ("Southeast Asia", "Southeast Asia"): 600,
    ("Oceania", "Oceania"): 700,
    ("Northeast Asia", "Southeast Asia"): 900,
    ("Southeast Asia", "Oceania"): 900,
    ("Northeast Asia", "Russia"): 900,
}

def calculate_airfare(origin_economy, host_economy):
    r1 = ECONOMY_REGION.get(origin_economy)
    r2 = ECONOMY_REGION.get(host_economy)

    if not r1 or not r2:
        return 1400

    if (r1, r2) in REGION_BANDS:
        return REGION_BANDS[(r1, r2)]

    if (r2, r1) in REGION_BANDS:
        return REGION_BANDS[(r2, r1)]

    return 1400

# =========================================================
# LOAD REFERENCE TABLES
# =========================================================
@st.cache_data
def load_economies():
    url = airtable_url("Economy Reference List")
    records = []
    offset = None

    while True:
        params = {"offset": offset} if offset else {}
        r = requests.get(url, headers=HEADERS, params=params)
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    economy_map = {}
    reverse_map = {}

    for rec in records:
        name = rec["fields"].get("Economy")
        if name:
            economy_map[name] = rec["id"]
            reverse_map[rec["id"]] = name

    return economy_map, reverse_map

@st.cache_data
def load_firms():
    url = airtable_url("OT4 Private Sector Firms")
    records = []
    offset = None

    while True:
        params = {"offset": offset} if offset else {}
        r = requests.get(url, headers=HEADERS, params=params)
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    firm_map = {}

    for rec in records:
        name = rec["fields"].get("Firm")
        linked_economy = rec["fields"].get("Economy")

        if name and linked_economy:
            firm_map[name] = {
                "id": rec["id"],
                "economy_id": linked_economy[0]
            }

    return firm_map

@st.cache_data
def load_engagements():
    return load_reference_table("Workshop Reference List", "Workshop")

def load_reference_table(table_name, primary_field):
    url = airtable_url(table_name)
    records = []
    offset = None

    while True:
        params = {"offset": offset} if offset else {}
        r = requests.get(url, headers=HEADERS, params=params)
        r.raise_for_status()
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

economy_dict, economy_reverse = load_economies()
firm_data = load_firms()
engagement_dict = load_engagements()

# =========================================================
# HELPERS
# =========================================================
def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(BytesIO(uploaded_file.read()))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

def parse_time(t):
    return datetime.strptime(t.strip().lower(), "%I:%M %p")

def extract_speaker_hours(text, speaker):
    total = 0.0
    pattern = r"(\d{1,2}:\d{2}\s*(?:am|pm))\s*[–\-]\s*(\d{1,2}:\d{2}\s*(?:am|pm))"
    matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))

    for i, m in enumerate(matches):
        start, end = m.groups()
        block_start = m.end()
        block_end = matches[i+1].start() if i+1 < len(matches) else len(text)
        block = text[block_start:block_end].lower()

        if speaker.lower() in block:
            s = parse_time(start)
            e = parse_time(end)
            total += (e - s).seconds / 3600

    return round(total, 2)

def derive_fy(d):
    fy = d.year + 1 if d.month >= 10 else d.year
    return f"FY{str(fy)[-2:]}"

# =========================================================
# SECTION A — LOE
# =========================================================
st.header("A. Speaker & Level of Effort")

speaker_name = st.text_input("Speaker Name")
agenda_file = st.file_uploader("Upload Agenda (PDF)", type=["pdf"])

agenda_text = ""
if agenda_file:
    agenda_text = extract_text_from_pdf(agenda_file)

auto_hours = 0.0
if speaker_name and agenda_text:
    auto_hours = extract_speaker_hours(agenda_text, speaker_name)

presentation_hours = st.number_input(
    "Presentation Hours",
    min_value=0.0,
    value=float(auto_hours),
    step=0.25
)

category = st.selectbox("Seniority Category", list(HOURLY_RATES.keys()))
labor_value = presentation_hours * LABOR_MULTIPLIER * HOURLY_RATES[category]

# =========================================================
# SECTION B — TRAVEL
# =========================================================
st.header("B. Travel")

firm_name = st.selectbox("Firm", sorted(firm_data.keys()))
host_economy = st.selectbox("Host Economy", sorted(economy_dict.keys()))

firm_economy_id = firm_data[firm_name]["economy_id"]
firm_economy_name = economy_reverse.get(firm_economy_id)

airfare_auto = calculate_airfare(firm_economy_name, host_economy)

override_airfare = st.checkbox("Override airfare")

if override_airfare:
    airfare = st.number_input("Manual Airfare", min_value=0.0, value=float(airfare_auto))
else:
    airfare = airfare_auto
    st.info(f"Auto-calculated airfare: ${airfare:,.0f}")

travel_start = st.date_input("Travel Start Date")
travel_end = st.date_input("Travel End Date")

lodging_rate = st.number_input("Lodging Rate (per night)", min_value=0.0)
mie_rate = st.number_input("M&IE Rate (per day)", min_value=0.0)

days = (travel_end - travel_start).days + 1
nights = max(days - 1, 0)

lodging_total = lodging_rate * nights
mie_total = mie_rate * days
travel_total = airfare + lodging_total + mie_total

# =========================================================
# SECTION C — ENGAGEMENT SPLIT
# =========================================================
st.header("C. Engagement Allocation")

selected_engagements = st.multiselect(
    "Select Engagement(s)",
    sorted(engagement_dict.keys())
)

total_value = labor_value + travel_total

per_engagement_value = total_value / len(selected_engagements) if selected_engagements else 0

# =========================================================
# REVIEW
# =========================================================
st.header("D. Review")

col1, col2 = st.columns(2)

with col1:
    st.metric("Labor Value", f"${labor_value:,.2f}")
    st.metric("Travel Value", f"${travel_total:,.2f}")

with col2:
    st.metric("Total Contribution", f"${total_value:,.2f}")
    st.metric("Per Engagement", f"${per_engagement_value:,.2f}")

# =========================================================
# SUBMIT
# =========================================================
if st.checkbox("I confirm this OT5 estimate is correct"):
    if st.button("Submit to Airtable"):

        for engagement in selected_engagements:
            payload = {
                "fields": {
                    "Amount": round(per_engagement_value, 2),
                    "Contribution Date": date.today().isoformat(),
                    "Fiscal Year": derive_fy(date.today()),
                    "Resource Type": "In-kind",
                    "Economy": [economy_dict[host_economy]],
                    "Firm": [firm_data[firm_name]["id"]],
                    "Engagement": [engagement_dict[engagement]]
                }
            }

            r = requests.post(airtable_url(AIRTABLE_TABLE), headers=HEADERS, json=payload)

            if r.status_code not in [200, 201]:
                st.error(r.text)
                st.stop()

        st.success("OT5 record(s) successfully created.")
