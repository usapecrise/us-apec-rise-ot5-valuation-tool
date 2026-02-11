import streamlit as st
import re
import requests
import os
import urllib.parse
from datetime import datetime, date
from io import BytesIO
from PyPDF2 import PdfReader

# =========================================================
# STREAMLIT CONFIG
# =========================================================
st.set_page_config(page_title="OT5 Valuation Tool", layout="centered")
st.title("OT5 / PSE-4 Private Sector Valuation Tool")
st.caption("Agenda-based labor valuation, standardized travel, Airtable submission")

# =========================================================
# AIRTABLE CONFIG (MATCHES YOUR SECRETS)
# =========================================================
AIRTABLE_TOKEN = st.secrets("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID = st.secrets("AIRTABLE_BASE_ID")
AIRTABLE_TABLE = st.secrets("AIRTABLE_OT5_TABLE")

if not AIRTABLE_TOKEN or not AIRTABLE_BASE_ID or not AIRTABLE_TABLE:
    st.error("Missing Airtable configuration. Check Streamlit Secrets.")
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
STANDARD_TRAVEL_DAYS = 2
TRAVEL_DAY_MIE_FACTOR = 0.75

AIRFARE_BANDS = {
    "Domestic (same economy)": 550,
    "Regional (same region)": 700,
    "Intercontinental": 1400
}

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
# LOAD REFERENCE TABLES (CACHED)
# =========================================================
@st.cache_data
def load_reference_table(table_name, primary_field):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(table_name)}"
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

economy_dict = load_reference_table("Economy Reference List", "Economy")
firm_dict = load_reference_table("Firm Reference List", "Firm")

# =========================================================
# HELPERS
# =========================================================
def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(BytesIO(uploaded_file.read()))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

def extract_speaker_hours(text, speaker):
    speaker = speaker.lower()
    total = 0.0
    time_pattern = r"(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})"
    matches = list(re.finditer(time_pattern, text))

    for i, m in enumerate(matches):
        start_t, end_t = m.groups()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].lower()
        if speaker in block:
            s = datetime.strptime(start_t, "%H:%M")
            e = datetime.strptime(end_t, "%H:%M")
            total += (e - s).seconds / 3600

    return round(total, 2)

def assess_seniority_from_agenda(text):
    titles = [
        r"\bceo\b", r"\bcoo\b", r"\bcfo\b", r"\bchief .* officer\b",
        r"\bpresident\b", r"\bvice president\b", r"\bvp\b",
        r"\bmanaging director\b", r"\bpartner\b", r"\bprincipal\b",
        r"\bfounder\b", r"\bco[- ]?founder\b"
    ]
    for t in titles:
        if re.search(t, text.lower()):
            return "Executive / Senior Leadership"
    return "Senior Specialist"

def calculate_labor(category, hours):
    total_hours = round(hours * LABOR_MULTIPLIER, 2)
    return total_hours, round(total_hours * HOURLY_RATES[category], 2)

def calculate_travel(airfare, lodging_rate, mie_rate, start, end, workshops):
    days = (end - start).days + 1
    nights = max(days - 1, 0)
    lodging = lodging_rate * nights
    mie_travel = mie_rate * TRAVEL_DAY_MIE_FACTOR * STANDARD_TRAVEL_DAYS
    mie_full = mie_rate * max(days - STANDARD_TRAVEL_DAYS, 0)
    total = airfare + lodging + mie_travel + mie_full
    return round(total / workshops, 2)

def derive_usg_fiscal_year(d):
    return d.year + 1 if d.month >= 10 else d.year

# =========================================================
# A. AGENDA
# =========================================================
st.subheader("A. Agenda & Speaker")

speaker_name = st.text_input("Speaker Name")
agenda_file = st.file_uploader("Upload Agenda (PDF)", type=["pdf"])
agenda_text = extract_text_from_pdf(agenda_file) if agenda_file else ""
agenda_text = st.text_area("Agenda Text", value=agenda_text, height=260)

presentation_hours = extract_speaker_hours(agenda_text, speaker_name)
presentation_hours = st.number_input(
    "Presentation Hours",
    value=presentation_hours,
    step=0.25
)

# =========================================================
# B. LABOR
# =========================================================
st.subheader("B. Labor Valuation")

category = assess_seniority_from_agenda(agenda_text)
category = st.selectbox(
    "Confirm Category",
    list(HOURLY_RATES.keys()),
    index=list(HOURLY_RATES.keys()).index(category)
)

labor_hours, labor_value = calculate_labor(category, presentation_hours)

# =========================================================
# C. TRAVEL
# =========================================================
st.subheader("C. Travel Valuation")

trip_type = st.selectbox("Trip Type", list(AIRFARE_BANDS.keys()))
airfare = AIRFARE_BANDS[trip_type]

travel_start = st.date_input("Travel Start Date")
travel_end = st.date_input("Travel End Date")

lodging_rate = st.number_input("DOS Lodging Rate", min_value=0.0)
mie_rate = st.number_input("DOS M&IE Rate", min_value=0.0)
workshops_on_trip = st.number_input("Workshops on this trip", min_value=1)

travel_value = calculate_travel(
    airfare, lodging_rate, mie_rate,
    travel_start, travel_end, workshops_on_trip
)

# =========================================================
# D. POLICY FIELDS
# =========================================================
st.subheader("D. Policy Fields")

firm_name = st.selectbox("Firm Name", sorted(firm_dict.keys()))
host_economy = st.selectbox("Host Economy", sorted(economy_dict.keys()))

resource_origin = st.selectbox(
    "Resource Origin",
    ["U.S.-based", "Host Country-based", "Third Country-based"]
)

faos = st.multiselect(
    "U.S. FAOs Addressed",
    FAO_OPTIONS,
    default=["Economic Growth (Other)"]
)

# =========================================================
# E. REVIEW
# =========================================================
total_ot5 = round(labor_value + travel_value, 2)
fiscal_year = f"FY {derive_usg_fiscal_year(date.today())}"

st.subheader("E. Review & Submit")

st.write({
    "Labor Value": labor_value,
    "Travel Value": travel_value,
    "Total OT5 Value": total_ot5,
    "Fiscal Year": fiscal_year
})

# =========================================================
# F. SUBMIT
# =========================================================
if st.checkbox("I confirm this OT5 valuation is correct"):
    if st.button("Submit OT5 Record to Airtable"):

        payload = {
            "fields": {
                "Amount": total_ot5,
                "Indicator ID": "OT5",
                "Contribution Date": date.today().isoformat(),
                "Fiscal Year": fiscal_year,
                "Resource Type": "In-kind",
                "Resource Origin": resource_origin,
                "U.S. FAOs Addressed": faos,
                "Economy": [economy_dict[host_economy]],
                "Firm": [firm_dict[firm_name]]
            }
        }

        r = requests.post(AIRTABLE_URL, headers=HEADERS, json=payload)

        if r.status_code in [200, 201]:
            st.success("OT5 record successfully created in Airtable.")
        else:
            st.error("Airtable submission failed.")
            st.json(r.json())
