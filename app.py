import streamlit as st
import re
import requests
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
# AIRTABLE CONFIG
# =========================================================
try:
    AIRTABLE_TOKEN = st.secrets["AIRTABLE_TOKEN"]
    AIRTABLE_BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
    AIRTABLE_TABLE = st.secrets["AIRTABLE_OT5_TABLE"]
except Exception:
    st.error("Missing Airtable secrets in Streamlit settings.")
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

# =========================================================
# HELPERS
# =========================================================
def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(BytesIO(uploaded_file.read()))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

# ✅ FIXED VERSION (Handles Your Agenda Format)
def extract_speaker_hours(text, speaker):
    speaker = speaker.lower()
    total = 0.0

    time_pattern = r"(\d{1,2}:\d{2})(?:\s*(am|pm))?\s*[–\-]\s*(\d{1,2}:\d{2})(?:\s*(am|pm))?"
    matches = list(re.finditer(time_pattern, text, re.IGNORECASE))

    for i, m in enumerate(matches):
        start_time, start_ampm, end_time, end_ampm = m.groups()

        # If only end has am/pm, apply it to start
        if not start_ampm and end_ampm:
            start_ampm = end_ampm

        if not start_ampm:
            start_ampm = "am"
        if not end_ampm:
            end_ampm = start_ampm

        start_index = m.start()
        end_index = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start_index:end_index].lower()

        if speaker in block:
            try:
                s = datetime.strptime(f"{start_time} {start_ampm}", "%I:%M %p")
                e = datetime.strptime(f"{end_time} {end_ampm}", "%I:%M %p")

                # Handle noon crossover
                if e < s:
                    e = e.replace(hour=e.hour + 12)

                duration = (e - s).seconds / 3600
                total += duration
            except:
                continue

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
# AGENDA
# =========================================================
st.subheader("A. Agenda & Speaker")

speaker_name = st.text_input("Speaker Name")
agenda_file = st.file_uploader("Upload Agenda (PDF)", type=["pdf"])
agenda_text = extract_text_from_pdf(agenda_file) if agenda_file else ""
agenda_text = st.text_area("Agenda Text", value=agenda_text, height=260)

presentation_hours = extract_speaker_hours(agenda_text, speaker_name)
presentation_hours = st.number_input("Presentation Hours", value=presentation_hours, step=0.25)

# =========================================================
# LABOR
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
# TRAVEL
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
# POLICY FIELDS
# =========================================================
st.subheader("D. Policy Fields")

firm_name = st.selectbox("Firm Name", sorted(firm_dict.keys()))
host_economy = st.selectbox("Host Economy", sorted(economy_dict.keys()))

resource_origin = st.selectbox(
    "Resource Origin",
    ["US-based", "Host Country-based", "Third Country-based"]
)

fao = st.selectbox(
    "U.S. FAOs Addressed",
    FAO_OPTIONS,
    index=FAO_OPTIONS.index("Economic Growth (Other)")
)

# =========================================================
# REVIEW
# =========================================================
total_ot5 = round(labor_value + travel_value, 2)
fy_number = derive_usg_fiscal_year(date.today()) % 100
fiscal_year = f"FY{fy_number}"

st.subheader("E. Review & Submit")

st.write({
    "Presentation Hours": presentation_hours,
    "Labor Value": labor_value,
    "Travel Value": travel_value,
    "Total OT5 Value": total_ot5,
    "Fiscal Year": fiscal_year
})

# =========================================================
# SUBMIT
# =========================================================
if st.checkbox("I confirm this OT5 valuation is correct"):
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
                "Firm": [firm_dict[firm_name]]
            }
        }

        r = requests.post(AIRTABLE_URL, headers=HEADERS, json=payload)

        if r.status_code in [200, 201]:
            st.success("OT5 record successfully created in Airtable.")
        else:
            st.error(f"Airtable submission failed ({r.status_code})")
            st.json(r.json())
