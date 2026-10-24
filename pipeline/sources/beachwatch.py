"""State Water Board Beach Watch (data.ca.gov CKAN, ODC-BY): bacteria results, stations, advisories — San Diego County."""
import pandas as pd

from ._common import get, write

SQL = "https://data.ca.gov/api/3/action/datastore_search_sql"
RESULTS = "7bd961cf-abe4-433b-8033-378161237ff3"
STATIONS = "98e628ff-d012-4982-ad32-b9f9ad8ab524"
ADVISORIES = "d5cd6a23-829c-426d-a63e-689a55a3db9c"
PAGE = 32000  # CKAN SQL row cap


def _sql(name, resource, cols, where):
    sel = ", ".join(f'"{c}"' for c in cols)
    frames, offset = [], 0
    while True:
        q = f'SELECT {sel} FROM "{resource}" WHERE {where} ORDER BY "_id" LIMIT {PAGE} OFFSET {offset}'
        js = get(f"beachwatch_{name}", SQL, {"sql": q}, ext="json", timeout=600).json()
        if not js.get("success"):
            raise RuntimeError(f"beachwatch {name}: {js.get('error')}")
        recs = js["result"]["records"]
        frames.append(pd.DataFrame(recs, columns=cols))
        if len(recs) < PAGE:
            return pd.concat(frames, ignore_index=True)
        offset += PAGE


def results():
    cols = ["SampleDate", "StartTime", "Parameter", "Qualifier", "Result", "Unit", "AnalysisMethod", "SampleType",
            "Station_id", "Station_Name", "AgencyStationIdentifier", "Station_UpperLat", "Station_UpperLon",
            "Beach_Name", "WaterBodyType"]
    df = _sql("results", RESULTS, cols, "\"CountyName\" = 'San Diego' AND \"Parameter\" ILIKE 'entero%'")
    df["date"] = pd.to_datetime(df.SampleDate).dt.date
    df["Result"] = pd.to_numeric(df.Result, errors="coerce")
    df["tz_source"] = "America/Los_Angeles (date only)"
    return df


def stations():
    cols = ["Station_id", "Station_Name", "Station_Description", "AgencyStationIdentifier", "Station_UpperLat",
            "Station_UpperLon", "Beach_Name", "Status", "WaterBodyType", "AB411Beach"]
    return _sql("stations", STATIONS, cols, "\"CountyName\" = 'San Diego'")


def advisories():
    cols = ["Advisory id", "Station_id", "Station_Name", "Beach_Name", "DateofAdvisory", "DateOpened",
            "AdvisoryType", "AdvisoryCause", "Source", "Description", "Station_UpperLat", "Station_UpperLon"]
    return _sql("advisories", ADVISORIES, cols, "\"CountyName\" = 'San Diego'")


def fetch_history():
    write(results(), "beach_results")
    write(stations(), "beach_stations")
    write(advisories(), "beach_advisories")


fetch_live = fetch_history  # the state dataset updates every few months; the hourly job checks it daily
