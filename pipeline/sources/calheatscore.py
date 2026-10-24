"""CalHeatScore (CalEPA/OEHHA) ZIP heat score 0–4 for today + 6 days. Live only: no history exists, so we log it."""
import pandas as pd

from ._common import get, upsert

URL = ("https://services1.arcgis.com/PCHfdHz4GlDNAhBb/arcgis/rest/services/"
       "CalHeatScore_Live_Data_for_API_Use/FeatureServer/0/query")
DAYS = [f"CHS_Day_{i}" for i in range(7)]


def fetch_live(zips):
    where = "ZIP_CODE IN (" + ",".join(f"'{z}'" for z in zips) + ")"
    js = get("calheatscore", URL, {"where": where, "outFields": ",".join(["ZIP_CODE", "DATE", *DAYS]),
                                   "returnGeometry": "false", "f": "json"}, ext="json").json()
    df = pd.DataFrame([f["attributes"] for f in js["features"]])
    df = df.melt(id_vars=["ZIP_CODE", "DATE"], value_vars=DAYS, var_name="lead", value_name="chs")
    df = pd.DataFrame({"zip": df.ZIP_CODE, "issued": pd.to_datetime(df.DATE).dt.date,
                       "lead_days": df["lead"].str[-1].astype(int), "chs": pd.to_numeric(df.chs).astype("Int64")})
    df["target_date"] = (pd.to_datetime(df.issued) + pd.to_timedelta(df.lead_days, unit="D")).dt.date
    df["tz_source"] = "America/Los_Angeles (date only)"
    return upsert(df, "calheatscore_log", ["zip", "issued", "lead_days"])


fetch_history = None  # no historical archive is published (checked both OEHHA layers: 1 record per ZIP)
