"""1.0.6 (Christian, 22 Nov 2026: "please upload drafts of the full 3d models with and without the rover ... make that
part of the processing"): a station's full 3D model to Sketchfab, as DRAFTS (never published from here: the owner
sets the camera limits in Sketchfab's editor and publishes).

* two models per station: ``<prefix>_station_scape.glb`` as it is (terrain, horizon, rover) and the same without the
  rover part (assembled here, in a temporary folder);
* the account's API token is read from the environment variable ``RPP_SKETCHFAB_TOKEN`` - it is never written to a
  file, a record or a log;
* ``<station folder>/sketchfab.json`` records each model's uid, so a station made again replaces its models' files
  (the settings made in the editor stay); a draft Sketchfab has deleted (30 days) is uploaded anew;
* after the upload the model is set shadeless (the textures are photographs) once Sketchfab has processed it; a
  failure of that step is a warning.

Sketchfab's Data API v3 takes the file itself (a multipart POST); it does not fetch from a URL, so the file goes from
this machine, not from Hugging Face.  ``http`` (a function) can be given for tests.
"""
from __future__ import annotations

import json
import logging
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .. import env as rpp_env
from ..config import PathLike

log = logging.getLogger("rpp.ibr")

API = "https://api.sketchfab.com/v3"
TOKEN_VARIABLE = "RPP_SKETCHFAB_TOKEN"
RECORD = "sketchfab.json"
NAME_MAX = 48                    # Sketchfab's limit for a model's name
SOURCE = "rover-photogrammetry"
TAGS = ("mars", "perseverance", "mars2020", "photogrammetry", "rpp")
PROCESS_WAIT_S = 600.0           # how long the shading step waits for Sketchfab to process a model
PROCESS_POLL_S = 10.0
VARIANTS = ("with_rover", "terrain")


def token() -> Optional[str]:
    t = (rpp_env.get(TOKEN_VARIABLE) or "").strip()
    return t or None


def _http(method: str, url: str, tok: str, fields: Optional[Sequence[Tuple[str, str]]] = None,
          file: Optional[Tuple[str, str, bytes]] = None, body: Optional[Dict[str, Any]] = None,
          timeout: float = 1800.0) -> Tuple[int, Dict[str, Any]]:
    """One request: (status, the JSON answer or {"text": ...}).  ``fields`` + ``file`` (field, file name, bytes): a
    multipart form; ``body``: JSON."""
    import urllib.error
    import urllib.request
    headers = {"Authorization": f"Token {tok}"}
    data = None
    if fields is not None or file is not None:
        b = uuid.uuid4().hex
        parts: List[bytes] = []
        for k, v in fields or ():
            parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
        if file is not None:
            parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{file[0]}"; filename="{file[1]}"\r\n'
                         f'Content-Type: application/octet-stream\r\n\r\n'.encode("utf-8") + file[2] + b"\r\n")
        parts.append(f"--{b}--\r\n".encode("utf-8"))
        data = b"".join(parts)
        headers["Content-Type"] = f"multipart/form-data; boundary={b}"
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    try:
        return code, (json.loads(raw.decode("utf-8")) if raw else {})
    except ValueError:
        return code, {"text": raw[:500].decode("utf-8", "replace")}


def check(http: Optional[Callable] = None) -> Dict[str, Any]:
    """Is there a token, and does Sketchfab take it?  {"ok", "message", "account"}."""
    tok = token()
    if not tok:
        return {"ok": False, "message": f"{TOKEN_VARIABLE} is not set (setx {TOKEN_VARIABLE} <the account's API token>, then a new window)"}
    try:
        code, ans = (http or _http)("GET", f"{API}/me", tok, timeout=60.0)
    except Exception as e:                                       # noqa: BLE001 - no network, a proxy
        return {"ok": False, "message": f"Sketchfab not reached ({type(e).__name__}: {e})"}
    if code != 200:
        return {"ok": False, "message": f"Sketchfab refused the token (HTTP {code}: {str(ans)[:200]})"}
    return {"ok": True, "account": ans.get("username"), "plan": ans.get("account"),
            "message": f"Sketchfab account {ans.get('username')} ({ans.get('account')})"}


def station_files(folder: PathLike) -> Optional[Dict[str, Path]]:
    """{"with_rover": the station's full 3D file, "terrain": the same without the rover (made in a temporary folder)}
    or None when the station has no full 3D model."""
    from . import station_mesh as SM
    d = Path(folder)
    glbs = sorted(d.glob(f"*{SM.SCAPE_SUFFIX}"))
    if not glbs:
        return None
    out = {"with_rover": glbs[0]}
    tmp = Path(tempfile.mkdtemp(prefix="rpp_sketchfab_"))
    try:
        stem = glbs[0].name[:-len(SM.SCAPE_SUFFIX)]
        bare = tmp / f"{stem}station_scape_terrain_only.glb"
        if SM.assemble_scape(d, rover_folder=tmp / "no_rover", out=bare) is not None and bare.is_file():
            out["terrain"] = bare
    except Exception as e:                                       # noqa: BLE001 - the one file then
        log.warning("sketchfab: the model without the rover was not made (%s: %s)", type(e).__name__, e)
    return out


def _name(title: str, variant: str) -> str:
    tail = "" if variant == "with_rover" else " (terrain)"
    return (title[: NAME_MAX - len(tail)].rstrip() + tail)[:NAME_MAX]


def upload_station(folder: PathLike, label: str, title: Optional[str] = None, description: str = "",
                   license_slug: Optional[str] = None, http: Optional[Callable] = None, shade: bool = True,
                   variants: Sequence[str] = VARIANTS) -> Dict[str, Any]:
    """The station's full 3D models to Sketchfab as drafts (see the module).  Returns {"ok", "message", "models":
    {variant: {"uid", "url", "action"}}}; never raises."""
    from .. import __version__
    http = http or _http
    tok = token()
    if not tok:
        return {"ok": False, "message": f"{TOKEN_VARIABLE} is not set", "models": {}}
    d = Path(folder)
    files = station_files(d)
    if not files:
        return {"ok": False, "message": f"{label}: no full 3D model in {d}", "models": {}}
    rec_file = d / RECORD
    try:
        rec = json.loads(rec_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    models: Dict[str, Any] = dict(rec.get("models") or {})
    done: Dict[str, Any] = {}
    ok = True
    for v in variants:
        f = files.get(v)
        if f is None:
            continue
        name = _name(title or label, v)
        try:
            data = f.read_bytes()
            uid = (models.get(v) or {}).get("uid")
            action = None
            if uid:                                              # made again: the same model, a new file
                code, ans = http("PUT", f"{API}/models/{uid}", tok, fields=[("name", name)], file=("modelFile", f.name, data))
                if code in (200, 201, 202, 204):
                    action = "replaced"
                elif code != 404:
                    raise RuntimeError(f"HTTP {code}: {str(ans)[:300]}")
            if action is None:                                   # new (or the draft is gone)
                fields = [("name", name), ("description", description or f"Made with the Rover Photogrammetry Pipeline (RPP {__version__})."),
                          ("isPublished", "false"), ("isInspectable", "true"), ("source", SOURCE)]
                fields += [("tags", t) for t in TAGS]
                if license_slug:
                    fields.append(("license", license_slug))
                code, ans = http("POST", f"{API}/models", tok, fields=fields, file=("modelFile", f.name, data))
                if code not in (200, 201, 202) or not ans.get("uid"):
                    raise RuntimeError(f"HTTP {code}: {str(ans)[:300]}")
                uid, action = ans["uid"], "uploaded as a draft"
            models[v] = {"uid": uid, "url": f"https://sketchfab.com/models/{uid}", "name": name, "file": f.name,
                         "bytes": len(data), "rpp": __version__, "when": time.strftime("%Y-%m-%dT%H:%M:%S")}
            done[v] = dict(models[v], action=action)
        except Exception as e:                                   # noqa: BLE001 - the station's products are not lost for it
            ok = False
            done[v] = {"failed": f"{type(e).__name__}: {e}"}
            log.warning("sketchfab: %s %s not uploaded (%s: %s)", label, v, type(e).__name__, e)
    try:
        rec_file.write_text(json.dumps({"models": models, "note": "drafts: published by the owner in Sketchfab"}, indent=1), encoding="utf-8")
    except OSError:
        pass
    if shade:
        for v, m in done.items():
            if m.get("uid"):
                m["shading"] = _shadeless(m["uid"], tok, http)
    for f in files.values():                                     # the temporary file
        if f.parent.name.startswith("rpp_sketchfab_"):
            import shutil
            shutil.rmtree(f.parent, ignore_errors=True)
    parts = [f"{v}: {m.get('action')} {m.get('url')}" if m.get("uid") else f"{v}: FAILED ({m.get('failed')})" for v, m in done.items()]
    return {"ok": ok and bool(done), "message": f"Sketchfab {label} - " + "; ".join(parts), "models": done}


def _shadeless(uid: str, tok: str, http: Callable) -> str:
    """Shadeless once the model is processed; what happened, in a word."""
    t0 = time.time()
    try:
        while True:
            code, ans = http("GET", f"{API}/models/{uid}", tok, timeout=60.0)
            state = ((ans.get("status") or {}).get("processing") or "").upper() if code == 200 else ""
            if state == "SUCCEEDED":
                break
            if state == "FAILED":
                return "Sketchfab could not process the file"
            if time.time() - t0 > PROCESS_WAIT_S:
                return "not set (still processing) - set Shadeless in the editor"
            time.sleep(PROCESS_POLL_S)
        code, ans = http("PATCH", f"{API}/models/{uid}/options", tok, body={"shading": "shadeless"}, timeout=60.0)
        return "shadeless" if code in (200, 204) else f"not set (HTTP {code}) - set Shadeless in the editor"
    except Exception as e:                                       # noqa: BLE001
        return f"not set ({type(e).__name__}) - set Shadeless in the editor"
