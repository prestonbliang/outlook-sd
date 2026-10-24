"""Exercise atomic replacement through real parquet/GeoJSON engines, without source downloads."""
import json

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from pipeline.sources import _common
from pipeline.storage import atomic_output


def test_processed_parquet_failure_preserves_last_usable_source(tmp_path, monkeypatch):
    monkeypatch.setattr(_common, "PROCESSED", tmp_path)
    original = pd.DataFrame({"value": [1]})
    _common.write(original, "source")

    def interrupted(self, path, **kwargs):
        path.write_bytes(b"incomplete parquet")
        raise OSError("interrupted source write")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        _common.write(pd.DataFrame({"value": [2]}), "source")
    pd.testing.assert_frame_equal(pd.read_parquet(tmp_path / "source.parquet"), original)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source.parquet"]


def test_geojson_engine_supports_atomic_replacement(tmp_path):
    target = tmp_path / "map.geojson"
    target.write_text('{"type":"FeatureCollection","features":[]}')
    frame = gpd.GeoDataFrame({"name": ["Test fixture"]}, geometry=[Point(-117.1, 32.7)], crs=4326)
    with atomic_output(target) as temporary:
        frame.to_file(temporary, driver="GeoJSON")
    result = json.loads(target.read_text())
    assert result["features"][0]["properties"]["name"] == "Test fixture"
    assert len(list(tmp_path.iterdir())) == 1
