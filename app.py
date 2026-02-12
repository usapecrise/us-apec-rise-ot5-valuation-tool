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
st.title("OT5 / PSE-4 Private Sector Valuation Tool")
st.caption("Agenda-based labor valuation, auto airfare logic, Airtable submission")

# =========================================================
# AIRTABLE CONFIG
# =========================================================
AIRTABLE_TOKEN = st.secrets["AIRTABLE_TOKEN"]
AIRTABLE_BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
AIRTABLE_TABLE = st.secrets["AIRTABLE_OT5_TABLE"]

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
# LOAD AIRTABLE TABLES (NO CACHING)
# =========================================================
def load_full_table(table_name):
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

    return records


# Load tables fresh every run
economy_records = load_full_table("Economy Reference List")
firm_records = load_full_table("OT4 Private Sector Firms")
workshop_records = load_full_table("Workshop Reference List")

# Convert to dictionaries
economy_lookup = {
    rec["fields"]["Economy"]: rec
    for rec in economy_records
    if "Economy" in rec["fields"]
}

firm_lookup = {
    rec["fields"]["Firm"]: rec
    for rec in firm_records
    if "Firm" in rec["fields"]
}

workshop_lookup = {
    rec["fields"]["Workshop"]: rec
    for rec in workshop_records
    if "Workshop" in rec["fields"]
}

# =========================================================
# AGENDA PARSING (ROBUST)
# =========================================================
def extract_text(uploaded_file):
    reader = PdfReader(BytesIO(uploaded_file.read()))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_agenda_hours(text, speaker_name):
    if not speaker_name:
        return 0.0

    text = text.replace("–", "-")
    speaker_name = speaker_name.lower()

    pattern = r"(\d{1,2}:\d{2})\s*(am|pm)?\s*-\s*(\d{1,2}:\d{2})\s*(am|pm)?"

    matches = list(re.finditer(pattern, text, re.IGNORECASE))

    total = 0.0

    for i, match in enumerate(matches):
        start_time = match.group(1)
        start_ampm = match.group(2)
        end_time = match.group(3)
        end_ampm = match.group(4)

        block_start = match.end()
        block_end = matches[i+1].start() if i+1 < len(matches) else len(text)
        block = text[block_start:block_end].lower()

        if speaker_name in block:
            start_dt = datetime.strptime(f"{start_time} {start_ampm}", "%I:%M %p")
            end_dt = datetime.strptime(f"{end_time} {end_ampm}", "%I:%M %p")
            diff = (end_dt - start_dt).seconds / 3600
            total += diff

    return round(total, 2)


# =========================================================
# AIRFARE LOGIC USING REGION FIELD
# =========================================================
def calculate_airfare(origin, host):
    origin_region = economy_lookup.get(origin, {}).get("fields", {}).get("Region")
    host_region = economy_lookup.get(host, {}).get("fields", {}).get("Region")

    if not origin_region or not host_region:
        return AIRFARE_BANDS["Intercontinental"]

    if origin == host:
        return AIRFARE_BANDS["Domestic"]

    if origin_region == host_region:
        return AIRFARE_BANDS["Regional"]

    return AIRFARE_BANDS["Intercontinental"]


# =========================================================
# UI
# =========================================================
st.header("A. Speaker & Level of Effort")

speaker = st.text_input("Speaker Name")
agenda_file = st.file_uploader("Upload Agenda (PDF)", type=["pdf"])

agenda_text = ""
if agenda_file:
    agenda_text = extract_text(agenda_file)

auto_hours = parse_agenda_hours(agenda_text, speaker)

presentation_hours = st.number_input(
    "Presentation Hours (auto-detected)",
    value=float(auto_hours),
    step=0.25
)

seniority = st.selectbox("Seniority Category", list(HOURLY_RATES.keys()))

labor_hours = round(presentation_hours * LABOR_MULTIPLIER, 2)
labor_value = round(labor_hours * HOURLY_RATES[seniority], 2)

# =========================================================
st.header("B. Travel")

firm = st.selectbox("Firm", sorted(firm_lookup.keys()))
host = st.selectbox("Host Economy", sorted(economy_lookup.keys()))

firm_origin = firm_lookup.get(firm, {}).get("fields", {}).get("Economy")

auto_airfare = calculate_airfare(firm_origin, host)

st.info(f"Auto-calculated airfare: ${auto_airfare:,}")

travel_start = st.date_input("Travel Start")
travel_end = st.date_input("Travel End")

lodging = st.number_input("Lodging (per night)", min_value=0.0)
mie = st.number_input("M&IE (per day)", min_value=0.0)

travel_days = (travel_end - travel_start).days + 1
nights = max(travel_days - 1, 0)

travel_value = round(
    auto_airfare +
    (lodging * nights) +
    (mie * travel_days),
    2
)

# =========================================================
st.header("C. Engagement")

engagement = st.selectbox("Engagement (Workshop)", sorted(workshop_lookup.keys()))

engagement_record = workshop_lookup.get(engagement)
engagement_id = engagement_record["id"] if engagement_record else None
workstream_id = None

if engagement_record:
    workstream_links = engagement_record["fields"].get("Workstream")
    if workstream_links:
        workstream_id = workstream_links[0]

# =========================================================
# REVIEW
# =========================================================
st.header("D. Review")

total_value = round(labor_value + travel_value, 2)
fiscal_year = f"FY{str(date.today().year)[-2:]}"

st.metric("Labor Value", f"${labor_value:,.2f}")
st.metric("Travel Value", f"${travel_value:,.2f}")
st.metric("Total OT5 Value", f"${total_value:,.2f}")
st.write(f"Fiscal Year: {fiscal_year}")

# =========================================================
# SUBMIT
# =========================================================
if st.checkbox("Confirm OT5 estimate is correct"):
    if st.button("Submit OT5 Record to Airtable"):

        payload = {
            "fields": {
                "Amount": total_value,
                "Contribution Date": date.today().isoformat(),
                "Fiscal Year": fiscal_year,
                "Resource Type": "In-kind",
                "Economy": [economy_lookup[host]["id"]],
                "Firm": [firm_lookup[firm]["id"]],
                "Engagement": [engagement_id] if engagement_id else [],
                "Workstream": [workstream_id] if workstream_id else []
            }
        }

        r = requests.post(AIRTABLE_URL, headers=HEADERS, json=payload)

        if r.status_code in [200, 201]:
            st.success("OT5 record successfully created.")
        else:
            st.error(f"Submission failed ({r.status_code})")
            st.json(r.json())
