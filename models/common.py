"""Shared training/evaluation helpers: time splits, block-bootstrap CIs, artifact saving."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ART = Path(__file__).resolve().parent / "artifacts"
SPLITS = {"train": (None, "2023-12-31"), "val": ("2024-01-01", "2024-12-31"), "test": ("2025-01-01", None)}


def split(df, col, name):
    lo, hi = SPLITS[name]
    d = pd.to_datetime(df[col])
    d = d.dt.tz_convert(None) if d.dt.tz is not None else d
    m = pd.Series(True, index=df.index)
    if lo:
        m &= d >= lo
    if hi:
        m &= d <= pd.Timestamp(hi) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return df[m]


def block_bootstrap(df, block_col, stat, n=1000, seed=0):
    """95% CI of stat(df) resampling whole blocks (e.g. weeks) with replacement — keeps autocorrelation."""
    rng = np.random.default_rng(seed)
    groups = [g for _, g in df.groupby(block_col)]
    vals = []
    for _ in range(n):
        idx = rng.integers(0, len(groups), len(groups))
        vals.append(stat(pd.concat([groups[i] for i in idx])))
    lo, hi = np.nanpercentile(vals, [2.5, 97.5])
    return {"value": float(stat(df)), "ci95": [float(lo), float(hi)]}


def save(tile, files):
    """files: {name: object}; dict/list → JSON, LightGBM Booster → model text."""
    out = ART / tile
    out.mkdir(parents=True, exist_ok=True)
    for name, obj in files.items():
        if hasattr(obj, "save_model"):
            obj.save_model(str(out / name))
        else:
            (out / name).write_text(json.dumps(obj, indent=2, default=str))
    return out
