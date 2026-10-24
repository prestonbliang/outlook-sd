"""FPA FOD 6th edition (USDA Forest Service RDS-2013-0009.6): US wildfire records 1992–2020, read from the zip."""
import zipfile

import geopandas as gpd

from ._common import BBOX, PROCESSED, RAW, get

URL = "https://www.fs.usda.gov/rds/archive/products/RDS-2013-0009.6/RDS-2013-0009.6_Data_Format2_GDB.zip"


def fetch_history():
    path = RAW / "fpa_fod" / "fpa_fod_gdb.zip"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(get("fpa_fod", URL, save=False, timeout=1800).content)
    gdb = next(n.split(".gdb/")[0] + ".gdb" for n in zipfile.ZipFile(path).namelist() if ".gdb/" in n)
    g = gpd.read_file(f"zip://{path}!{gdb}", layer="Fires", bbox=BBOX)
    g.drop(columns="geometry").to_parquet(PROCESSED / "fpa_fod_sd.parquet", index=False)
    return g
