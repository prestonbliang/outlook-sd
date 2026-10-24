"""Census geography: San Diego County boundary and ZCTA (ZIP) polygons clipped to it."""
import io

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import box

from ._common import BBOX, PROCESSED, RAW, UA, get

COUNTY_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
ZCTA_URL = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip"


def _read_zip(source, url, name):
    path = RAW / source / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(get(source, url, save=False, timeout=600).content)
    return gpd.read_file(f"zip://{path}")


def fetch_history():
    county = _read_zip("census", COUNTY_URL, "county.zip")
    county = county[(county.STATEFP == "06") & (county.COUNTYFP == "073")].to_crs(4326)[["GEOID", "NAME", "geometry"]]
    zcta = _read_zip("census", ZCTA_URL, "zcta.zip").to_crs(4326)
    zcta = zcta[zcta.intersects(county.union_all())]
    # keep ZIPs mostly inside the county (drops slivers from Orange / Riverside / Imperial)
    area = zcta.to_crs(3310).area
    inside = zcta.to_crs(3310).intersection(county.to_crs(3310).union_all()).area
    zcta = zcta[(inside / area) > 0.5].rename(columns={"ZCTA5CE20": "zip"})[["zip", "geometry"]]
    county.to_parquet(PROCESSED / "county.parquet")
    zcta.to_parquet(PROCESSED / "zcta_sd.parquet")
    return county, zcta


def county():
    return gpd.read_parquet(PROCESSED / "county.parquet")


def zcta():
    return gpd.read_parquet(PROCESSED / "zcta_sd.parquet")


ACS_SF = "https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/acsdt5y2023-{t}.dat"
# B01003 total population; B01001 sex by age (65+ = male E020–E025, female E044–E049);
# B19013 median household income; B25035 median year structure built
AGE65 = [f"B01001_E{i:03d}" for i in [*range(20, 26), *range(44, 50)]]


def _acs_table(table, zips):
    """Stream one ACS 5-year summary file (all U.S. geographies, no API key) and keep only the given ZCTAs."""
    want = {f"860Z200US{z}" for z in zips}
    with requests.get(ACS_SF.format(t=table), headers=UA, stream=True, timeout=600) as r:
        r.raise_for_status()
        lines = (ln.decode("utf-8") for ln in r.iter_lines())
        header = next(lines).split("|")
        rows = [ln.split("|") for ln in lines if ln.split("|", 1)[0] in want]
    df = pd.DataFrame(rows, columns=header)
    df["zip"] = df.GEO_ID.str[-5:]
    return df.set_index("zip").drop(columns="GEO_ID").apply(pd.to_numeric, errors="coerce")


def acs(zips):
    pop = _acs_table("b01003", zips).B01003_E001
    age = _acs_table("b01001", zips)
    inc = _acs_table("b19013", zips).B19013_E001
    built = _acs_table("b25035", zips).B25035_E001
    out = pd.DataFrame({"population": pop, "median_income": inc.where(inc >= 0),
                        "median_year_built": built.where(built >= 0)})  # negative = Census "not available" codes
    out["share_65plus"] = age[AGE65].sum(axis=1) / age.B01001_E001
    out = out.rename_axis("zip").reset_index()
    out.to_parquet(PROCESSED / "acs_zcta.parquet", index=False)
    return out


ROADS_URL = "https://www2.census.gov/geo/tiger/TIGER2023/PRISECROADS/tl_2023_06_prisecroads.zip"
FHSZ_URL = ("https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/"
            "FHSZ_in_SRA_for_FHSZ_in_LRA/FeatureServer/0/query")  # CAL FIRE (prefire.calfire), State Responsibility Area


def roads():
    """Census TIGER primary + secondary roads, clipped to the county (for 'distance to roads')."""
    g = _read_zip("census", ROADS_URL, "prisecroads.zip").to_crs(4326)
    g = g[g.intersects(county().union_all())][["FULLNAME", "MTFCC", "geometry"]]
    g.to_parquet(PROCESSED / "roads_sd.parquet")
    return g


def fhsz():
    """CAL FIRE Fire Hazard Severity Zones in State Responsibility Areas (Moderate / High / Very High)."""
    w, s, e, n = BBOX
    frames, offset = [], 0
    while True:
        r = get("calfire_fhsz", FHSZ_URL, {
            "where": "1=1", "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outFields": "FHSZ_Description", "outSR": 4326,
            "maxAllowableOffset": 0.0005, "resultOffset": offset, "resultRecordCount": 1000, "f": "geojson"},
            ext="geojson", timeout=600)
        g = gpd.read_file(r.text)
        frames.append(g)
        if len(g) < 1000:
            break
        offset += 1000
    g = pd.concat(frames, ignore_index=True).rename(columns={"FHSZ_Description": "FHSZ"})
    g.to_parquet(PROCESSED / "fhsz_sd.parquet")
    return g


PLACES_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_06_place_500k.zip"
GAZ_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_gaz_place_06.txt"
CPA_URL = "https://seshat.datasd.org/gis_community_planning_districts/cmty_plan_datasd.geojson"


def place_polygons():
    """Census places (cities + CDPs, ≥2 km² land) in the county, plus City of San Diego community planning areas."""
    gaz = pd.read_csv(io.StringIO(get("census_gaz", GAZ_URL, ext="txt").text), sep="\t", dtype={"GEOID": str})
    gaz.columns = [c.strip() for c in gaz.columns]
    cp = _read_zip("census", PLACES_URL, "places_06.zip").to_crs(4326).merge(gaz[["GEOID", "INTPTLAT", "INTPTLONG"]])
    near = county().to_crs(3310).buffer(2000).to_crs(4326).union_all()
    cp = cp[gpd.points_from_xy(cp.INTPTLONG, cp.INTPTLAT).within(near) & (cp.ALAND > 2e6) & (cp.NAME != "San Diego")]
    cp = gpd.GeoDataFrame({"name": cp.NAME, "kind": "census_place"}, geometry=cp.geometry.to_numpy(), crs=4326)
    cpa = gpd.read_file(get("sd_cpa", CPA_URL, ext="geojson").text).to_crs(4326)
    name_col = next(c for c in cpa.columns if c.lower() in ("cpname", "cp_name", "name"))
    cpa = gpd.GeoDataFrame({"name": cpa[name_col].str.title(), "kind": "sd_community"}, geometry=cpa.geometry, crs=4326)
    cpa = cpa[~cpa.name.str.contains("Reserve Area|Subarea|Ncfua")]  # administrative areas, not neighborhoods
    return pd.concat([cp, cpa], ignore_index=True)


def places():
    """Named places: id, name, kind, zip (ZCTA containing the representative point), lat/lon, coastal flag
    (place outline within 0.5 km of the ocean or bay shore → the Flood tile applies)."""
    poly = place_polygons()
    shore = gpd.GeoSeries([shoreline()], crs=4326).to_crs(3310).iloc[0]
    poly["coastal"] = poly.to_crs(3310).distance(shore).to_numpy() <= 500
    poly[poly.coastal].assign(geometry=lambda g: g.simplify(0.0003))[["name", "geometry"]].to_parquet(
        PROCESSED / "coastal_places.parquet")  # Flood map layer
    pts = poly.set_geometry(poly.representative_point())
    pts = gpd.sjoin_nearest(pts.to_crs(3310), zcta().to_crs(3310), max_distance=3000).to_crs(4326)
    pts["lat"], pts["lon"] = pts.geometry.y.round(5), pts.geometry.x.round(5)
    pts["id"] = pts.name.str.lower().str.replace(r"[^a-z0-9]+", "-", regex=True).str.strip("-")
    out = pts.drop_duplicates("id")[["id", "name", "kind", "zip", "lat", "lon", "coastal"]]
    out = out.sort_values("name").reset_index(drop=True)
    out.to_parquet(PROCESSED / "places.parquet", index=False)
    return out


AREAWATER_URL = "https://www2.census.gov/geo/tiger/TIGER2023/AREAWATER/tl_2023_06073_areawater.zip"


def shoreline():
    """Pacific shore (county outline minus land borders) + San Diego Bay and Mission Bay shores, EPSG:4326."""
    edge = county().to_crs(4326).boundary.union_all()
    shore = edge.intersection(box(-117.65, 32.545, -117.05, 33.385))
    water = _read_zip("census", AREAWATER_URL, "areawater_06073.zip").to_crs(4326)
    bays = water[water.FULLNAME.fillna("").isin(["San Diego Bay", "Mission Bay"])].boundary.union_all()
    return shore.union(bays)


def write_places_json():
    """api/places.json: named places with ZIP, coordinates and a coastal flag (for the Flood tile)."""
    import json
    from .openmeteo import grid_id
    p = places()
    z = zcta().set_index("zip")
    c = z.to_crs(3310).centroid.to_crs(4326)
    p["point_id"] = grid_id(c.y.reindex(p.zip).to_numpy(), c.x.reindex(p.zip).to_numpy())[0]  # Heat weather point
    (PROCESSED.parents[1] / "api" / "places.json").write_text(json.dumps(p.to_dict("records"), indent=1))
    return p
