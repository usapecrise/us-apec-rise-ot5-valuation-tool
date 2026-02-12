import streamlit as st
import requests
import urllib.parse
import re
from datetime import datetime, date
from io import BytesIO
from PyPDF2 import PdfReader

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(page_title="OT5 Valuation Tool", layout="centered")

st.title("OT5 / PSE-4 Private Sector Valuation Tool")
st.caption("Agenda-based labor valuation • Automated airfare • Airtable submission")

# =========================================================
# AIRTABLE SECRETS
# =========================================================
AIRTABLE_TOKEN = st.secrets["AIRTABLE_TOKEN"]
AIRTABLE_BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
AIRTABLE_TABLE = st.secrets["AIRTABLE_OT5_TABLE"]

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"

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

AIRFARE_BANDS = {
    "Domestic": 550,
    "Regional": 700,
    "Intercontinental": 1400
}

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
    "Peru": "South America"
}

# =========================================================
# REFERENCE TABLE LOADER
# =========================================================
@st.cache_data
def load_reference_table(table_name, primary_field):
    url = f"{BASE_URL}/{urllib.parse.quote(table_name)}"
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
        rec["fields"].get(primary_field): rec
        for rec in records
        if rec["fields"].get(primary_field)
    }

economy_table = load_reference_table("Economy Reference List", "Economy")
firm_table = load_reference_table("OT4 Private Sector Firms", "Firm")
workshop_table = load_reference_table("Workshop Reference List", "Workshop")

# =========================================================
# AGENDA EXTRACTION
# =========================================================
def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(BytesIO(uploaded_file.read()))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

def normalize_time(t):
    t = t.lower().strip()
    if "am" not in t and "pm" not in t:
        t += " am"
    return datetime.strptime(t.strip(), "%I:%M %p")

def extract_hours(text, speaker):
    total = 0
    speaker = speaker.lower()
    text = text.lower()

    pattern = r'(\d{1,2}:\d{2}\s*(?:am|pm)?)\s*[–\-]\s*(\d{1,2}:\d{2}\s*(?:am|pm))'
    matches = list(re.finditer(pattern, text))

    for i, m in enumerate(matches):
        start_raw, end_raw = m.groups()
        start_index = m.end()
        end_index = matches[i+1].start() if i+1 < len(matches) else len(text)
        block = text[start_index:end_index]

        if speaker in block:
            start_time = normalize_time(start_raw)
            end_time = normalize_time(end_raw)
            total += (end_time - start_time).seconds / 3600

    return round(total, 2)

# =========================================================
# UI SECTION A
# =========================================================
st.header("A. Speaker & Level of Effort")

speaker = st.text_input("Speaker Name")

agenda_file = st.file_uploader("Upload Agenda (PDF)", type=["pdf"])

agenda_text = ""
if agenda_file:
    agenda_text = extract_text_from_pdf(agenda_file)

auto_hours = extract_hours(agenda_text, speaker) if speaker and agenda_text else 0.0

presentation_hours = st.number_input(
    "Presentation Hours",
    min_value=0.0,
    value=float(auto_hours),
    step=0.25
)

category = st.selectbox(
    "Seniority Category",
    list(HOURLY_RATES.keys())
)

labor_hours = presentation_hours * LABOR_MULTIPLIER
labor_value = round(labor_hours * HOURLY_RATES[category], 2)

# =========================================================
# UI SECTION B
# =========================================================
st.header("B. Travel")

firm_name = st.selectbox("Firm", sorted(firm_table.keys()))
host_economy = st.selectbox("Host Economy", sorted(economy_table.keys()))

firm_origin = firm_table[firm_name]["fields"].get("Economy")

def calculate_airfare(origin, host):
    if origin == host:
        return AIRFARE_BANDS["Domestic"]

    if REGION_MATRIX.get(origin) == REGION_MATRIX.get(host):
        return AIRFARE_BANDS["Regional"]

    return AIRFARE_BANDS["Intercontinental"]

auto_airfare = calculate_airfare(firm_origin, host_economy)

st.info(f"Auto-calculated airfare: ${auto_airfare:,}")

travel_start = st.date_input("Travel Start Date")
travel_end = st.date_input("Travel End Date")

lodging_rate = st.number_input("Lodging Rate (per night)", min_value=0.0)
mie_rate = st.number_input("M&IE Rate (per day)", min_value=0.0)
workshops_on_trip = st.number_input("Workshops on Trip", min_value=1)

days = (travel_end - travel_start).days + 1
nights = max(days - 1, 0)

lodging = lodging_rate * nights
mie = mie_rate * days

travel_total = auto_airfare + lodging + mie
travel_value = round(travel_total / workshops_on_trip, 2)

# =========================================================
# UI SECTION C
# =========================================================
st.header("C. Engagement")

engagement = st.selectbox("Engagement", sorted(workshop_table.keys()))

engagement_record = workshop_table[engagement]
engagement_id = engagement_record["id"]
workstream_link = engagement_record["fields"].get("Workstream", [])

# =========================================================
# REVIEW
# =========================================================
total_ot5 = round(labor_value + travel_value, 2)

fy = date.today().year
if date.today().month >= 10:
    fy += 1
fy_formatted = f"FY{str(fy)[-2:]}"

st.header("D. Review")

col1, col2 = st.columns(2)

with col1:
    st.metric("Labor Contribution", f"${labor_value:,.2f}")
    st.metric("Travel Contribution", f"${travel_value:,.2f}")

with col2:
    st.metric("Total OT5 Value", f"${total_ot5:,.2f}")
    st.metric("Fiscal Year", fy_formatted)

# =========================================================
# SUBMIT
# =========================================================
if st.checkbox("I confirm this OT5 estimate is correct"):
    if st.button("Submit OT5 Record to Airtable"):

        payload = {
            "fields": {
                "Amount": total_ot5,
                "Indicator": "OT5",
                "Contribution Date": date.today().isoformat(),
                "Fiscal Year": fy_formatted,
                "Firm": [firm_table[firm_name]["id"]],
                "Economy": [economy_table[host_economy]["id"]],
                "Engagement": [engagement_id],
                "Workstream": workstream_link
            }
        }

        url = f"{BASE_URL}/{urllib.parse.quote(AIRTABLE_TABLE)}"
        r = requests.post(url, headers=HEADERS, json=payload)

        if r.status_code in [200, 201]:
            st.success("OT5 record successfully created.")
        else:
            st.error(f"Airtable submission failed ({r.status_code})")
            st.json(r.json())
