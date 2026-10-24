"""CAL FIRE: historic fire perimeters (FRAP, ArcGIS) and the incident list API (2013+, includes active fires)."""
import geopandas as gpd
import pandas as pd

from ._common import BBOX, get, upsert, write

PERIMS = ("https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/"
          "California_Historic_Fire_Perimeters/FeatureServer/0/query")
INCIDENTS = "https://incidents.fire.ca.gov/umbraco/api/IncidentApi/List"


def perimeters(min_year=1990):
    w, s, e, n = BBOX
    frames, offset = [], 0
    while True:
        r = get("calfire_perims", PERIMS, {
            "where": f"YEAR_ >= {min_year}", "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "outSR": 4326,
            "maxAllowableOffset": 0.0005, "resultOffset": offset, "resultRecordCount": 1000, "f": "geojson"},
            ext="geojson", timeout=600)
        g = gpd.read_file(r.text)
        frames.append(g)
        if len(g) < 1000:
            break
        offset += 1000
    g = pd.concat(frames, ignore_index=True)
    c = g.to_crs(3310).centroid.to_crs(4326)
    g = g.assign(lat=c.y, lon=c.x)
    g = g[g.lon.between(w, e) & g.lat.between(s, n)]
    g["date"] = pd.to_datetime(g.ALARM_DATE, unit="ms", errors="coerce").dt.date
    return g


def incidents(years=range(2013, 2027)):
    frames = [pd.DataFrame(get("calfire_incidents", INCIDENTS, {"inactive": "true", "year": y}, ext="json").json())
              for y in years]
    df = pd.concat(frames, ignore_index=True)
    return df[df.County.fillna("").str.contains("San Diego")].drop_duplicates("UniqueId").reset_index(drop=True)


def update_incidents(year):
    """Refresh one year of the incident list (new fires appear daily) into processed/calfire_incidents."""
    return upsert(incidents([year]), "calfire_incidents", ["UniqueId"])


def fetch_live():
    df = pd.DataFrame(get("calfire_incidents", INCIDENTS, {"inactive": "false"}, ext="json").json())
    return df[df.County.fillna("").str.contains("San Diego")] if len(df) else df


def fetch_history():
    p = perimeters()
    p.to_parquet(PROCESSED_PERIMS, index=False)
    write(incidents(), "calfire_incidents")


from ._common import PROCESSED  # noqa: E402
PROCESSED_PERIMS = PROCESSED / "calfire_perimeters.parquet"
