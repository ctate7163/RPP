"""1.0.6: a station's full 3D models to Sketchfab as drafts (rpp.ibr.sketchfab) - with a stand-in for the network."""
import json

import numpy as np

from rpp.ibr import sketchfab as SF, station_mesh as SM


def _station(tmp_path):
    d = tmp_path / "Sol0001"
    (d / "with_rover").mkdir(parents=True)
    import cv2
    tri = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], np.float32)
    uv = np.array([[0, 0], [1, 0], [0, 1]], np.float32)
    F = np.array([[0, 1, 2]], np.uint32)
    for folder, kind, extra in ((d, "scape", {"shell_V": tri + 5, "shell_F": F, "shell_uv": uv}), (d / "with_rover", "rover", {})):
        stem = folder / f"Sol0001_{SM.PART[kind]}"
        np.savez(str(stem) + ".npz", V=tri, F=F, uv=uv, **extra)
        cv2.imwrite(str(stem) + ".jpg", np.full((8, 8, 3), 128, np.uint8))
        (folder / (stem.name + ".json")).write_text("{}")
    assert SM.assemble_scape(d) is not None
    return d


def test_drafts_with_and_without_the_rover_and_a_station_made_again_replaces_them(tmp_path, monkeypatch):
    d = _station(tmp_path)
    calls = []

    def http(method, url, tok, fields=None, file=None, body=None, timeout=0):
        calls.append((method, url, dict(fields or []), file[1] if file else None, body))
        assert tok == "secret-token"
        if method == "GET" and url.endswith("/me"):
            return 200, {"username": "someone", "account": "pro"}
        if method == "POST":
            return 201, {"uid": f"uid{sum(1 for c in calls if c[0] == 'POST')}"}
        if method == "GET":
            return 200, {"status": {"processing": "SUCCEEDED"}}
        if method == "PUT":
            return (404, {}) if url.endswith("uid2") and http.gone else (204, {})
        return 204, {}
    http.gone = False
    monkeypatch.delenv(SF.TOKEN_VARIABLE, raising=False)
    assert not SF.check(http)["ok"] and not SF.upload_station(d, "Sol0001", http=http)["ok"] and not calls
    monkeypatch.setenv(SF.TOKEN_VARIABLE, "secret-token")
    assert SF.check(http)["ok"]
    r = SF.upload_station(d, "Sol0001", title="Perseverance Sol 1: A place with a very long name indeed, too long", http=http)
    assert r["ok"] and set(r["models"]) == {"with_rover", "terrain"}
    posts = [c for c in calls if c[0] == "POST"]
    assert len(posts) == 2 and all(c[2]["isPublished"] == "false" for c in posts)          # drafts, never published
    assert all(len(c[2]["name"]) <= SF.NAME_MAX for c in posts) and posts[1][2]["name"].endswith("(terrain)")
    assert posts[0][3] == "Sol0001_station_scape.glb" and posts[1][3] == "Sol0001_station_scape_terrain_only.glb"
    assert [c[4] for c in calls if c[0] == "PATCH"] == [{"shading": "shadeless"}] * 2
    rec = json.loads((d / SF.RECORD).read_text())
    assert rec["models"]["with_rover"]["uid"] == "uid1" and "secret-token" not in (d / SF.RECORD).read_text()
    # the two files: with the rover part, and without it
    from rpp.ibr import rover_surface as RS
    files = SF.station_files(d)
    names = {k: [m["name"] for m in RS.read_glb(f.read_bytes())[0]["meshes"]] for k, f in files.items()}
    assert names == {"with_rover": ["terrain", "horizon", "rover"], "terrain": ["terrain", "horizon"]}
    # made again: the same models get the new file; a draft Sketchfab deleted is uploaded anew
    calls.clear()
    http.gone = True
    r = SF.upload_station(d, "Sol0001", http=http, shade=False)
    assert r["ok"] and r["models"]["with_rover"]["action"] == "replaced" and r["models"]["terrain"]["action"] == "uploaded as a draft"
    assert [c[0] for c in calls] == ["PUT", "PUT", "POST"]
    # a failure is reported, not raised
    r = SF.upload_station(d, "Sol0001", http=lambda *a, **k: (500, {"detail": "no"}), shade=False)
    assert not r["ok"] and "FAILED" in r["message"]


def test_sketchfab_is_not_in_the_panoramas_code_key():
    from rpp.ibr import single_sites as SS
    assert "sketchfab.py" in SS.NOT_IN_CODE_KEY
