"""1.0.1: the hole fill bounded by what was seen, the mesh checks, and the depth-map check and repair bookkeeping."""
import json

import numpy as np

from rpp.ibr import mesh as M
from rpp.sfm import dense as D


def _grid_mesh(fn, r_max=60.0, step=0.5, skip=None):
    xs = np.arange(-r_max, r_max + step, step)
    X, Y = np.meshgrid(xs, xs)
    Z = fn(X, Y)
    V = np.c_[X.ravel(), Y.ravel(), Z.ravel()]
    n = len(xs)
    F = []
    for i in range(n - 1):
        for j in range(n - 1):
            a, b, c, d = i * n + j, i * n + j + 1, (i + 1) * n + j + 1, (i + 1) * n + j
            cx, cy = X[i, j] + step / 2, Y[i, j] + step / 2
            if np.hypot(cx, cy) > r_max or (skip is not None and skip(cx, cy)):
                continue
            F += [(a, b, c), (a, c, d)]
    return V, np.asarray(F, np.int64)


PLANE = {"normal": [0.0, 0.0, 1.0], "offset": 0.0}


def test_harmonic_fill_does_not_rise_over_a_wide_hole():
    # flat ground at 0 with a 50 deg wedge missing beyond 6 m (Van Zyl behind the rover): the old cubic made a dome
    wedge = lambda x, y: np.hypot(x, y) > 6 and (np.degrees(np.arctan2(x, y)) % 360 > 320 or np.degrees(np.arctan2(x, y)) % 360 < 10)
    V, F = _grid_mesh(lambda x, y: 0.02 * np.sin(x) * np.cos(y), skip=wedge)
    P = np.array([0.0, 0.0, 1.9])
    V2, F2, rep = M.fill_terrain(V, F, P, (0, 0, 1), PLANE, 55.0)
    fill = V2[F2[len(F):]].reshape(-1, 3)
    r = np.hypot(fill[:, 0], fill[:, 1])
    assert rep["fill_harmonic"]["nodes"] > 0
    assert fill[(r > 6) & (r < 50), 2].max() < 0.1          # no hill: within the rim's few centimeters


def test_fill_stays_under_the_line_of_sight():
    # a hole between 10 and 30 m on one azimuth band, ground seen beyond it at 40-55 m on a low slope; a tall rim
    # cell beside the hole must not lift the fill above the rays from the pivot to the far ground
    def z(x, y):
        return np.where((np.hypot(x, y) > 9) & (np.hypot(x, y) < 10) & (np.abs(np.degrees(np.arctan2(x, y))) < 4), 3.0, 0.0)
    hole = lambda x, y: 10 < np.hypot(x, y) < 30 and abs(np.degrees(np.arctan2(x, y))) < 12
    V, F = _grid_mesh(z, skip=hole)
    P = np.array([0.0, 0.0, 1.9])
    V2, F2, rep = M.fill_terrain(V, F, P, (0, 0, 1), PLANE, 55.0)
    fill = V2[F2[len(F):]].reshape(-1, 3)
    r = np.hypot(fill[:, 0], fill[:, 1])
    az = np.degrees(np.arctan2(fill[:, 0], fill[:, 1]))
    sel = (r > 12) & (r < 28) & (np.abs(az) < 2)
    el = np.degrees(np.arctan2(fill[sel, 2] - 1.9, r[sel]))
    ground_el = np.degrees(np.arctan2(-1.9, 40.0))          # the nearest far ground seen past the hole
    assert el.max() <= ground_el + 0.5
    assert rep["fill_bounds"]["nodes_lowered"] >= 0


def test_mesh_checks_flag_a_sector_without_measured_surface():
    wedge = lambda x, y: np.hypot(x, y) > 6 and (np.degrees(np.arctan2(x, y)) % 360 > 320 or np.degrees(np.arctan2(x, y)) % 360 < 10)
    V, F = _grid_mesh(lambda x, y: 0 * x, skip=wedge)
    P = np.array([0.0, 0.0, 1.9])
    V2, F2, rep = M.fill_terrain(V, F, P, (0, 0, 1), PLANE, 55.0)
    c = M.mesh_checks(V2, F2, len(F), len(F2), P, (0, 0, 1), north=(0, 1, 0), radius_m=55.0)
    assert 340 in c["mostly_fill_sectors_deg"] and 180 not in c["mostly_fill_sectors_deg"]
    assert c["fill_above_skyline_sectors"] == 0
    assert any("mostly fill" in w for w in c["warnings"])


def _write_map(path, A):
    h, w = A.shape
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(f"{w}&{h}&1&".encode())
        f.write(np.asarray(A, np.float32).T.tobytes())       # column-major, as COLMAP writes it


def test_depth_check_finds_a_failed_frame_and_repairs_once(tmp_path):
    ws = tmp_path
    good = np.where(np.random.default_rng(0).random((40, 60)) < 0.6, 5.0, 0.0)
    bad = np.zeros((40, 60)); bad[:3] = 300.0                # 7.5 % of the frame (Van Zyl: 8 %)
    for i in range(4):
        _write_map(ws / "stereo" / "depth_maps" / f"f{i}.png.geometric.bin", good)
    _write_map(ws / "stereo" / "depth_maps" / "fbad.png.geometric.bin", bad)
    chk = D.check_depth_maps(ws)
    assert chk["failed"] == ["fbad.png"] and 0.5 < chk["median"] < 0.7
    assert json.loads((ws / "stereo" / D.DEPTH_CHECK_FILE).read_text())["failed"] == ["fbad.png"]
    assert D.frames_to_repair(ws) == ["fbad.png"]
    assert D.clear_depth_maps(ws, ["fbad.png"]) == 1
    (ws / "stereo" / D.DEPTH_REPAIR_FILE).write_text(json.dumps({"fbad.png": {"before": 0.075}}))
    _write_map(ws / "stereo" / "depth_maps" / "fbad.png.geometric.bin", bad)
    assert D.frames_to_repair(ws) == []                     # once only


def test_new_station_workspaces_search_a_bounded_depth_range():
    assert D.STATION_DEPTH_RANGE["depth_max"] <= 500 and D.STATION_DEPTH_RANGE["depth_min"] > 0
    import pycolmap
    po = pycolmap.PatchMatchOptions()
    D.set_options(po, D.STATION_DEPTH_RANGE)                 # the fields exist on pycolmap's options
    assert po.depth_max == D.STATION_DEPTH_RANGE["depth_max"]
