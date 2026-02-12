import streamlit as st
import re
import requests
import urllib.parse
from datetime import datetime, date
from io import BytesIO
from PyPDF2 import PdfReader
import math

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(page_title="OT5 Valuation Tool", layout="centered")

st.title("OT5 / PSE-4 Private Sector Contribution Tool")
st.caption("Agenda-based labor valuation · Region-based airfare · Multi-event allocation")

# =========================================================
# AIRTABLE CONFIG
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

def airtable_url(table_name):
    return f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(table_name)}"

# =========================================================
# CONSTANTS
# =========================================================
HOURLY_RATES = {
    "Executive / Senior Leadership": 149,
    "Senior Specialist": 131
}

LABOR_MULTIPLIER = 3.5
TRAVEL_DAY_MIE_FACTOR = 0.75
STANDARD_TRAVEL_DAYS = 2

REGION_MATRIX = {
    "North America": 700,
    "Latin America": 900,
    "Asia-Pacific": 1400,
    "Oceania": 1500
}

ECONOMY_REGION = {
    "Australia": "Oceania",
    "Chile": "Latin America",
    "Mexico": "Latin America",
    "United States": "North America",
    "Japan": "Asia-Pacific",
    "Viet Nam": "Asia-Pacific"
}

VALID_FYS = ["FY25", "FY26", "FY27", "FY28", "FY29", "FY30"]

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
        if r.status_code != 200:
            raise Exception(r.text)

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
# SECTION A – SPEAKER & LOE (AUTO)
# =========================================================
st.header("A. Speaker & Level of Effort")

speaker_name = st.text_input("Speaker Name")

agenda_file = st.file_uploader("Upload Agenda PDF", type=["pdf"])

auto_hours = 0.0

if agenda_file and speaker_name:
    reader = PdfReader(BytesIO(agenda_file.read()))
    agenda_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    pattern = r"(\d{1,2}:\d{2})\s*[–\-]\s*(\d{1,2}:\d{2})"
    match
