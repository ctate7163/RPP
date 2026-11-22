"""1.0.5 (Christian, 22 Nov 2026: "Run van zyl from the large or huge block, but limit the depth maps just to the
sites in the van zyl regular block. Do this for the others too ... Test this to make sure it doesn't break the
process"): single-sites --terrain regular and the patterns of rpp dense --block-images."""
import json
import types
from pathlib import Path

import numpy as np
import pytest

from rpp.ibr import single_sites as SS


def _dense(run):
    return next(c["argv"] for c in run["commands"] if c["step"] == "dense")


def _after(argv, flag):
    i = argv.index(flag) + 1
    j = next((k for k in range(i, len(argv)) if argv[k].startswith("--")), len(argv))
    return argv[i:j]


def test_regular_terrain_of_a_huge_block_is_the_regular_blocks_sols(tmp_path):
    cfg = SS.load_config()
    runs = {r["label"]: r for r in SS.plan(cfg, tmp_path, labels=["Sol0052", "Sol0461", "Sol0816", "Sol1454"],
                                           block_cameras="NF", terrain="regular")}
    d = _dense(runs["Sol0052"])                                   # Van Zyl: the huge block, the regular block's sols 49-71
    assert Path(runs["Sol0052"]["work"]).name.endswith("van_zyl_overlook_huge")
    assert "--whole-block" in d and _after(d, "--block-cameras") == ["NF"] and _after(d, "--block-name") == ["van_zyl_overlook_FN"]
    pats = _after(d, "--block-images")
    assert pats[:23] == [f"???_{s:04d}_*" for s in range(49, 72)] and pats[23:] == ["*_N0032046*"]
    assert "the regular block van_zyl_overlook (sols 49-71)" in runs["Sol0052"]["terrain_part"]
    for c in runs["Sol0052"]["commands"]:                         # every later step reads that cloud
        if c["step"] == "mesh":
            assert Path(c["argv"][c["argv"].index("--points") + 1]).parts[-3:] == ("colmap", "dense_block_van_zyl_overlook_FN", "fused.ply")
            assert "--keep-under-rover" in c["argv"]
    assert len(" ".join(d)) < 2000                                # a command line Windows takes (its limit: 32767)
    d = _dense(runs["Sol1454"])                                   # Bell Island Large: sols 1451-1467 of 1431-1478
    assert _after(d, "--block-name") == ["bell_island_FN"] and len(_after(d, "--block-images")) == 17 + 1
    d = _dense(runs["Sol0461"])                                   # Rockytop is no large block: the whole block, as --terrain block
    assert "--whole-block" in d and "--block-images" not in d and _after(d, "--block-cameras") == ["NF"]
    assert runs["Sol0461"]["terrain_part"] is None
    assert d == _dense(SS.plan(cfg, tmp_path, labels=["Sol0461"], block_cameras="NF", terrain="block")[0])
    d = _dense(runs["Sol0816"])                                   # sol 816 is not of belva_crater (784-815) and the block
    assert "--whole-block" in d and "--block-images" not in d    # is not there to measure in: the whole block
    # --terrain block and the config's own terrain are as they were
    d = _dense(SS.plan(cfg, tmp_path, labels=["Sol0052"], block_cameras="NF", terrain="block")[0])
    assert "--block-images" not in d and _after(d, "--block-cameras") == ["NF"]
    assert "--block-images" not in _dense(SS.plan(cfg, tmp_path, labels=["Sol0052"])[0])


def test_regular_terrain_without_a_regular_block_is_the_stations_nearby(tmp_path, monkeypatch):
    cfg = SS.load_config()
    rows = []
    for (site, drive), xy in {(39, 1418): (0, 0), (39, 1170): (20, 0), (39, 926): (0, 29), (39, 300): (80, 0), (38, 10): (0, -200)}.items():
        for k in range(3):
            rows.append({"name": f"NLF_08{k:02d}_1_N{site:03d}{drive:04d}NCAM00001_x.png", "camera_group": "N", "site": site,
                         "drive": drive, "sol": 800 + k, "prior_C": [xy[0], xy[1], 1.0 + 0.01 * k]})
    rows.append({"name": "ZL0_0800_1_N0391170ZCAM00001_x.png", "camera_group": "Z", "site": 39, "drive": 1170, "sol": 800,
                 "prior_C": [20.0, 0.0, 1.0]})
    monkeypatch.setattr(SS, "_block_project", lambda work: types.SimpleNamespace(images=rows))
    run = SS.plan(cfg, tmp_path, labels=["Sol0816"], block_cameras="NF", terrain="regular")[0]
    d = _dense(run)
    assert _after(d, "--block-name") == ["near30_S039D1418_FN"]
    assert _after(d, "--block-images") == ["*_N0391418*", "*_N0390926*", "*_N0391170*"]      # its own, then those within 30 m
    assert "2 station(s) within 30 m" in run["terrain_part"]
    st = cfg["stations"]["Sol0816"]
    assert SS.regular_terrain(dict(st, site="rockytop", work=None), "Sol0816", tmp_path / "mars2020_sol_0460_rockytop") is None
    monkeypatch.setattr(SS, "_block_project", lambda work: None)             # no project to measure in: the whole block
    assert SS.regular_terrain(st, "Sol0816", run["work"], "NF") is None


def test_dense_block_images_takes_patterns(tmp_path, monkeypatch):
    """rpp dense --whole-block --block-images with patterns: the frames they match, in the named workspace; the
    station's own frames recorded beside it as before; a pattern set that matches nothing stops (exit 2), it does not
    fall back to the whole block."""
    pycolmap = pytest.importorskip("pycolmap")
    import rpp.pipeline as PL
    import rpp.sfm.gpu as G
    from rpp.cli import main as rpp_main
    from rpp.sfm.project import SfmProject
    from test_ibr import _station_scene
    proj0, rec, st, scene, P, colors = _station_scene(tmp_path)
    root = proj0.root
    (root / "gui_native" / "sparse").mkdir(parents=True)
    rec.write(str(root / "gui_native" / "sparse"))
    rows = json.loads((root / "project.json").read_text(encoding="utf-8"))["images"]
    for r in rows:
        r.update(station="Sol0091_S003D0010", sequence="NCAM00001", downsample_scale=1.0)
    SfmProject(root, rows, {}, {}, [0.0, 0.0, 0.0], {"world_frame": "site3_enu"}).save()
    names = sorted(r["name"] for r in rows)
    calls = []
    monkeypatch.delenv("GPU_PYTHON", raising=False)
    monkeypatch.setattr(pycolmap, "has_cuda", False, raising=False)
    monkeypatch.setattr(PL, "_default_gpu_python", lambda: "/envs/rpp_gpu/python.exe")
    monkeypatch.setattr(G, "run_step", lambda py, step, proj, **kw: calls.append((py, step, kw)) or {"steps": {}})
    assert names == ["NLF_1.png", "NLF_2.png", "NLF_3.png", "NLF_4.png"]
    pat, want = "NLF_[12].*", ["NLF_1.png", "NLF_2.png"]
    assert rpp_main(["dense", str(root.parent), "--station", "3_10", "--whole-block", "--block-name", "part",
                     "--block-images", pat, "--stereo", "--fusion"]) == 0
    kw = calls[0][2]
    assert kw["workspace"].endswith("dense_block_part") and sorted(kw["images"]) == want
    stub = json.loads((root / "dense_S003D0010_block" / "mppp_dense.json").read_text(encoding="utf-8"))
    assert stub["block_workspace"] == "dense_block_part" and len(stub["subset"]) == 4
    calls.clear()                                                 # a pattern and a name together
    other = next(n for n in names if n not in want)
    assert rpp_main(["dense", str(root.parent), "--station", "3_10", "--whole-block", "--block-name", "part2",
                     "--block-images", pat, other[:-4], "--stereo"]) == 0
    assert sorted(calls[0][2]["images"]) == sorted(want + [other])
    calls.clear()
    assert rpp_main(["dense", str(root.parent), "--station", "3_10", "--whole-block", "--block-name", "none",
                     "--block-images", "???_9999_*", "--stereo"]) == 2
    assert not calls
    calls.clear()                                                 # without patterns: the whole block, as before
    assert rpp_main(["dense", str(root.parent), "--station", "3_10", "--whole-block", "--stereo"]) == 0
    assert calls[0][2]["workspace"].endswith("dense_block_N") and len(calls[0][2]["images"]) == len(rows)


def test_single_sites_runs_through_with_the_regular_terrain(tmp_path, monkeypatch):
    """The run itself: every step of a station of a huge block runs with the regular block's cloud, a second run finds
    them done, and another terrain makes them again (their commands differ) - the records are kept per command."""
    work = tmp_path / "mars2020_sol_0015_van_zyl_overlook_huge"
    for ws in ("dense_block_van_zyl_overlook", "dense_block_N"):
        (work / "colmap" / ws).mkdir(parents=True)
        (work / "colmap" / ws / "fused.ply").write_bytes(b"x")
    cfg = {"stations": {"Sol0052": {"station": "3_2046", "work": str(work)}}, "variants": ["rover", "masked"], "terrain": "block"}
    ran = []

    def fake(argv, fh):
        ran.append(argv)
        if argv[0] in SS.STEP_OUTPUT:
            out = Path(argv[argv.index("--out") + 1])
            out.mkdir(parents=True, exist_ok=True)
            (out / SS.STEP_OUTPUT[argv[0]]).write_text("{}")
        return 0
    monkeypatch.setattr(SS, "_run", fake)
    out = tmp_path / "o"
    plan = lambda t: SS.plan(cfg, tmp_path, out, terrain=t)       # noqa: E731
    assert SS.run_all(plan("regular"), out) == 0
    steps = [a[0] for a in ran]
    assert steps[0] == "dense" and steps.count("mesh") == 2 and steps.count("ods") == 2 and "depthmaps" in steps
    assert _after(ran[0], "--block-name") == ["van_zyl_overlook"] and "???_0052_*" in ran[0]
    assert all("dense_block_van_zyl_overlook" in a[a.index("--points") + 1] for a in ran if a[0] == "mesh")
    assert SS.station_done(plan("regular")[0])
    ran.clear()
    assert SS.run_all(plan("regular"), out) == 0 and [a[0] for a in ran] == ["dense"]     # (rpp dense skips what it has)
    ran.clear()                                                   # the whole block's cloud: other commands, made again
    assert SS.run_all(plan("block"), out) == 0 and [a[0] for a in ran].count("mesh") == 2
    assert all(a[a.index("--points") + 1].endswith(str(Path("dense_block_N") / "fused.ply")) for a in ran if a[0] == "mesh")


def test_page_only_puts_the_viewer_page_up_and_touches_no_station(tmp_path, monkeypatch):
    """1.0.5: rpp single-sites --page-only - the page of this installation into the viewer checkout, committed and
    pushed with no station (the page that hides the stations without a full 3D model need not wait for one)."""
    from rpp.cli import main as rpp_main
    from rpp.ibr import web
    calls = []
    monkeypatch.setattr(web, "upload", lambda d, stations=(), **kw: calls.append((Path(d), list(stations))) or {"ok": True, "message": "pushed"})
    monkeypatch.setattr(SS, "plan", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no station is planned")))
    d = tmp_path / "rpv"
    assert rpp_main(["single-sites", "--page-only", "--publish", str(d), "--upload"]) == 0
    page = (d / "index.html").read_text(encoding="utf-8")
    assert "with3d" in page and (d / "vendor").is_dir() and calls == [(d, [])]
    calls.clear()
    assert rpp_main(["single-sites", "--page-only", "--publish", str(d), "--no-upload"]) == 0 and not calls
    monkeypatch.setattr(web, "upload", lambda d, stations=(), **kw: {"ok": False, "message": "no network"})
    assert rpp_main(["single-sites", "--page-only", "--publish", str(d)]) == 1


def test_check_done_says_whether_the_run_would_make_anything(tmp_path, monkeypatch):
    """1.0.5: single-sites --check-done - nothing run; exit 0 when every station of the run is made as these arguments
    would make it (the batch file runs Van Zyl again from its own frames only when the regular terrain did not make
    it, not when only its upload failed)."""
    from rpp.cli import main as rpp_main
    work = tmp_path / "mars2020_sol_0015_van_zyl_overlook_huge"
    (work / "colmap").mkdir(parents=True)
    (work / "colmap" / "project.json").write_text('{"images": []}')
    (work / "colmap" / "run_done.json").write_text("{}")
    cfgf = tmp_path / "cfg.json"
    cfgf.write_text(json.dumps({"stations": {"Sol0052": {"station": "3_2046", "work": str(work)}}, "variants": ["rover", "masked"],
                                "terrain": "block"}))
    monkeypatch.setattr(SS, "_run", lambda argv, fh: 1)          # nothing would be run: a call would fail the test
    args = ["single-sites", "Sol0052", "--config", str(cfgf), "--root", str(tmp_path), "--any-block", "--block-cameras", "NF",
            "--terrain", "regular", "--no-zcam"]
    assert rpp_main(args + ["--check-done"]) == 1
    ran = []

    def fake(argv, fh):
        ran.append(argv)
        if argv[0] in SS.STEP_OUTPUT:
            out = Path(argv[argv.index("--out") + 1])
            out.mkdir(parents=True, exist_ok=True)
            (out / SS.STEP_OUTPUT[argv[0]]).write_text("{}")
            if argv[0] == "ods" and "--station-mesh" in argv:
                from rpp.ibr import station_mesh as SM
                for kind in (("rover",) if "--rover" in argv else ("scape", "terrain")):
                    (out / f"Sol0052_{SM.PART[kind]}.json").write_text(json.dumps({"model_code": SM.model_code()}))
        if argv[0] == "dense":
            ws = work / "colmap" / "dense_block_van_zyl_overlook_FN"
            ws.mkdir(parents=True, exist_ok=True)
            (ws / "fused.ply").write_bytes(b"x")
        return 0
    monkeypatch.setattr(SS, "_run", fake)
    assert rpp_main(args + ["--no-upload"]) == 0 and ran
    monkeypatch.setattr(SS, "_run", lambda argv, fh: 1)
    assert rpp_main(args + ["--check-done"]) == 0                 # made, with the CLI's own defaults (the rover surface's eyes, the model)
    assert rpp_main(args[:-2] + ["block", "--no-zcam", "--check-done"]) == 1    # the whole block's cloud: not made
