"""1.1: the 16-bit frame cache and a station's stored levels follow the radiometric settings."""
import json
from types import SimpleNamespace

import numpy as np

from rpp.ibr import linear16 as L


def _project(tmp_path, radiometry=None):
    (tmp_path / "processed").mkdir(exist_ok=True)
    (tmp_path / "processed" / "mppp_config_v1p0.json").write_text(json.dumps({"config": {"radiometry": radiometry or {}}}))
    (tmp_path / "colmap").mkdir(exist_ok=True)
    return SimpleNamespace(root=tmp_path / "colmap", settings={"processed_dir": str(tmp_path / "processed")})


def test_frames_cached_under_other_radiometry_are_made_again(tmp_path):
    name = "NLF_0461_0707874229_177RAD_N0260630NCAM02461_0A0195J02.png"
    pds = tmp_path / "pds"
    pds.mkdir()
    (pds / name.replace(".png", ".IMG")).write_bytes(b"x")
    calls = []

    def make(prod, cfg):
        calls.append(cfg["radiometry"]["apply_sun_distance"])
        return np.full((4, 6, 3), 1000, np.uint16), np.zeros((4, 6), bool), {"product": prod.name, "saturated_share": 0.0, "clipped_in_8bit_share": 0.0, "clipped_in_16bit_share": 0.0}
    proj = _project(tmp_path, {"apply_sun_distance": False})
    r = L.ensure_linear16(proj, [name], pds=pds, make=make)
    assert r["made"] == 1 and r["remade_stale"] == 0 and calls == [False]
    assert L.ensure_linear16(proj, [name], pds=pds, make=make)["made"] == 0            # the same settings: kept
    proj = _project(tmp_path)                                    # a block without the key: today's default (on)
    r2 = L.ensure_linear16(proj, [name], pds=pds, make=make)
    assert r2["made"] == 1 and r2["remade_stale"] == 1 and calls == [False, True] and r2["radiometry_key"] != r["radiometry_key"]
    rec = json.loads((proj.root / "images16" / "linear16.json").read_text())
    assert rec[name]["radiometry_key"] == r2["radiometry_key"]
    assert not list((proj.root / "images16").glob("*.tmp*"))
    rec[name].pop("radiometry_key")                              # a cache made before 1.1 has no key: stale
    (proj.root / "images16" / "linear16.json").write_text(json.dumps(rec))
    assert L.ensure_linear16(proj, [name], pds=pds, make=make)["remade_stale"] == 1


def test_stored_levels_of_other_radiometry_are_dropped(tmp_path):
    f = tmp_path / "tone_levels.json"
    f.write_text(json.dumps({"exposure16": 2.0, "levels_8bit_linear_units": [3.0, 90.0]}))
    assert L.reset_stale_levels(f, "abc") is True and json.loads(f.read_text()) == {"radiometry_key": "abc"}
    v, src = L.shared_value(f, "exposure16", lambda: 1.5)
    assert (v, src) == (1.5, "computed")
    assert L.reset_stale_levels(f, "abc") is False and json.loads(f.read_text())["exposure16"] == 1.5   # the same key: kept
    assert L.reset_stale_levels(None, "abc") is False and L.reset_stale_levels(f, None) is False
