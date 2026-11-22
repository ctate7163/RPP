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


def test_model_stamp_follows_the_model(tmp_path):
    """1.0.1: the stamp of an aligned model changes with its poses and not with a rewrite of the same files."""
    import os
    from rpp.sfm.dense import MODEL_STAMP_FILE, files_stamp, model_stamp
    assert model_stamp(tmp_path) is None
    (tmp_path / "cameras.bin").write_bytes(b"c" * 100)
    (tmp_path / "images.bin").write_bytes(b"i" * 1000)
    a = model_stamp(tmp_path)
    assert a and (tmp_path / MODEL_STAMP_FILE).is_file() and model_stamp(tmp_path) == a
    (tmp_path / "images.bin").write_bytes(b"i" * 1000)           # written again with the same content
    os.utime(tmp_path / "images.bin", (2e9, 2e9))
    assert model_stamp(tmp_path) == a
    (tmp_path / "images.bin").write_bytes(b"j" * 1000)           # other poses
    assert model_stamp(tmp_path) != a
    assert files_stamp([tmp_path / "cameras.bin", tmp_path / "nothing"]).startswith("1:") and files_stamp([]) is None


def test_station_steps_follow_the_block(tmp_path):
    """1.0.1: a station step's key holds the block's model and radiometric settings."""
    import json
    from rpp.ibr.single_sites import block_stamp, step_key
    (tmp_path / "colmap" / "gui_native" / "sparse").mkdir(parents=True)
    (tmp_path / "colmap" / "gui_native" / "sparse" / "cameras.bin").write_bytes(b"c")
    (tmp_path / "processed").mkdir()
    (tmp_path / "processed" / "mppp_config_v1p0.json").write_text(json.dumps({"config": {}}))
    a = block_stamp(tmp_path)
    assert a.startswith("model:") and "radiometry:None" not in a and "model:None" not in a
    k = step_key(["mesh"], "", "code", block=a)
    (tmp_path / "colmap" / "gui_native" / "sparse" / "cameras.bin").write_bytes(b"d")
    assert step_key(["mesh"], "", "code", block=block_stamp(tmp_path)) != k            # aligned again
    (tmp_path / "colmap" / "gui_native" / "sparse" / "cameras.bin").write_bytes(b"c")
    assert step_key(["mesh"], "", "code", block=block_stamp(tmp_path)) == k
    (tmp_path / "processed" / "mppp_config_v1p0.json").write_text(json.dumps({"config": {"color": {"scale_rad_to_int16": 1e5}}}))
    assert step_key(["mesh"], "", "code", block=block_stamp(tmp_path)) != k            # other brightness


def test_a_block_under_a_run_is_left_alone(tmp_path):
    """1.0.1: a station is not made from a block whose run is going on (images, masks and model being rewritten)."""
    import datetime, json, os, socket
    from rpp.ibr.single_sites import block_busy
    from rpp.runner import STATUS_FILE
    assert block_busy(tmp_path) is None
    st = {"state": "running", "pid": os.getpid(), "host": socket.gethostname(), "heartbeat": datetime.datetime.now().isoformat()}
    (tmp_path / STATUS_FILE).write_text(json.dumps(st))
    assert block_busy(tmp_path) == os.getpid()
    (tmp_path / STATUS_FILE).write_text(json.dumps(dict(st, state="done")))
    assert block_busy(tmp_path) is None
