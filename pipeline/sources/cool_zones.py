"""County of San Diego Cool Zones (air-conditioned public sites), via the SANDAG hosted layer."""
import pandas as pd

from ._common import get, write

URL = "https://geo.sandag.org/server/rest/services/Hosted/Cool_Zones/FeatureServer/0/query"


def fetch_live():
    js = get("cool_zones", URL, {"where": "1=1", "outFields": "organization,address,city,zipcode,phone,petpolicy,"
                                 "operationalhours", "outSR": 4326, "f": "json", "resultRecordCount": 2000},
             ext="json").json()
    df = pd.DataFrame([{**f["attributes"], "lon": f["geometry"]["x"], "lat": f["geometry"]["y"]}
                       for f in js["features"] if f.get("geometry")])
    df = df.rename(columns={"organization": "name", "zipcode": "zip", "petpolicy": "pets", "operationalhours": "hours"})
    df["zip"] = df.zip.astype("Int64").astype(str)
    return write(df, "cool_zones")


fetch_history = fetch_live
