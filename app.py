import streamlit as st
import requests
import urllib.parse
import re
from datetime import datetime, date
from io import BytesIO
from PyPDF2 import PdfReader

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(page_title="OT5 Valuation Dashboard", layout="wide")
st.title("OT5 / PSE-4 Private Sector Contribution Dashboard")
st.caption("Agenda-based LOE • Region airfare matrix • Multi-engagement allocation")

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

AIRFARE_VALUES = {
    "A": 600,
    "B": 900,
    "C": 1500
}

# =========================================================
# REGION MAP
# =========================================================
REGION_MAP = {
    "United States": "NA", "Canada": "NA", "Mexico": "NA",
    "Chile": "SA", "Peru": "SA",
    "Japan": "NEA", "Korea": "NEA", "China": "NEA",
    "Chinese Taipei": "NEA", "Hong Kong": "NEA",
    "Singapore": "SEA", "Malaysia": "SEA", "Thailand": "SEA",
    "Vietnam": "SEA", "Philippines": "SEA",
    "Indonesia": "SEA", "Brunei": "SEA",
    "Australia": "OC", "New Zealand": "OC",
    "Papua New Guinea": "OC",
    "Russia": "RU"
}

BAND_MATRIX = {
    ("NA","NA"): "A",
    ("SA","SA"): "A",
    ("NEA","NEA"): "A",
    ("SEA","SEA"): "A",
    ("OC","OC"): "A",
    ("RU","RU"): "A",
    ("NA","SA"): "B",
    ("NA","NEA"): "B",
    ("NEA","SEA"): "B",
    ("SEA","OC"): "B",
    ("NEA","RU"): "B"
}

def get_band(origin, host):
    r1 = REGION_MAP.get(origin)
    r2 = REGION_MAP.get(host)

    if not r1 or not r2:
        return "C"

    if (r1, r2) in BAND_MATRIX:
        return BAND_MATRIX[(r1, r2)]
    if (r2, r1) in BAND_MATRIX:
        return BAND_MATRIX[(r2, r1)]
    if r1 == r2:
        return "A"
    return "C"

# =========================================================
# AGENDA LOE FUNCTIONS
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
# SECTION A: AGENDA & LOE
# =========================================================
st.header("A. Agenda & Speaker")

speaker_name = st.text_input("Speaker Name")
agenda_file = st.file_uploader("Upload Agenda (PDF)", type=["pdf"])

agenda_text = ""
if agenda_file:
    agenda_text = extract_text_from_pdf(agenda_file)

agenda_text = st.text_area("Agenda Text (editable)", value=agenda_text, height=250)

auto_hours = extract_speaker_hours(agenda_text, speaker_name) if speaker_name else 0

presentation_hours = st.number_input(
    "Presentation Hours (auto-detected, editable)",
    value=auto_hours,
    step=0.25
)

category = st.selectbox("Speaker Category", list(HOURLY_RATES.keys()))

labor_total = round(presentation_hours * LABOR_MULTIPLIER * HOURLY_RATES[category], 2)

# =========================================================
# SECTION B: TRAVEL
# =========================================================
st.header("B. Trip")

speaker_origin = st.selectbox("Speaker Origin Economy", sorted(REGION_MAP.keys()))
host_economy = st.selectbox("Host Economy", sorted(economy_dict.keys()))

travel_start = st.date_input("Travel Start Date")
travel_end = st.date_input("Travel End Date")

lodging_rate = st.number_input("Lodging Rate (USD)", min_value=0.0)

band = get_band(speaker_origin, host_economy)
airfare = AIRFARE_VALUES[band]

st.info(f"Airfare Band: {band} (${airfare})")

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

# =========================================================
# SECTION D: REVIEW
# =========================================================
st.header("D. Review")

col1, col2 = st.columns(2)

with col1:
    st.metric("Total Labor (Trip)", f"${labor_total:,.2f}")
    st.metric("Travel per Engagement", f"${travel_per_engagement:,.2f}")

with col2:
    total_per_engagement = labor_total + travel_per_engagement
    st.metric("Total per Engagement", f"${total_per_engagement:,.2f}")

# =========================================================
# SUBMIT
# =========================================================
if st.checkbox("I confirm this OT5 allocation is correct"):
    if st.button("Submit OT5 Record(s)"):

        for e in engagements_selected:

            payload = {
                "fields": {
                    "Amount": total_per_engagement,
                    "Contribution Date": travel_start.isoformat(),
                    "Fiscal Year": f"FY{str(travel_start.year + (1 if travel_start.month >= 10 else 0))[-2:]}",
                    "Resource Type": "In-kind",
                    "Economy": [economy_dict[host_economy]],
                    "Firm": [firm_dict.get(speaker_name, "")],
                    "Engagement": [workshop_dict[e]["id"]],
                    "Workstream": [workshop_dict[e]["workstream_id"]]
                }
            }

            r = requests.post(AIRTABLE_URL, headers=HEADERS, json=payload)

            if r.status_code not in [200, 201]:
                st.error(f"Submission failed for {e}")
                st.json(r.json())
                st.stop()

        st.success("All OT5 records successfully created.")
