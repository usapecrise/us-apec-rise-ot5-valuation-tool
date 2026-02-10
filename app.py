import streamlit as st
import re
from datetime import datetime
from io import BytesIO
from PyPDF2 import PdfReader

# =========================================================
# APP CONFIG
# =========================================================
st.set_page_config(page_title="OT5 Valuation Tool", layout="centered")
st.title("OT5 / PSE-4 Private Sector Valuation Tool")
st.caption("Labor category and hours derived from official workshop agenda")

# =========================================================
# CONSTANTS (FIXED FOR PROJECT LIFE)
# =========================================================
HOURLY_RATES = {
    "Executive / Senior Leadership": 149,
    "Senior Specialist": 131
}

LABOR_MULTIPLIER = 3.5          # 1x presentation + 2x prep + 0.5x follow-up
STANDARD_TRAVEL_DAYS = 2
TRAVEL_DAY_MIE_FACTOR = 0.75

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
        start_idx = match.end()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(agenda_text)
        block = agenda_text[start_idx:end_idx]

        if speaker in block.lower():
            return block

    return ""


def extract_speaker_hours(agenda_text, speaker_name):
    speaker = speaker_name.lower().strip()
    total_hours = 0.0

    time_pattern = r"(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})"
    matches = list(re.finditer(time_pattern, agenda_text))

    for i, match in enumerate(matches):
        start_time, end_time = match.groups()
        start_idx = match.end()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(agenda_text)
        session_block = agenda_text[start_idx:end_idx].lower()

        if speaker in session_block:
            s = datetime.strptime(start_time, "%H:%M")
            e = datetime.strptime(end_time, "%H:%M")
            total_hours += (e - s).seconds / 3600

    return round(total_hours, 2)


def assess_seniority_from_agenda(agenda_block):
    """
    Assigns labor category based solely on agenda-listed current role titles.
    """
    t = agenda_block.lower()

    executive_title_patterns = [
        r"\bceo\b",
        r"\bcoo\b",
        r"\bcfo\b",
        r"\bchief .* officer\b",
        r"\bpresident\b",
        r"\bvice president\b",
        r"\bvp\b",
        r"\bmanaging director\b",
        r"\bpartner\b",
        r"\bsenior partner\b",
        r"\bprincipal\b",
        r"\bfounder\b",
        r"\bco[- ]?founder\b",
        r"\bcountry director\b",
        r"\bregional director\b",
        r"\bgeneral manager\b",
        r"\bdepartment head\b",
        r"\bhead of\b"
    ]

    for pattern in executive_title_patterns:
        if re.search(pattern, t):
            return (
                "Executive / Senior Leadership",
                f"Agenda-listed title matched pattern: '{pattern}'"
            )

    return (
        "Senior Specialist",
        "Agenda-listed title does not meet Executive / Senior Leadership criteria"
    )


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

    return round(allocated_travel, 2)


def derive_usg_fiscal_year(d):
    return d.year + 1 if d.month >= 10 else d.year

# =========================================================
# A. SPEAKER & AGENDA
# =========================================================
st.subheader("A. Speaker & Agenda")

speaker_name = st.text_input("Speaker Name")

agenda_file = st.file_uploader("Upload Agenda (PDF)", type=["pdf"])

agenda_text = ""
if agenda_file:
    agenda_text = extract_text_from_pdf(agenda_file)

agenda_text = st.text_area("Agenda Text", value=agenda_text, height=260)

agenda_block = ""
presentation_hours = 0.0

if speaker_name and agenda_text:
    agenda_block = extract_person_agenda_block(agenda_text, speaker_name)
    presentation_hours = extract_speaker_hours(agenda_text, speaker_name)

presentation_hours = st.number_input(
    "Presentation Hours (auto-detected; override if needed)",
    value=presentation_hours,
    step=0.25
)

if speaker_name and agenda_text and presentation_hours == 0:
    st.warning("Speaker name not matched to agenda sessions. Check spelling or override hours.")

# =========================================================
# B. LABOR CATEGORY (AGENDA ONLY)
# =========================================================
st.subheader("B. Labor Category (Agenda-Based)")

if agenda_block:
    suggested_category, rationale = assess_seniority_from_agenda(agenda_block)
else:
    suggested_category = "Senior Specialist"
    rationale = "No agenda block found for speaker"

st.info(f"Suggested Category: **{suggested_category}**")
st.caption(rationale)
st.caption(
    "Labor category is determined solely from the speaker’s current role "
    "as listed in the official workshop agenda. Staff may override if needed."
)

category = st.selectbox(
    "Confirm or Override Category",
    options=list(HOURLY_RATES.keys()),
    index=list(HOURLY_RATES.keys()).index(suggested_category)
)

labor_value = calculate_labor(category, presentation_hours)
st.markdown(f"**Labor Contribution:** ${labor_value:,.2f}")

# =========================================================
# C. TRAVEL VALUATION
# =========================================================
st.subheader("C. Travel Valuation")

travel_start = st.date_input("Travel Start Date")
travel_end = st.date_input("Travel End Date")

airfare = st.number_input("Estimated Round-Trip Airfare (USD)", min_value=0.0)
lodging_rate = st.number_input("DOS Lodging Rate per Night (USD)", min_value=0.0)
mie_rate = st.number_input("DOS M&IE Rate per Day (USD)", min_value=0.0)

workshops_on_trip = st.number_input(
    "Number of US APEC–RISE Workshops on This Trip",
    min_value=1,
    step=1
)

travel_value = calculate_travel(
    airfare,
    lodging_rate,
    mie_rate,
    travel_start,
    travel_end,
    workshops_on_trip
)

st.markdown(f"**Allocated Travel Contribution:** ${travel_value:,.2f}")

# =========================================================
# D. MANUAL POLICY FIELDS
# =========================================================
st.subheader("D. Policy Classification (Manual)")

firm_name = st.text_input("Firm Name")
host_economy = st.text_input("Host Economy")

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

contribution_date = st.date_input("Contribution Date")
fiscal_year = f"FY {derive_usg_fiscal_year(contribution_date)}"

# =========================================================
# E. FINAL REVIEW
# =========================================================
st.subheader("E. Review Summary")

total_ot5 = round(labor_value + travel_value, 2)

st.metric("Total OT5 Contribution (USD)", f"${total_ot5:,.2f}")
st.markdown(f"**Fiscal Year:** {fiscal_year}")

st.write({
    "Presentation Hours": presentation_hours,
    "Labor Value": labor_value,
    "Travel Value": travel_value,
    "Total OT5 Value": total_ot5
})

st.caption(
    "Final values should be entered into the Airtable "
    "‘OT5 Private Sector Resources’ table as the system of record."
)
