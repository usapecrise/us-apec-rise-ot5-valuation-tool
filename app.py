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
st.set_page_config(page_title="OT5 Valuation Tool", layout="centered")
st.title("OT5 / PSE-4 Private Sector Valuation Tool")
st.caption("Agenda-based labor valuation · Region-based airfare · Airtable submission")

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

OT5_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(AIRTABLE_OT5_TABLE)}"

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

FY_OPTIONS = ["FY25","FY26","FY27","FY28","FY29","FY30"]

FAO_OPTIONS = [
    "Peace and Security",
    "Democracy",
    "Human Rights and Governance",
    "Health",
    "Education",
    "Economic Growth (Other)"
]

# =========================================================
# LOAD TABLES
# =========================================================
@st.cache_data
def load_table(table_name):
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

    return {rec["fields"][list(rec["fields"].keys())[0]]: rec for rec in records}

economy_table = load_table("Economy Reference List")
firm_table = load_table("OT4 Private Sector Firms")
workshop_table = load_table("Workshop Reference List")
workstream_table = load_table("Workstream Reference List")

# =========================================================
# AGENDA PARSING
# =========================================================
def extract_text(uploaded_file):
    reader = PdfReader(BytesIO(uploaded_file.read()))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

def extract_speaker_hours(text, speaker):
    if not text or not speaker:
        return 0.0

    speaker = speaker.lower()
    total = 0.0

    pattern = r"(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})"
    matches = list(re.finditer(pattern, text))

    for i, m in enumerate(matches):
        start_time, end_time = m.groups()
        start_idx = m.end()
        end_idx = matches[i+1].start() if i+1 < len(matches) else len(text)
        block = text[start_idx:end_idx].lower()

        if speaker in block:
            try:
                s = datetime.strptime(start_time, "%H:%M")
                e = datetime.strptime(end_time, "%H:%M")
                hours = (e - s).seconds / 3600
                total += hours
            except:
                continue

    return round(total, 2)

# =========================================================
# FIRM ORIGIN LOOKUP
# =========================================================
def get_firm_origin(firm_name):
    firm_record = firm_table.get(firm_name)
    if not firm_record:
        return None

    linked = firm_record["fields"].get("Economy", [])
    if not linked:
        return None

    econ_id = linked[0]

    for econ_name, econ_record in economy_table.items():
        if econ_record["id"] == econ_id:
            return econ_name

    return None

# =========================================================
# AIRFARE LOGIC (DATA-DRIVEN)
# =========================================================
def calculate_airfare(origin, host):

    # Always treat "Other" as intercontinental
    if origin == "Other" or host == "Other":
        return AIRFARE_BANDS["Intercontinental"]

    if not origin or not host:
        return AIRFARE_BANDS["Intercontinental"]

    if origin == host:
        return AIRFARE_BANDS["Domestic"]

    origin_region = economy_table.get(origin, {}).get("fields", {}).get("Region")
    host_region = economy_table.get(host, {}).get("fields", {}).get("Region")

    if not origin_region or not host_region:
        return AIRFARE_BANDS["Intercontinental"]

    if origin_region == host_region:
        return AIRFARE_BANDS["Regional"]

    return AIRFARE_BANDS["Intercontinental"]

# =========================================================
# UI
# =========================================================
st.header("A. Speaker & Level of Effort")

speaker_name = st.text_input("Speaker Name")
agenda_file = st.file_uploader("Upload Agenda (PDF)", type=["pdf"])

agenda_text = extract_text(agenda_file) if agenda_file else ""
auto_hours = extract_speaker_hours(agenda_text, speaker_name)

presentation_hours = st.number_input(
    "Presentation Hours (auto-detected)",
    min_value=0.0,
    value=float(auto_hours),
    step=0.25
)

category = st.selectbox("Seniority Category", list(HOURLY_RATES.keys()))

total_labor_hours = presentation_hours * LABOR_MULTIPLIER
labor_value = total_labor_hours * HOURLY_RATES[category]

# =========================================================
# TRAVEL
# =========================================================
st.header("B. Travel")

firm_name = st.selectbox("Firm", sorted(firm_table.keys()))
host_economy = st.selectbox("Host Economy", sorted(economy_table.keys()))

firm_origin = get_firm_origin(firm_name)
auto_airfare = calculate_airfare(firm_origin, host_economy)

override = st.checkbox("Override airfare")

if override:
    airfare = st.number_input("Manual Airfare", min_value=0.0, value=float(auto_airfare))
else:
    airfare = auto_airfare
    st.info(f"Auto-calculated airfare: ${auto_airfare:,.0f}")

travel_start = st.date_input("Travel Start Date")
travel_end = st.date_input("Travel End Date")

lodging_rate = st.number_input("Lodging Rate", min_value=0.0)
mie_rate = st.number_input("M&IE Rate", min_value=0.0)
workshops_on_trip = st.number_input("Workshops on this trip", min_value=1, value=1)

days = (travel_end - travel_start).days + 1
nights = max(days - 1, 0)

travel_total = airfare + (lodging_rate * nights) + (mie_rate * days)
travel_value = travel_total / workshops_on_trip

# =========================================================
# ENGAGEMENT + AUTO WORKSTREAM
# =========================================================
st.header("C. Engagement")

selected_workshop = st.selectbox("Engagement (Workshop)", sorted(workshop_table.keys()))

linked_ws = workshop_table[selected_workshop]["fields"].get("Workstream", [])
workstream_name = None

if linked_ws:
    ws_id = linked_ws[0]
    for name, record in workstream_table.items():
        if record["id"] == ws_id:
            workstream_name = name
            break

st.info(f"Workstream: {workstream_name}")

# =========================================================
# CLASSIFICATION
# =========================================================
st.header("D. Classification")

fiscal_year = st.selectbox("Fiscal Year", FY_OPTIONS)
fao = st.selectbox("U.S. FAOs Addressed", FAO_OPTIONS)
resource_origin = st.selectbox(
    "Resource Origin",
    ["U.S.-based","Host Country-based","Third Country-based"]
)

# =========================================================
# REVIEW
# =========================================================
total_ot5 = labor_value + travel_value

st.header("E. Review")

st.metric("Labor Contribution", f"${labor_value:,.2f}")
st.metric("Travel Contribution (Allocated)", f"${travel_value:,.2f}")
st.metric("Total OT5 Value", f"${total_ot5:,.2f}")

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
                "Firm": [firm_table[firm_name]["id"]],
                "Economy": [economy_table[host_economy]["id"]],
                "Engagement": [workshop_table[selected_workshop]["id"]],
                "Workstream": [workstream_table[workstream_name]["id"]] if workstream_name else []
            }
        }

        r = requests.post(OT5_URL, headers=HEADERS, json=payload)

        if r.status_code in [200,201]:
            st.success("OT5 record successfully created.")
        else:
            st.error(f"Airtable submission failed ({r.status_code})")
            st.json(r.json())
