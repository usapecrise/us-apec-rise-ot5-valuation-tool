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
st.caption("Agenda-driven labor valuation • Standardized travel • Structured Airtable submission")

# =========================================================
# AIRTABLE SECRETS
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

AIRFARE_BANDS = {
    "Domestic": 550,
    "Regional": 700,
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

@st.cache_data
def load_workshops():
    url = airtable_url("Workshop Reference List")
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

    workshop_map = {}
    for rec in records:
        name = rec["fields"].get("Workshop")
        if name:
            workshop_map[name] = rec["id"]

    return workshop_map

economy_dict = load_reference_table("Economy Reference List", "Economy")
firm_dict = load_reference_table("OT4 Private Sector Firms", "Firm")
workshop_dict = load_workshops()

# =========================================================
# HELPERS
# =========================================================
def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(BytesIO(uploaded_file.read()))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

def parse_time(t):
    t = t.strip().lower()
    return datetime.strptime(t, "%I:%M %p")

def extract_speaker_hours(text, speaker):
    speaker = speaker.lower()
    total = 0.0

    pattern = r"(\d{1,2}:\d{2}\s*(?:am|pm))\s*[–\-]\s*(\d{1,2}:\d{2}\s*(?:am|pm))"
    matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))

    for i, m in enumerate(matches):
        start_time, end_time = m.groups()
        start_idx = m.end()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        block = text[start_idx:end_idx].lower()

        if speaker in block:
            s = parse_time(start_time)
            e = parse_time(end_time)
            total += (e - s).seconds / 3600

    return round(float(total), 2)

def assess_seniority(text):
    senior_patterns = [
        r"\bceo\b", r"\bcoo\b", r"\bcfo\b",
        r"\bpresident\b", r"\bvice president\b", r"\bvp\b",
        r"\bmanaging director\b", r"\bpartner\b",
        r"\bprincipal\b", r"\bco[- ]?founder\b"
    ]
    for p in senior_patterns:
        if re.search(p, text.lower()):
            return "Executive / Senior Leadership"
    return "Senior Specialist"

def derive_fy(d):
    fy = d.year + 1 if d.month >= 10 else d.year
    return f"FY{str(fy)[-2:]}"

# =========================================================
# AGENDA
# =========================================================
st.header("A. Speaker & Agenda")

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

# =========================================================
# LABOR
# =========================================================
st.header("B. Labor")

category_auto = assess_seniority(agenda_text)
category = st.selectbox(
    "Seniority Category",
    list(HOURLY_RATES.keys()),
    index=list(HOURLY_RATES.keys()).index(category_auto)
)

labor_hours = presentation_hours * LABOR_MULTIPLIER
labor_value = labor_hours * HOURLY_RATES[category]

# =========================================================
# TRAVEL
# =========================================================
st.header("C. Travel")

trip_type = st.selectbox("Trip Type", list(AIRFARE_BANDS.keys()))
airfare = AIRFARE_BANDS[trip_type]

travel_value = airfare

# =========================================================
# ENGAGEMENT ALLOCATION
# =========================================================
st.header("D. Engagement Allocation")

selected_engagements = st.multiselect(
    "Select Engagement(s)",
    sorted(workshop_dict.keys())
)

# =========================================================
# POLICY INFO
# =========================================================
st.header("E. Contribution Information")

firm_name = st.selectbox("Firm", sorted(firm_dict.keys()))
host_economy = st.selectbox("Host Economy", sorted(economy_dict.keys()))

resource_origin = st.selectbox(
    "Resource Origin",
    ["U.S.-based", "Host Country-based", "Third Country-based"]
)

fao = st.selectbox("U.S. FAO Addressed", FAO_OPTIONS)

contribution_date = st.date_input("Contribution Date", value=date.today())
fiscal_year = derive_fy(contribution_date)

# =========================================================
# REVIEW DASHBOARD
# =========================================================
st.header("F. Review")

total_value = labor_value + travel_value

if selected_engagements:
    allocated_per_engagement = total_value / len(selected_engagements)
else:
    allocated_per_engagement = 0

col1, col2 = st.columns(2)

with col1:
    st.metric("Labor Contribution", f"${labor_value:,.2f}")
    st.metric("Travel Contribution", f"${travel_value:,.2f}")

with col2:
    st.metric("Total Contribution", f"${total_value:,.2f}")
    st.metric("Fiscal Year", fiscal_year)

if selected_engagements:
    st.info(f"Will create {len(selected_engagements)} OT5 record(s) at ${allocated_per_engagement:,.2f} each")

# =========================================================
# SUBMIT
# =========================================================
if st.checkbox("I confirm this contribution estimate is correct"):
    if st.button("Submit to Airtable"):

        for engagement in selected_engagements:

            payload = {
                "fields": {
                    "Amount": round(allocated_per_engagement, 2),
                    "Contribution Date": contribution_date.isoformat(),
                    "Fiscal Year": fiscal_year,
                    "Resource Type": "In-kind",
                    "Resource Origin": resource_origin,
                    "U.S. FAOs Addressed": fao,
                    "Economy": [economy_dict[host_economy]],
                    "Firm": [firm_dict[firm_name]],
                    "Engagement": [workshop_dict[engagement]]
                }
            }

            r = requests.post(airtable_url(AIRTABLE_TABLE), headers=HEADERS, json=payload)

            if r.status_code not in [200, 201]:
                st.error(f"Submission failed: {r.text}")
                st.stop()

        st.success("OT5 record(s) successfully created.")
