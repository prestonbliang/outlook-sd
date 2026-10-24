"""NWS API: active alerts (live) and IEM's archive of NWS warnings (history, for baselines)."""
import io

import pandas as pd

from ._common import get, upsert

ALERTS = "https://api.weather.gov/alerts/active"
IEM = "https://mesonet.agron.iastate.edu/cgi-bin/request/gis/watchwarn.py"
# VTEC (phenomenon, significance): Red Flag Warning, Coastal Flood Warning/Advisory, Heat Advisory,
# Excessive Heat Warning, Extreme Heat Warning
PRODUCTS = [("FW", "W"), ("CF", "W"), ("CF", "Y"), ("HT", "Y"), ("EH", "W"), ("XH", "W")]


def fetch_live():
    js = get("nws_alerts", ALERTS, {"area": "CA"}, ext="json").json()
    rows = [f["properties"] for f in js["features"] if f["properties"].get("senderName") == "NWS San Diego CA"]
    cols = ["id", "event", "severity", "headline", "areaDesc", "onset", "ends", "expires"]
    return pd.DataFrame([{c: p.get(c) for c in cols} for p in rows], columns=cols)


def fetch_history(start="2010-01-01", end=None):
    """All SGX (San Diego office) warnings/advisories for the phenomena above, from IEM."""
    end = end or pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    frames = []
    for ph, sig in PRODUCTS:  # IEM honours one phenomenon/significance pair per request
        params = {"accept": "csv", "sts": f"{start}T00:00Z", "ets": f"{end}T00:00Z", "wfos[]": "SGX",
                  "limitps": "yes", "phenomena": ph, "significance": sig}
        r = get("iem_warnings", IEM, params, ext="csv", timeout=600)
        frames.append(pd.read_csv(io.StringIO(r.text)))  # columns: wfo, utc_issue, utc_expire, phenomena, significance, ugc…
    df = pd.concat(frames, ignore_index=True)
    for c in ["utc_issue", "utc_expire"]:
        df[c] = pd.to_datetime(df[c], utc=True, errors="coerce")
    df["tz_source"] = "UTC"
    return upsert(df, "nws_warnings", ["wfo", "phenomena", "significance", "eventid", "ugc", "utc_issue"])
