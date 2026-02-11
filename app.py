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
st.set_page_config(page_title="OT5 Valuation Dashboard", layout="wide")
st.title("OT5 / PSE-4 Private Sector Contribution Dashboard")
st.caption("Agenda-based labor valuation • Standardized travel • Multi-engagement allocation")

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

VALID_FY_OPTIONS = ["FY25", "FY26", "FY27", "FY28", "FY29", "FY30"]

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
        if r.status_code != 200:
            raise Exception(f"{table_name} failed: {r.text}")
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
    speaker = speaker.lower()
    total = 0.0
    pattern = r"(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})"

    matches = list(re.finditer(pattern, text))

    for i, m in enumerate(matches):
        start_t, end_t = m.groups()
        start_block = m.end()
        end_block = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start_block:end_block].lower()

        if speaker in block:
            s = datetime.strptime(start_t, "%H:%M")
            e = datetime.strptime(end_t, "%H:%M")
            total += (e - s).seconds / 3600

    return round(total, 2)

def assess_seniority(text):
    exec_titles = [
        r"\bceo\b", r"\bco[- ]?founder\b", r"\bpresident\b",
        r"\bvice president\b", r"\bvp\b",
        r"\bmanaging director\b", r"\bpartner\b", r"\bprincipal\b"
    ]
    for t in exec_titles:
        if re.search(t, text.lower()):
            return "Executive / Senior Leadership"
    return "Senior Specialist"

def calculate_labor(category, hours):
    total_hours = round(hours * LABOR_MULTIPLIER, 2)
    return round(total_hours * HOURLY_RATES[category], 2)

def derive_fy(d):
    fy = d.year + 1 if d.month >= 10 else d.year
    return f"FY{str(fy)[-2:]}"

# =========================================================
# SECTION A: SPEAKER & AGENDA
# =========================================================
st.header("A. Speaker & Agenda Review")

col1, col2 = st.columns(2)

with col1:
    speaker_name = st.text_input("Speaker Name")
    agenda_file = st.file_uploader("Upload Agenda (PDF)", type=["pdf"])

with col2:
    agenda_text = ""
    if agenda_file:
        agenda_text = extract_text_from_pdf(agenda_file)
    agenda_text = st.text_area("Agenda Text", value=agenda_text, height=250)

presentation_hours = extract_speaker_hours(agenda_text, speaker_name)
presentation_hours = st.number_input("Presentation Hours (editable)", value=presentation_hours, step=0.25)

# =========================================================
# SECTION B: LABOR
# =========================================================
st.header("B. Labor Valuation")

category = assess_seniority(agenda_text)
category = st.selectbox("Speaker Category", list(HOURLY_RATES.keys()),
                        index=list(HOURLY_RATES.keys()).index(category))

labor_value = calculate_labor(category, presentation_hours)

# =========================================================
# SECTION C: TRAVEL (ONE TRIP)
# =========================================================
st.header("C. Travel (Trip-Level)")

trip_type = st.selectbox("Trip Type", list(AIRFARE_BANDS.keys()))
airfare = AIRFARE_BANDS[trip_type]

travel_start = st.date_input("Travel Start Date")
travel_end = st.date_input("Travel End Date")

lodging_rate = st.number_input("Lodging Rate (USD)", min_value=0.0)
mie_rate = st.number_input("M&IE Rate (USD)", min_value=0.0)

days = (travel_end - travel_start).days + 1
nights = max(days - 1, 0)

travel_total = airfare + (lodging_rate * nights)

# =========================================================
# SECTION D: ENGAGEMENT ALLOCATION
# =========================================================
st.header("D. Engagement Allocation")

engagements_selected = st.multiselect("Select Engagement(s)", sorted(engagement_dict.keys()))

num_engagements = len(engagements_selected) if engagements_selected else 1
travel_per_engagement = round(travel_total / num_engagements, 2)

st.info(f"Travel will be split across {num_engagements} engagement(s).")

# =========================================================
# SECTION E: CLASSIFICATION
# =========================================================
st.header("E. Contribution Classification")

firm_name = st.selectbox("Firm", sorted(firm_dict.keys()))
host_economy = st.selectbox("Economy", sorted(economy_dict.keys()))
workstream = st.selectbox("Workstream", sorted(workstream_dict.keys()))

resource_origin = st.selectbox(
    "Resource Origin",
    ["U.S.-based", "Host Country-based", "Third Country-based"]
)

fiscal_year = derive_fy(travel_start)
if fiscal_year not in VALID_FY_OPTIONS:
    fiscal_year = st.selectbox("Fiscal Year", VALID_FY_OPTIONS)
else:
    st.write(f"Fiscal Year: {fiscal_year}")

# =========================================================
# SECTION F: DASHBOARD SUMMARY
# =========================================================
st.header("F. Review & Submit")

colA, colB = st.columns(2)

with colA:
    st.metric("Labor Contribution", f"${labor_value:,.2f}")
    st.metric("Travel (Per Engagement)", f"${travel_per_engagement:,.2f}")

with colB:
    total_per_engagement = labor_value + travel_per_engagement
    st.metric("Total OT5 (Per Engagement)", f"${total_per_engagement:,.2f}")
    st.write("Engagement Count:", num_engagements)

# =========================================================
# SECTION G: SUBMIT MULTIPLE RECORDS
# =========================================================
if st.checkbox("I confirm this OT5 contribution estimate is correct"):
    if st.button("Submit OT5 Record(s) to Airtable"):

        created = 0

        for engagement in engagements_selected:

            payload = {
                "fields": {
                    "Amount": total_per_engagement,
                    "Contribution Date": travel_start.isoformat(),
                    "Fiscal Year": fiscal_year,
                    "Resource Type": "In-kind",
                    "Resource Origin": resource_origin,
                    "Economy": [economy_dict[host_economy]],
                    "Firm": [firm_dict[firm_name]],
                    "Workstream": [workstream_dict[workstream]],
                    "Engagement": [engagement_dict[engagement]]
                }
            }

            r = requests.post(AIRTABLE_URL, headers=HEADERS, json=payload)

            if r.status_code in [200, 201]:
                created += 1
            else:
                st.error(f"Failed for {engagement}")
                st.json(r.json())
                st.stop()

        st.success(f"{created} OT5 record(s) successfully created.")
