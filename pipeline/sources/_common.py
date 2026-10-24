"""Shared helpers for source modules: raw saving, parquet upsert, probe reports."""
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from pipeline.security import redact
from pipeline.storage import atomic_output

load_dotenv()
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
BBOX = (-117.60, 32.53, -116.08, 33.51)  # west, south, east, north — San Diego County
UA = {"User-Agent": os.environ.get("NWS_USER_AGENT") or "OutlookSD"}


def now_utc():
    return datetime.now(timezone.utc)


def save_raw(source, content, ext):
    out = RAW / source / f"{now_utc():%Y%m%dT%H%M%S%fZ}.{ext}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(content if isinstance(content, bytes) else content.encode())
    return out


def get(source, url, params=None, ext="txt", timeout=120, save=True, **kw):
    """GET with User-Agent; raises on HTTP error; saves the raw body under data/raw/<source>/."""
    try:
        r = requests.get(url, params=params, headers=UA, timeout=timeout, **kw)
    except requests.RequestException as e:  # these messages include the URL, which can carry a key
        raise RuntimeError(redact(f"{source}: {type(e).__name__}: {e}")) from None
    if r.status_code != 200:
        raise RuntimeError(redact(f"{source}: HTTP {r.status_code} for {r.url}\n{r.text[:500]}"))
    if save:
        save_raw(source, r.content, ext)
    return r


def upsert(df, name, keys):
    """Append df to processed/<name>.parquet and de-duplicate on keys (newest wins)."""
    path = PROCESSED / f"{name}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        df = pd.concat([pd.read_parquet(path), df], ignore_index=True)
    df = df.drop_duplicates(keys, keep="last").sort_values(keys).reset_index(drop=True)
    with atomic_output(path) as temporary:
        df.to_parquet(temporary, index=False)
    return df


def write(df, name):
    path = PROCESSED / f"{name}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_output(path) as temporary:
        df.to_parquet(temporary, index=False)
    return df


def probe_report(name, df, time_col=None):
    """Rule 2: print columns, row count and date range; save a sample to data/raw/_probes/."""
    out = RAW / "_probes" / f"{name}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.head(200).to_csv(out, index=False)
    rng = ""
    if time_col and len(df):
        rng = f" | {df[time_col].min()} → {df[time_col].max()}"
    print(f"[{name}] rows={len(df)}{rng}\n  columns={list(df.columns)}\n  sample → {out.relative_to(ROOT)}")
