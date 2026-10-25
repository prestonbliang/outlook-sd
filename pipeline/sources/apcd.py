"""San Diego APCD air-quality complaint log (public XLSX, updated every few days). We keep odor complaints only."""
import io

import pandas as pd

from ._common import get, write

URL = ("https://www.sdapcd.org/content/dam/sdapcd/documents/compliance/air-quality-complaint-list/"
       "Complaint-Report.xlsx")
PAGE = "https://www.sdapcd.org/content/sdapcd/compliance/Complaint-Info-Dataset.html"
# Imperial Beach, San Ysidro, Otay Mesa/Nestor, Chula Vista (west), Coronado — downwind of the Tijuana River valley
SOUTH_BAY = ["91932", "91950", "92154", "92173", "91910", "91911", "92118"]


def parse(content):
    d = pd.read_excel(io.BytesIO(content))
    d = d[d.COMPLAINT_TYPE.str.strip().str.lower() == "odor"]
    return pd.DataFrame({"record": d.COMPLAINT_RECORD, "zip": d.ZIP.astype(str).str[:5], "city": d.CITY,
                         "date": pd.to_datetime(d.DATE_RECEIVED).dt.date, "outcome": d.INVESTIGATION_OUTCOME,
                         "tz_source": "America/Los_Angeles (date only)"}).reset_index(drop=True)


def fetch_live():
    return write(parse(get("apcd", URL, ext="xlsx").content), "odor_complaints")


fetch_history = fetch_live  # the file holds the full record since 2018
