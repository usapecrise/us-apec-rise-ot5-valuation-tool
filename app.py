import streamlit as st
import re
import requests
import os
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
# AIRTABLE CONFIG (SECRETS)
# =========================================================
AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE = os.getenv("AIRTABLE_TABLE_NAME")

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}

AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE}"

# =========================================================
# CONSTANTS (POLICY-FIXED)
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
# HELPERS
# =========================================================
def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(BytesIO(uploaded_file.read()))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_person_agenda_block(text, speaker):
    speaker = speaker.lower()
    time_pattern = r"(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})"
    matches = list(re.finditer(time_pattern, text))

    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        if speaker in block.lower():
            return block
    return ""


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


def assess_seniority_from_agenda(block):
    titles = [
        r"\bceo\b", r"\bcoo\b", r"\bcfo\b", r"\bchief .* officer\b",
        r"\bpresident\b", r"\bvice president\b", r"\bvp\b",
        r"\bmanaging director\b", r"\bpartner\b", r"\bprincipal\b",
        r"\bfounder\b", r"\bco[- ]?founder\b",
        r"\bcountry director\b", r"\bregional director\b",
        r"\bgeneral manager\b", r"\bdepartment head\b", r"\bhead of\b"
    ]
    for t in titles:
        if re.search(t, block.lower()):
            return "Executive / Senior Leadership", t
    return "Senior Specialist", "No executive title detected"


def extract_contribution_date(text):
    pattern = r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}"
    match = re.search(pattern, text)
    if match:
        return datetime.strptime(match.group(), "%B %d, %Y").date()
    return None


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
    return {
        "days": days,
        "nights": nights,
        "lodging": round(lodging, 2),
        "mie_travel": round(mie_travel, 2),
        "mie_full": round(mie_full, 2),
        "allocated": round(total / workshops, 2)
    }


def derive_usg_fiscal_year(d):
    return d.year + 1 if d.month >= 10 else d.year


def get_linked_record_id(table, field, value):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table}"
    params = {"filterByFormula": f"{{{field}}}='{value}'"}
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    records = r.json().get("records", [])
    return records[0]["id"] if records else None

# =========================================================
# A. AGENDA INPUT
# =========================================================
st.subheader("A. Agenda & Speaker")

speaker_name = st.text_input("Speaker Name")

agenda_file = st.file_uploader("Upload Agenda (PDF)", type=["pdf"])
agenda_text = extract_text_from_pdf(agenda_file) if agenda_file else ""

agenda_text = st.text_area("Agenda Text", value=agenda_text, height=260)

agenda_block = extract_person_agenda_block(agenda_text, speaker_name)
presentation_hours = extract_speaker_hours(agenda_text, speaker_name)

presentation_hours = st.number_input(
    "Presentation Hours (auto-detected; override if needed)",
    value=presentation_hours,
    step=0.25
)

# =========================================================
# B. LABOR
# =========================================================
st.subheader("B. Labor Valuation")

category, rationale = assess_seniority_from_agenda(agenda_block)
st.info(f"Suggested Category: {category}")
st.caption(f"Agenda trigger: {rationale}")

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

lodging_rate = st.number_input("DOS Lodging Rate (USD/night)", min_value=0.0)
mie_rate = st.number_input("DOS M&IE Rate (USD/day)", min_value=0.0)

workshops_on_trip = st.number_input("Workshops on this trip", min_value=1, step=1)

travel = calculate_travel(
    airfare, lodging_rate, mie_rate,
    travel_start, travel_end, workshops_on_trip
)

# =========================================================
# D. CONTRIBUTION DATE
# =========================================================
st.subheader("D. Contribution Date")

auto_date = extract_contribution_date(agenda_text)
contribution_date = st.date_input(
    "Contribution Date (from agenda; override if needed)",
    value=auto_date or date.today()
)

fiscal_year = f"FY {derive_usg_fiscal_year(contribution_date)}"

# =========================================================
# E. POLICY FIELDS
# =========================================================
st.subheader("E. Policy Fields")

firm_name = st.text_input("Firm Name")
host_economy = st.text_input("Host Economy")

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
# F. REVIEW
# =========================================================
st.subheader("F. Review & Submit")

total_ot5 = round(labor_value + travel["allocated"], 2)

st.write({
    "Presentation Hours": presentation_hours,
    "Total Labor Hours": labor_hours,
    "Labor Value": labor_value,
    "Travel Value": travel["allocated"],
    "Total OT5 Value": total_ot5,
    "Fiscal Year": fiscal_year
})

# =========================================================
# G. SUBMIT TO AIRTABLE
# =========================================================
if st.checkbox("I confirm this OT5 valuation is correct and ready to submit"):
    if st.button("Submit OT5 Record to Airtable"):
        economy_id = get_linked_record_id("Economy Reference List", "Economy", host_economy)
        firm_id = get_linked_record_id("Firm Reference List", "Firm", firm_name)

        if not economy_id:
            st.error("Economy not found in reference table.")
            st.stop()

        payload = {
            "fields": {
                "Amount": total_ot5,
                "Indicator ID": "OT5",
                "Contribution Date": contribution_date.isoformat(),
                "Fiscal Year": fiscal_year,
                "Resource Type": "In-kind",
                "Resource Origin": resource_origin,
                "U.S. FAOs Addressed": faos,
                "Economy": [economy_id],
                "Firm": [firm_id] if firm_id else []
            }
        }

        r = requests.post(AIRTABLE_URL, headers=HEADERS, json=payload)

        if r.status_code == 200:
            st.success("OT5 record successfully created in Airtable.")
        else:
            st.error("Airtable submission failed.")
            st.json(r.json())
