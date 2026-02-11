import streamlit as st
import re
from datetime import datetime, date
from io import BytesIO
from PyPDF2 import PdfReader

# =========================================================
# APP CONFIG
# =========================================================
st.set_page_config(page_title="OT5 Valuation Tool", layout="centered")
st.title("OT5 / PSE-4 Private Sector Valuation Tool")
st.caption("Labor, travel, and contribution date derived from official workshop agenda")

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
# HELPERS
# =========================================================
def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(BytesIO(uploaded_file.read()))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_person_agenda_block(agenda_text, speaker_name):
    speaker = speaker_name.lower().strip()
    time_pattern = r"(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})"
    matches = list(re.finditer(time_pattern, agenda_text))

    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(agenda_text)
        block = agenda_text[start:end]
        if speaker in block.lower():
            return block
    return ""


def extract_speaker_hours(agenda_text, speaker_name):
    speaker = speaker_name.lower().strip()
    total = 0.0
    time_pattern = r"(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})"
    matches = list(re.finditer(time_pattern, agenda_text))

    for i, match in enumerate(matches):
        start_time, end_time = match.groups()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(agenda_text)
        block = agenda_text[start:end].lower()

        if speaker in block:
            s = datetime.strptime(start_time, "%H:%M")
            e = datetime.strptime(end_time, "%H:%M")
            total += (e - s).seconds / 3600

    return round(total, 2)


def assess_seniority_from_agenda(agenda_block):
    t = agenda_block.lower()

    executive_titles = [
        r"\bceo\b", r"\bcoo\b", r"\bcfo\b", r"\bchief .* officer\b",
        r"\bpresident\b", r"\bvice president\b", r"\bvp\b",
        r"\bmanaging director\b", r"\bpartner\b", r"\bsenior partner\b",
        r"\bprincipal\b", r"\bfounder\b", r"\bco[- ]?founder\b",
        r"\bcountry director\b", r"\bregional director\b",
        r"\bgeneral manager\b", r"\bdepartment head\b", r"\bhead of\b"
    ]

    for p in executive_titles:
        if re.search(p, t):
            return "Executive / Senior Leadership", f"Matched agenda title pattern: {p}"

    return "Senior Specialist", "No executive-level title detected in agenda"


def extract_contribution_date(agenda_text):
    """
    Extracts the FIRST date mentioned in the agenda.
    Used as contribution date for multi-day workshops.
    """
    date_patterns = [
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
        r"\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}"
    ]

    for pattern in date_patterns:
        match = re.search(pattern, agenda_text)
        if match:
            return datetime.strptime(match.group(), "%B %d, %Y").date()

    return None


def calculate_labor(category, hours):
    total_hours = hours * LABOR_MULTIPLIER
    return round(total_hours, 2), round(HOURLY_RATES[category] * total_hours, 2)


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

# =========================================================
# A. SPEAKER & AGENDA
# =========================================================
st.subheader("A. Speaker & Agenda")

speaker_name = st.text_input("Speaker Name")

agenda_file = st.file_uploader("Upload Agenda (PDF)", type=["pdf"])
agenda_text = extract_text_from_pdf(agenda_file) if agenda_file else ""

agenda_text = st.text_area("Agenda Text", value=agenda_text, height=260)

agenda_block = extract_person_agenda_block(agenda_text, speaker_name) if speaker_name else ""
presentation_hours = extract_speaker_hours(agenda_text, speaker_name) if speaker_name else 0.0

presentation_hours = st.number_input(
    "Presentation Hours (auto-detected; override if needed)",
    value=presentation_hours,
    step=0.25
)

# =========================================================
# B. LABOR CATEGORY
# =========================================================
st.subheader("B. Labor Category (Agenda-Based)")

category, category_rationale = assess_seniority_from_agenda(agenda_block)
st.info(f"Suggested Category: **{category}**")
st.caption(category_rationale)

category = st.selectbox(
    "Confirm or Override Category",
    list(HOURLY_RATES.keys()),
    index=list(HOURLY_RATES.keys()).index(category)
)

labor_hours, labor_value = calculate_labor(category, presentation_hours)

# =========================================================
# C. TRAVEL VALUATION
# =========================================================
st.subheader("C. Travel Valuation")

trip_type = st.selectbox("Trip Type", list(AIRFARE_BANDS.keys()))
airfare = AIRFARE_BANDS[trip_type]

travel_start = st.date_input("Travel Start Date")
travel_end = st.date_input("Travel End Date")

lodging_rate = st.number_input("DOS Lodging Rate per Night (USD)", min_value=0.0)
mie_rate = st.number_input("DOS M&IE Rate per Day (USD)", min_value=0.0)

workshops_on_trip = st.number_input("Workshops on This Trip", min_value=1, step=1)

travel = calculate_travel(
    airfare, lodging_rate, mie_rate,
    travel_start, travel_end, workshops_on_trip
)

# =========================================================
# D. CONTRIBUTION DATE
# =========================================================
st.subheader("D. Contribution Date")

auto_contribution_date = extract_contribution_date(agenda_text)
contribution_date = st.date_input(
    "Contribution Date (from agenda; override if needed)",
    value=auto_contribution_date or date.today()
)

fiscal_year = f"FY {derive_usg_fiscal_year(contribution_date)}"

# =========================================================
# E. BREAKDOWN & REVIEW
# =========================================================
st.subheader("E. Valuation Breakdown")

st.markdown("### Labor Calculation")
st.write({
    "Presentation Hours": presentation_hours,
    "Labor Multiplier": LABOR_MULTIPLIER,
    "Total Labor Hours": labor_hours,
    "Hourly Rate": HOURLY_RATES[category],
    "Labor Value (USD)": labor_value
})

st.markdown("### Travel Calculation")
st.write({
    "Standardized Airfare": airfare,
    "Lodging Nights": travel["nights"],
    "Lodging Cost": travel["lodging"],
    "M&IE (Travel Days)": travel["mie_travel"],
    "M&IE (Full Days)": travel["mie_full"],
    "Allocated Travel Value": travel["allocated"]
})

total_ot5 = round(labor_value + travel["allocated"], 2)

st.markdown("### Final OT5 Value")
st.metric("Total OT5 Contribution (USD)", f"${total_ot5:,.2f}")
st.markdown(f"**Contribution Date:** {contribution_date}")
st.markdown(f"**Fiscal Year:** {fiscal_year}")

st.caption(
    "Final OT5 values should be entered into the Airtable "
    "‘OT5 Private Sector Resources’ table as the system of record."
)
