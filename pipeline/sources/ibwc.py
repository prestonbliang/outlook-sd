"""IBWC gauge 11-0133.00, Tijuana River at International Boundary (border flow)."""
import io

import pandas as pd

from ._common import RAW, get, upsert

LIVE_URL = "https://ibwcsftpstg.blob.core.windows.net/wad/TelemetryTXT/11013300.txt"
HYDROSHARE_URL = ("http://www.hydroshare.org/resource/d2f319994a0e4a07ac0b09dcdff4bb61/"
                  "data/contents/Q_5minute_IBWC_TJR_border_2000-2021.csv")
PORTAL_EXPORT = RAW / "ibwc" / "portal_export.csv"  # manual export from waterdata.ibwc.gov (user-supplied)
COLS = ["ts_utc", "stage_m", "discharge_m3s", "source", "tz_source"]


def parse_live(text):
    """Telemetry text: Date (MM/DD/YYYY), Time (PST), Stage (m), Discharge (m3/s); newest first, blanks allowed."""
    data = [ln for ln in text.splitlines() if ln[:2].isdigit() and "/" in ln[:10]]
    df = pd.read_fwf(io.StringIO("\n".join(data)), colspecs=[(0, 10), (10, 19), (19, 33), (33, 60)],
                     names=["date", "time", "stage_m", "discharge_m3s"], dtype=str)
    df["local"] = df.date.str.strip() + " " + df.time.str.strip()
    for c in ["stage_m", "discharge_m3s"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # PST is a fixed UTC-8 offset (the file does not switch to PDT)
    df["ts_utc"] = (pd.to_datetime(df.local, format="%m/%d/%Y %H:%M") + pd.Timedelta(hours=8)).dt.tz_localize("UTC")
    df["source"], df["tz_source"] = "ibwc_live", "PST(UTC-8)"
    return df[COLS]


def parse_aquarius_export(text, source):
    """AQUARIUS 'Data Set Export' CSV: comment line(s), then 'Timestamp (UTC-08:00),Value (...)'."""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("Timestamp"))
    header = lines[start]
    offset = header.split("(UTC")[1].split(")")[0] if "(UTC" in header else "+00:00"
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    hours = -int(offset[:3]) if offset not in ("", "+00:00") else 0
    df = df[df.iloc[:, 0].str.match(r"\d{4}-\d{2}-\d{2}", na=False)]  # drops the trailing disclaimer row
    df["ts_utc"] = (pd.to_datetime(df.iloc[:, 0]) + pd.Timedelta(hours=hours)).dt.tz_localize("UTC")
    df["discharge_m3s"] = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    df["stage_m"] = float("nan")
    df["source"], df["tz_source"] = source, f"UTC{offset}"
    return df[COLS]


def fetch_live():
    df = parse_live(get("ibwc", LIVE_URL).text)
    return upsert(df, "ibwc_flow", ["ts_utc"]), df


def fetch_history():
    frames = [parse_aquarius_export(get("ibwc", HYDROSHARE_URL, ext="csv").text, "hydroshare_d2f31999")]
    if PORTAL_EXPORT.exists():
        frames.append(parse_aquarius_export(PORTAL_EXPORT.read_text(), "ibwc_portal_export"))
    else:
        print(f"ibwc: no portal export at {PORTAL_EXPORT}; history ends 2021 plus the live file")
    df = pd.concat(frames, ignore_index=True)
    return upsert(df, "ibwc_flow", ["ts_utc"])
