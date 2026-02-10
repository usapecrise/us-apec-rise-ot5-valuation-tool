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
st.caption("Implements standardized OT5 methodology (labor + travel valuation)")

# =========================================================
# CONSTANTS
# =========================================================
HOURLY_RATES = {
    "Executive / Senior Leadership": 149,
    "Senior Specialist": 131
}

LABOR_MULTIPLIER = 3.5          # 1x presentation + 2x prep + 0.5x follow-up
STANDARD_TRAVEL_DAYS = 2        # Outbound + return
TRAVEL_DAY_MIE_FACTOR = 0.75    # 75% M&IE on travel days

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


def extract_speaker_hours(agenda_text, speaker_name):
    """
    Extracts presentation hours ONLY for agenda lines
    that contain the speaker's name.
    """
    total_hours = 0.0
    speaker_lower = speaker_name.lower()

    lines = agenda_text.splitlines()
    time_pattern = r"(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})"

    for line in lines:
        if speaker_lower in line.lower():
            matches = re.findall(time_pattern, line)
            for start, end in matches:
                s = datetime.strptime(start, "%H:%M")
                e = datetime.strptime(end, "%H:%M")
                total_hours += (e - s).seconds / 3600

    return round(total_hours, 2)


def assess_seniority(bio_text):
    executive_keywords = [
        "ceo", "coo", "cfo", "president", "vice president", "vp",
        "managing director", "partner", "country director",
        "regional director", "chief", "head of"
    ]

    text = bio_text.lower()
    for kw in executive_keywords:
        if kw in text:
            return "Executive / Senior Leadership", f"Detected keyword: '{kw}'"

    return "Senior Specialist", "No executive-level keywords detected"


def calculate_labor(category, presentation_hours):
    return round(
        HOURLY_RATES[category] * presentation_hours * LABOR_MULTIPLIER, 2
    )


def calculate_travel(
    airfare,
    lodging_rate,
    mie_rate,
    start_date,
    end_date,
    workshops_on_trip
):
    days = (end_date - start_date).days + 1
    nights = max(days - 1, 0)

    lodging_cost = lodging_rate * nights
    mie_travel_days = mie_rate * TRAVEL_DAY_MIE_FACTOR * STANDARD_TRAVEL_DAYS
    mie_full_days = mie_rate * max(days - STANDARD_TRAVEL_DAYS, 0)

    total_travel = airfare + lodging_cost + mie_travel_days + mie_full_days
    allocated_travel = total_travel / workshops_on_trip

    return {
        "days": days,
        "nights": nights,
        "lodging_cost": round(lodging_cost, 2),
        "mie_travel_days": round(mie_travel_days, 2),
        "mie_full_days": round(mie_full_days, 2),
        "total_travel": round(total_travel, 2),
        "allocated_travel": round(allocated_travel, 2)
    }


def derive_usg_fiscal_year(d):
    return d.year + 1 if d.month >= 10 else d.year

# =========================================================
# A. SPEAKER & AGENDA
# =========================================================
st.subheader("A. Speaker & Agenda")

speaker_name = st.text_input("Speaker Name")

agenda_file = st.file_uploader(
    "Upload Agenda (PDF) or paste agenda text below",
    type=["pdf"]
)

agenda_text = ""
if agenda_file:
    agenda_text = extract_text_from_pdf(agenda_file)

agenda_text = st.text_area(
    "Agenda Text",
    value=agenda_text,
    height=220,
    help="Agenda lines must include speaker name and session time (e.g., 10:00–11:00 Jane Smith)."
)

auto_hours = 0.0
if speaker_name and agenda_text:
    auto_hours = extract_speaker_hours(agenda_text, speaker_name)

presentation_hours = st.number_input(
    "Presentation Hours (auto-detected; override if needed)",
    value=auto_hours,
    step=0.25
)

if speaker_name and agenda_text and auto_hours == 0:
    st.warning(
        "No agenda sessions matched this speaker name. "
        "Check spelling or override presentation hours manually."
    )

# =========================================================
# B. BIO & SENIORITY
# =========================================================
st.subheader("B. Bio & Seniority Assessment")

bio_file = st.file_uploader(
    "Upload Speaker Bio / CV (PDF) or paste text below",
    type=["pdf"]
)

bio_text = ""
if bio_file:
    bio_text = extract_text_from_pdf(bio_file)

bio_text = st.text_area(
    "Bio Text",
    value=bio_text,
    height=200
)

suggested_category, rationale = assess_seniority(bio_text) if bio_text else (
    "Senior Specialist", "No bio provided"
)

st.info(f"Suggested category: **{suggested_category}**")
st.caption(f"Rationale: {rationale}")

category = st.selectbox(
    "Professional Category (confirm or override)",
    options=list(HOURLY_RATES.keys()),
    index=list(HOURLY_RATES.keys()).index(suggested_category)
)

labor_value = calculate_labor(category, presentation_hours)
st.markdown(f"**Labor Contribution:** ${labor_value:,.2f}")

# =========================================================
# C. TRAVEL (MANUAL PER DIEM ENTRY)
# =========================================================
st.subheader("C. Travel Valuation")

travel_start = st.date_input("Travel Start Date")
travel_end = st.date_input("Travel End Date")

airfare = st.number_input("Estimated Round-Trip Airfare (USD)", min_value=0.0)

lodging_rate = st.number_input(
    "DOS Lodging Rate per Night (USD)",
    min_value=0.0
)

mie_rate = st.number_input(
    "DOS M&IE Rate per Day (USD)",
    min_value=0.0
)

workshops_on_trip = st.number_input(
    "Number of US APEC–RISE Workshops on This Trip",
    min_value=1,
    step=1
)

travel = calculate_travel(
    airfare,
    lodging_rate,
    mie_rate,
    travel_start,
    travel_end,
    workshops_on_trip
)

st.markdown(f"**Allocated Travel Contribution:** ${travel['allocated_travel']:,.2f}")

# =========================================================
# D. MANUAL CLASSIFICATION
# =========================================================
st.subheader("D. Contribution Details")

firm_name = st.text_input("Firm Name")
host_economy = st.text_input("Host Economy (Workshop Location)")

resource_origin = st.selectbox(
    "Resource Origin",
    ["U.S.-based", "Host Country-based", "Third Country-based"]
)

resource_type = st.selectbox("Resource Type", ["In-kind"])

faos = st.multiselect(
    "U.S. FAOs Addressed",
    FAO_OPTIONS,
    default=["Economic Growth (Other)"]
)

contribution_date = st.date_input("Contribution Date (from agenda)")
fiscal_year = f"FY {derive_usg_fiscal_year(contribution_date)}"

# =========================================================
# E. REVIEW
# =========================================================
st.subheader("E. Review Summary")

total_ot5 = round(labor_value + travel["allocated_travel"], 2)

st.metric("Total OT5 Contribution (USD)", f"${total_ot5:,.2f}")
st.markdown(f"**Fiscal Year:** {fiscal_year}")

st.markdown("### Valuation Breakdown")
st.write({
    "Presentation Hours": presentation_hours,
    "Labor Value": labor_value,
    "Allocated Travel Value": travel["allocated_travel"],
    "Total OT5 Value": total_ot5
})

st.caption(
    "Enter the final OT5 amount and supporting documentation "
    "into the Airtable ‘OT5 Private Sector Resources’ table."
)
