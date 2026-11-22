"""1.0.1: the 16-bit frame cache and a station's stored levels follow the radiometric settings."""
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
    rec[name].pop("radiometry_key")                              # a cache made before 1.0.1 has no key: stale
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


def test_frames_carry_their_provenance_scales_and_position(tmp_path):
    """1.0.1: a 16-bit frame's PNG holds an XMP packet (source product, scales, radiometric key) and, where the
    block's manifest has the frame, the Mars position as EXIF GPS."""
    import cv2
    from rpp.ibr.xmp import read_fields
    from rpp.writers import read_png_chunks
    name = "NLF_0461_0707874229_177RAD_N0260630NCAM02461_0A0195J02.png"
    pds = tmp_path / "pds"
    pds.mkdir()
    (pds / name.replace(".png", ".IMG")).write_bytes(b"x")
    proj = _project(tmp_path)
    rec = {"source_product": name.replace(".png", ".IMG"), "camera_group": "NLF", "mppp_version": "1.0.1", "sol": 461,
           "site": 26, "drive": 630, "L_s_deg": 242.0, "solar_elevation_deg": 30.0, "tau_estimated": 0.98,
           "geo": {"lat_deg": 18.4586, "lon_east_deg": 77.4059, "elev_geoid_m": -2523.2}, "outputs": {"PNG8": "images_png8/" + name}}
    (tmp_path / "processed" / "mppp_manifest_v1p0.json").write_text(json.dumps({"images": [rec]}))

    def make(prod, cfg):
        return np.full((4, 6, 3), 1000, np.uint16), np.zeros((4, 6), bool), {
            "product": prod.name, "white_balance": [1.0, 1.224, 1.569], "brightness": 1.176, "scale_zenith": 0.61,
            "scale_sun_distance": 1.214, "scale_rad_to_int16": 2e5, "to_radiance_divide_by": [1.0, 2.0, 3.0],
            "saturated_share": 0.0, "clipped_in_8bit_share": 0.0, "clipped_in_16bit_share": 0.0}
    r = L.ensure_linear16(proj, [name], pds=pds, make=make)
    f = proj.root / "images16" / name
    assert r["made"] == 1 and cv2.imread(str(f), cv2.IMREAD_UNCHANGED).shape == (4, 6, 3)      # still a readable picture
    x = read_fields(f)
    assert x["SourceProduct"].endswith(".IMG") and x["RadiometryKey"] == r["radiometry_key"]
    assert float(x["SunDistanceScale"]) == 1.214 and float(x["ZenithScale"]) == 0.61 and x["Sol"] == "461"
    assert float(x["LatitudePlanetocentricDeg"]) == 18.4586 and float(x["LongitudeEastDeg"]) == 77.4059
    assert read_png_chunks(f).get("eXIf")                                # the Mars position as EXIF GPS
    pos = L.station_position(L.block_manifest(proj), [name])
    assert pos["LatitudePlanetocentricDeg"] == 18.4586 and pos["ElevationAreoidM"] == -2523.2 and "IAU 2000" in pos["Datum"]


def test_station_frames_keep_their_scale_whatever_the_blocks_16_bit_scale(tmp_path):
    """1.0.1: a block processed today (16-bit 1.76e5, 51.2 per 8-bit count) and one processed before 1.0.1 (2e5, 64,
    no Sun distance) give station frames of the same level: 2.2e5 counts per unit of radiance, 64 per 8-bit count."""
    import json
    from types import SimpleNamespace
    import pytest
    import rpp
    from rpp.ibr import linear16 as L
    for name, snap in (("new", rpp.default_config()),
                       ("old", {"color": {"scale_rad_to_int16": 2e5, "scale_int8_to_int16": 64}, "radiometry": {"tau_reference": 0.3}})):
        blk = tmp_path / name
        (blk / "processed").mkdir(parents=True)
        (blk / "colmap").mkdir()
        (blk / "processed" / "mppp_config_v1p0.json").write_text(json.dumps({"config": snap}))
        c = L.block_config(SimpleNamespace(root=blk / "colmap", settings={}))["color"]
        assert c["scale_rad_to_int16"] == pytest.approx(2.2e5) and c["scale_int8_to_int16"] == 64, name


def test_publish_with_no_station_rebuilds_none(tmp_path):
    """1.0.1 (21 Nov 2026): an empty station list is "none".  Read as "every station", a run whose station was skipped
    listed every station of the output root with local paths and uploaded none."""
    import json
    from rpp.ibr import web
    out, w = tmp_path / "out", tmp_path / "web"
    (out / "Sol0009").mkdir(parents=True)
    (out / "Sol0009" / f"Sol0009{web.STACK}").write_bytes(b"jpg")
    w.mkdir()
    entry = {"id": "Sol0009", "title": "x", "variants": [{"key": "masked", "views": {"standard": "https://hf/Sol0009.jpg"}}]}
    (w / "panos.json").write_text(json.dumps({"panos": [entry]}))
    doc = web.publish(out, w, stations=[])
    got = next(p for p in doc["panos"] if p["id"] == "Sol0009")
    assert got["variants"][0]["views"]["standard"] == "https://hf/Sol0009.jpg"
