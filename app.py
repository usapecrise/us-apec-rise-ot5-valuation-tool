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
st.set_page_config(
    page_title="OT5 Private Sector Valuation",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.title("OT5 / PSE-4 Private Sector Valuation Tool")
st.caption("Agenda-based labor valuation · Standardized travel · Structured Airtable submission")

# =========================================================
# AIRTABLE CONFIG
# =========================================================
try:
    AIRTABLE_TOKEN = st.secrets["AIRTABLE_TOKEN"]
    AIRTABLE_BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
    AIRTABLE_TABLE = st.secrets["AIRTABLE_OT5_TABLE"]
except Exception:
    st.error("Airtable secrets not configured.")
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
# REFERENCE TABLE LOADER
# =========================================================
@st.cache_data
def load_reference_table(table_name, primary_field):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(table_name)}"
    records = []
    offset = None

    while True:
        params = {"offset": offset} if offset else {}
        r = requests.get(url, headers=HEADERS, params=params)

        if r.status_code != 200:
            raise Exception(f"Airtable Error {r.status_code}: {r.text}")

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
# HELPERS
# =========================================================
def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(BytesIO(uploaded_file.read()))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

def extract_speaker_hours(text, speaker):
    if not speaker:
        return 0.0

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
        r"\bceo\b", r"\bpresident\b", r"\bvice president\b",
        r"\bmanaging director\b", r"\bprincipal\b",
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
    fy = d.year + 1 if d.month >= 10 else d.year
    return f"FY{str(fy)[-2:]}"  # FY26 format

# =========================================================
# SECTION A: AGENDA & SPEAKER
# =========================================================
st.divider()
st.header("A. Agenda & Speaker Information")

speaker_name = st.text_input("Speaker Name")

agenda_file = st.file_uploader("Upload Agenda (PDF)", type=["pdf"])
agenda_text = extract_text_from_pdf(agenda_file) if agenda_file else ""
agenda_text = st.text_area("Agenda Text (editable)", value=agenda_text, height=220)

presentation_hours = extract_speaker_hours(agenda_text, speaker_name)
presentation_hours = st.number_input(
    "Calculated Presentation Hours",
    value=presentation_hours,
    step=0.25
)

# =========================================================
# SECTION B: LABOR
# =========================================================
st.divider()
st.header("B. Labor Contribution")

category_guess = assess_seniority_from_agenda(agenda_text)
category = st.selectbox(
    "Seniority Category",
    list(HOURLY_RATES.keys()),
    index=list(HOURLY_RATES.keys()).index(category_guess)
)

labor_hours, labor_value = calculate_labor(category, presentation_hours)

# =========================================================
# SECTION C: TRAVEL
# =========================================================
st.divider()
st.header("C. Travel Contribution")

trip_type = st.selectbox("Trip Type", list(AIRFARE_BANDS.keys()))
airfare = AIRFARE_BANDS[trip_type]

col1, col2 = st.columns(2)
with col1:
    travel_start = st.date_input("Travel Start Date")
with col2:
    travel_end = st.date_input("Travel End Date")

lodging_rate = st.number_input("DOS Lodging Rate", min_value=0.0)
mie_rate = st.number_input("DOS M&IE Rate", min_value=0.0)
workshops_on_trip = st.number_input("Workshops on Trip", min_value=1)

travel_value = calculate_travel(
    airfare, lodging_rate, mie_rate,
    travel_start, travel_end, workshops_on_trip
)

# =========================================================
# SECTION D: CONTRIBUTION CLASSIFICATION
# =========================================================
st.divider()
st.header("D. Contribution Classification")

firm_name = st.selectbox("Firm", sorted(firm_dict.keys()))
host_economy = st.selectbox("Host Economy", sorted(economy_dict.keys()))
workstream = st.selectbox("Workstream", sorted(workstream_dict.keys()))
engagement = st.selectbox("Engagement (Workshop)", sorted(engagement_dict.keys()))

resource_origin = st.selectbox(
    "Resource Origin",
    ["U.S.-based", "Host Country-based", "Third Country-based"]
)

fao = st.selectbox("U.S. FAO Addressed", FAO_OPTIONS)

# =========================================================
# SECTION E: EXECUTIVE DASHBOARD REVIEW
# =========================================================
st.divider()
st.header("E. Review & Submit")

total_ot5 = round(labor_value + travel_value, 2)
fiscal_year = derive_usg_fiscal_year(date.today())

col1, col2 = st.columns(2)

with col1:
    st.metric("Labor Contribution", f"${labor_value:,.2f}")
    st.metric("Travel Contribution", f"${travel_value:,.2f}")

with col2:
    st.metric("Total OT5 Value", f"${total_ot5:,.2f}")
    st.metric("Fiscal Year", fiscal_year)

st.divider()

# =========================================================
# SUBMIT
# =========================================================
if st.checkbox("I confirm this OT5 contribution estimate is correct"):
    if st.button("Submit OT5 Record to Airtable"):

        payload = {
            "fields": {
                "Amount": total_ot5,
                "Contribution Date": date.today().isoformat(),
                "Fiscal Year": fiscal_year,
                "Resource Type": "In-kind",
                "Resource Origin": resource_origin,
                "U.S. FAOs Addressed": fao,
                "Economy": [economy_dict[host_economy]],
                "Firm": [firm_dict[firm_name]],
                "Workstream": [workstream_dict[workstream]],
                "Engagement": [engagement_dict[engagement]]
            }
        }

        r = requests.post(AIRTABLE_URL, headers=HEADERS, json=payload)

        if r.status_code in [200, 201]:
            st.success("OT5 record successfully created in Airtable.")
        else:
            st.error(f"Airtable submission failed ({r.status_code})")
            st.json(r.json())
