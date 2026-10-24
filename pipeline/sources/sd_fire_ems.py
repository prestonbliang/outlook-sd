"""City of San Diego Fire-Rescue calls for service (data.sandiego.gov), aggregated to daily calls per ZIP."""
import io

import pandas as pd

from ._common import RAW, get, upsert

URL = "https://seshat.datasd.org/fire_ems_incidents/fd_incidents_{year}_datasd.csv"
# category names changed in 2021; both sets are medical
MEDICAL = {"Life-Threatening Emergency Response", "Urgent Response", "Non-Life-Threatening Response",
           "Emergency Medical Response", "Non-Emergency Medical Response", "Urgent Medical Response"}
DICT_URL = "https://seshat.datasd.org/fire_ems_incidents/fd_incidents_dictionary_datasd.csv"


def year_file(year, refresh=False):
    path = RAW / "sd_fire_ems" / f"fd_incidents_{year}.csv"
    if refresh or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(get("sd_fire_ems", URL.format(year=year), save=False, timeout=600).content)
    return pd.read_csv(path, dtype=str)


def daily_by_zip(df):
    """date_response is local time (America/Los_Angeles); calls counted per local date and 5-digit ZIP."""
    zips = df.address_zip.str.extract(r"^(\d{5})", expand=False)  # older years store ZIPs as "92103.0"
    df = df.assign(date=pd.to_datetime(df.date_response).dt.date, zip=zips).dropna(subset=["zip"])
    df["medical"] = df.call_category.isin(MEDICAL)
    out = df.groupby(["date", "zip"]).agg(calls=("medical", "size"), calls_medical=("medical", "sum")).reset_index()
    out["tz_source"] = "America/Los_Angeles"
    return out


def fetch_history(years=range(2016, 2027)):
    for y in years:
        upsert(daily_by_zip(year_file(y, refresh=(y == max(years)))), "ems_daily_zip", ["date", "zip"])


def fetch_live():
    y = pd.Timestamp.now(tz="America/Los_Angeles").year
    return upsert(daily_by_zip(year_file(y, refresh=True)), "ems_daily_zip", ["date", "zip"])
