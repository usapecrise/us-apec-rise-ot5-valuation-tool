# US APEC–RISE OT5 Private Sector Valuation Tool

## Overview

This repository contains the **OT5 / PSE-4 Private Sector Valuation Tool** developed for the **US APEC–RISE** program.  
The tool provides a **standardized, auditable, and policy-aligned method** for valuing private sector speaker and moderator contributions attributable to US APEC–RISE activities.

The methodology and calculations implemented here support reporting under **OT5 (PSE-4): “Reasonably quantifiable private sector resource commitments attributable to USG engagement.”**

---

## Purpose

This tool is designed to:
- Ensure **consistent valuation** of private sector in-kind contributions across workshops and economies
- Apply **fixed, transparent assumptions** aligned with U.S. Department of State guidance
- Maintain **traceability and audit readiness** for quarterly and annual reporting
- Support **human-in-the-loop decision-making** where professional judgment is required

The tool intentionally avoids automated data scraping or individual salary collection. Only publicly available or voluntarily provided information is used.

---

## What the Tool Does

The Streamlit application:
- Captures standardized inputs related to:
  - Speaker category
  - Presentation hours
  - Travel eligibility and duration
- Applies fixed labor and travel valuation formulas
- Separates **labor contribution** and **travel contribution**
- Produces a total OT5 valuation per workshop
- Supports documentation and justification for each valuation

The tool calculates values once and is intended to write final results into the program’s **Airtable OT5 Private Sector Resources** table, which serves as the system of record.

---

## Valuation Methodology (Summary)

### Labor Valuation
- Speakers are assigned to one of two standardized professional categories:
  - Executive / Senior Leadership
  - Senior Specialist
- Hourly rates are fixed for the life of the project
- Total labor hours are calculated as:
  
