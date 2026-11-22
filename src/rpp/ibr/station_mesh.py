"""The station as a textured 3D surface: the terrain within 20 m (10 m until 0.99.39) and the rover (0.99.26).

Christian, 18 Nov 2026: "I do want a simplified medium poly mesh of the 10m radius area to be textured. The texture
should be 8kx8k and projected onto the terrain largely from the perspective of the viewer so that the near terrain
gets higher res than the outer area" ... "the texture projection center might be better a little above the pivot
point without the rover. Add this as a fourth mode in rpv as 3D terrain and rover. It should include the 3D rover.
The 3D rover surfaces should be textured if they are visible anywhere from 1m of the pivot and viewed by the ncams."
Answers: the center 0.5 m above the pivot; the terrain-only stereo panorama as the backdrop beyond 10 m; head motion
held within 1 m of the pivot.

**The terrain** (the rover-masked run of a station: ``rpp ods ... --station-mesh``):

* the mesh of the station folder (``mesh.ply``, without the rover model) within ``RADIUS_M`` of the mast axis,
  simplified to about ``TARGET_TRIANGLES`` triangles (quadric decimation, no smoothing);
* a ``TEXTURE_PX`` square texture.  A texel stands for a direction from the projection center C, ``CENTER_ABOVE_M``
  above the pivot: the texture's center is straight down, the distance from the center grows evenly with the angle
  from straight down (an azimuthal equidistant map; north up, east right), the disc's rim is the angle of the farthest
  vertex.  So every texel covers the same angle seen from C, and the near terrain gets the most texels per square
  meter.  A vertex's texture coordinates are its direction from C, so the disc has no seam;
* the triangles C does not see (behind a rock, an overhang) or sees almost edge on are given cells of their own in the
  texture's corners (0.99.39: those within ``CELL_RADIUS_M``; farther ones take the disc) (outside the disc: a shelf packing at one texel size, the largest that fits), each colored from
  the frames that see it;
* every texel is colored by the panorama's blend (:func:`rpp.ibr.ods.shade_rays`): a disc texel along its ray from C,
  a cell texel along the surface normal onto its point.  What no frame colored is filled from the texels around it.

**The rover** (the rover-shown run: the Perseverance model of ``mesh.ply``, ``scene.rover_triangles``):

* a triangle is textured when it can be seen from somewhere within ``VIEW_RADIUS_M`` of the pivot (from the pivot and
  from ``VIEWPOINTS`` points on spheres of 0.5 and 1 m about it, those inside the model left out) - the space the
  viewer may move in - and the Navcam frames (``ROVER_FAMILIES``) color it; it gets a place in a chart of the
  ``ROVER_TEXTURE_PX`` texture (1.0: connected triangles that face about the same way share one, :func:`layout_charts`;
  before, every triangle had a cell of its own), colored as the terrain's cells are.  In a Mastcam-Z run (0.99.27) the Mastcam-Z frames color it first and
  the Navcam frames where they do not (:func:`rover_families`); the terrain of such a run is the same: the Mastcam-Z
  frames are its regular sources, the Navcam and front Hazcam frames fill in as the Mastcam-Z frames' weight goes out;
* the other triangles are the rover gray of the panoramas, shaded a little by their slope.

The two runs write ``<prefix>_station_mesh_terrain.npz`` / ``.jpg`` / ``.json`` and ``<prefix>_rover_station_mesh_rover...``
beside their panoramas; :func:`assemble` puts them into one binary glTF, ``<prefix>_station_mesh.glb`` in the terrain
folder: two meshes in meters about the pivot (x east, y up, z south: the viewer's frame), each with its unlit texture.
The viewer shows it as the fourth mode, "3D terrain and rover" (:mod:`rpp.ibr.web`), over the terrain-only
panorama.
"""
from __future__ import annotations

import json
import logging
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

PathLike = Union[str, Path]
log = logging.getLogger("rpp.ibr")

RADIUS_M = 20.0                 # the terrain within this horizontal distance of the mast axis (0.99.39, Christian, 19 Nov
#                                 2026: "the 3d terrain should go out to 20 m instead of 10 m"; 10 m before)
CENTER_ABOVE_M = 0.0            # the terrain texture's projection center above the pivot.  1.0.1 (Christian, 21 Nov 2026:
#                                 "dark strips on the terrain ... from the ods pivot being rendered from a position
#                                 higher than the ncam views"; "use the same projection on the ods and full-3d
#                                 texture"): the pivot itself, the panorama's center (0.5 m above it until 1.0) - from
#                                 there the disc holds what the mast cameras saw, and no sliver of unseen ground
#                                 behind each rock, colored from other frames, outlines it
TARGET_TRIANGLES = 500_000      # the simplified terrain ("medium poly"; 300,000 within 10 m until 0.99.39)
TEXTURE_PX = 8192               # the terrain texture's side
ROVER_TEXTURE_PX = 8192         # the rover texture's side as it is made and kept (1.0.1, Christian, 21 Nov 2026: "A 8k rover
#                                 texture is useful, but we probably want to serve 4k in vr"; 4096 until 1.0)
ROVER_GLB_PX = 4096             # ... and its side in the viewer's .glb files (reduced from the kept one)
VIEW_RADIUS_M = 1.0             # the rover is textured where it can be seen from within this distance of the pivot
VIEWPOINTS = 32                 # directions of the viewpoints on each sphere (0.5 m and VIEW_RADIUS_M)
ROVER_FAMILIES = "N"            # the frames that color the rover ("viewed by the ncams")
GRAZING_COS = 0.12              # a terrain triangle C sees at more than about 83 deg from its normal gets a cell
CELL_RADIUS_M = 10.0            # 0.99.39: ... and one C does not see, only within this of the mast axis; beyond, every
#                                 triangle takes the disc (flat ground is edge on from about 20 m, and the cells share
#                                 one texel size: 10-20 m of hidden ground would make every cell about 3x coarser)
GUTTER_PX = 4                   # texels around every cell and the disc, colored as if the surface went on (2 until
#                                 0.99.51: JPEG's 8 x 8 blocks and the viewer's mipmaps reached past them)
BORDER_PX = 16                  # 0.99.51 (Christian, 20 Nov 2026: "they should be a neutral color with its surroundings so
#                                 that jpg compress blurring does not bleed over to the actual mesh"): the texels this
#                                 near a cell or the disc take the colors about them (pull-push), not white or black
WARP_MAX_M2 = 0.01              # 0.99.51 ("could you warp the UV a little so that slightly occluded spots are included in
#                                 the main texture ... Only larger and more continuous back faces should go to the
#                                 corners"): a connected patch of triangles C does not see (or sees edge on) smaller
#                                 than this keeps the disc - its inner vertices' texture coordinates are spread between
#                                 those of the seen triangles about it (a harmonic map); a larger one gets cells
MAX_CELL_PX = 384               # a cell's longest side; a larger triangle is given coarser texels
TERRAIN_OFFSET_M = 0.05         # a cell texel's ray starts this far off the simplified surface (it may lie below
ROVER_OFFSET_M = 0.005          # the measured one); the rover model is exact
INSIDE_HITS = 5                 # a viewpoint whose rays meet the rover model in this many of six directions is inside it
JPEG_QUALITY = 90
GRAY_STRIP = (4, 64)            # the rover gray's cell: width, height (the shade by slope down the strip)
# 1.0 (Christian, 20 Nov 2026: "the mesh_rover texture should also have larger texture islands if possible"): the rover's
# triangles share charts (:func:`triangle_charts`) in place of a cell each - fewer seams and less of the texture spent
# on gutters
CHART_MAX_DEG = 50.0            # a chart's triangles face within this angle of its first (largest) triangle (1.0.1,
#                                 Christian, 21 Nov 2026: "Larger patches (merge neighbors facing the same way)"; 35 deg
#                                 and 0.6 m until 1.0: on the rover model 21,800 charts, 13 % of its area in charts of
#                                 one triangle - with 50 deg and 1 m 14,200 and none; 70 deg gives only 13,000: the
#                                 model is made of small parts)
CHART_MAX_M = 1.0               # a chart's longest side, in its plane
MAX_CHART_PX = 1024             # a chart's longest side in texels; a larger chart is given coarser texels
WELD_M = 1e-4                   # vertices nearer than this are one (the model repeats them along its hard edges)
CHART_OVERLAP_TOL = 0.03        # a chart whose triangles cover more than its outline by this share folds over itself
SUFFIX = "station_mesh.glb"
PART = {"terrain": "station_mesh_terrain", "rover": "station_mesh_rover", "scape": "station_scape_terrain"}
# 0.99.32 (Christian, 18 Nov 2026: "expanding the mesh to the horizon with a low poly mesh ... continuous from below the
# rover to infinity ... One square uv mapping could go from the point below the prime pivot point, and extend outwards
# to the horizon which lies on a circle about 90% of the max size of circle that will fit in the square. Beyond that
# horizon circle, the uv ... goes to the sky"): the fifth mode's surface - see :func:`horizon_shell`
SCAPE = True                    # the masked run also makes the fifth mode's terrain (a second 8k texture)
SCAPE_SUFFIX = "station_scape.glb"
HORIZON_FRAC = 0.97             # the skyline's circle: this share of the texture's inscribed circle (0.99.41, Christian,
#                                 19 Nov 2026: "the full 3d texture can cut out some sky to make more room for center
#                                 detail" - and the sky is solid white now: 0.90 before)
SKYLINE_MARGIN_DEG = 1.5        # the full-density zone ends this far above the highest mesh seen from C ...
SKYLINE_MIN_DEG = 5.0           # ... and at least this far above the horizontal: the scene's far surface (beyond the
#                                 mesh) does not tell far hills from the sky, and hills seldom stand higher than this
#                                 (10 deg until 0.99.41: with HORIZON_FRAC the terrain gets about 13 % more texels a
#                                 degree)
SKY_WHITE = True                # 0.99.41 (Christian, 19 Nov 2026: "the sky still has too many blemishes. That can be
#                                 solid white"; "assuming the black area does not map to the mesh, make it white"): in
#                                 the fifth mode's texture the sky's texels (:func:`sky_texels`: the bright far texels
#                                 joined to the zenith - not the hills beyond the mesh) and the texels no triangle
#                                 uses are white
POLE_WHITE_EL_DEG = 60.0        # 0.99.52: the fifth mode's texture is sky white above this elevation (no hill rises so high)
SHELL_NEAR_TOL_M = 0.25         # 1.0.5: the scene this much nearer than the drawn terrain along a ray is not the terrain
SHELL_FROM_M = 17.0             # the shell starts this far from the mast axis (the near mesh fades out over FADE_M; 7 m
#                                 until 0.99.39)
FADE_M = (18.0, 20.0)           # the near terrain's opacity: 1 at the first, 0 at the second (horizontal m from the axis;
#                                 8-10 m until 0.99.39)
SHELL_AZ_STEP_DEG = 0.5
SHELL_STEP_DEG = 0.25           # the shell's rings below the skyline
SHELL_SKY_RINGS = 8             # ... and above it, to the zenith
DOME_M = 3000.0                 # the sky's distance (and the farthest a terrain vertex is put)


def _unit(v) -> np.ndarray:
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def page_frame(X: np.ndarray, pivot, east, up, north) -> np.ndarray:
    """Block coordinates -> the viewer's frame: meters about the pivot, x east, y up, z south."""
    d = np.asarray(X, float) - np.asarray(pivot, float)
    return np.stack([d @ _unit(east), d @ _unit(up), -(d @ _unit(north))], axis=1).astype(np.float32)


# ------------------------------------------------------------------------------------------- geometry
TOP_SHEET = True                # 1.0.5: the viewer's terrain is the mesh's top surface, one sheet (see top_sheet)
TOP_STEP_M = 0.025              # ... sampled on a grid of this step
TOP_PIT_WIDTH_M = 0.12          # a pit narrower than this ...
TOP_PIT_DEPTH_M = 0.04          # ... and deeper than this is a crack between two sheets: raised to its rim
TOP_NEAR_M = 2.0                # the simplified triangles are of one size within this of the mast axis ...
TOP_RANGE_POWER = 0.6           # ... and grow with the range to this power beyond (0: one size everywhere)
TOP_ROCKS_TO_M = 6.0            # the rocks by the rover: the places within this of the mast axis ...
TOP_ROCK_RELIEF_M = 0.08        # ... where the surface rises or falls this much within 0.25 m
TOP_ROCK_P95_MM = 3.0           # the simplified sheet is within this of the sampled surface at 95 % of them, or the
TOP_ROCK_MORE = 1.3             # simplification is done again with this many times the triangles (twice at most)


def _range_warp(X: np.ndarray, P: np.ndarray, back: bool = False) -> np.ndarray:
    """The points about ``P`` scaled by (range / TOP_NEAR_M) ** -TOP_RANGE_POWER beyond ``TOP_NEAR_M`` (range in 3D
    from P), or back.  Simplifying in the scaled space leaves triangles that grow with the range: more of them near
    the rover."""
    near_m, power = float(TOP_NEAR_M), float(TOP_RANGE_POWER)
    v = np.asarray(X, float) - P
    r = np.linalg.norm(v, axis=1)
    if back:
        r0 = np.where(r > near_m, near_m * (np.maximum(r, 1e-12) / near_m) ** (1.0 / (1.0 - power)), r)
        return P + v * (r0 / np.maximum(r, 1e-12))[:, None]
    return P + v * np.where(r > near_m, (np.maximum(r, 1e-12) / near_m) ** -power, 1.0)[:, None]


TOP_FLOATERS = True             # 1.0.5: the top surface is not taken where it floats (see under_floaters)
TOP_FLOATER_AIR_M = 0.4         # ... with this much air under it
TOP_FLOATER_THICK_M = 0.6       # ... and is no thicker than this itself (a hill's overhang is thicker)
TOP_FLOATER_LAYERS = 4          # the surfaces looked at under the top one
TOP_FLOATER_MIN_M2 = 0.05       # a floating piece smaller than this stays (a rock's rim)
TOP_FLOATER_JOIN_M = 0.15       # the ground beside a piece is joined to it when their heights differ by less ...
TOP_FLOATER_BROAD_M = 1.5       # ... and holds it when it is no narrower than this (a post or a pillar holds nothing)
TOP_FLOATER_PROUD_M = 0.3       # (narrower: it stands this much above the ground opened at that width)
TOP_FLOATER_HELD = 0.1          # a piece held along less than this share of its rim ...
TOP_FLOATER_OVER = 2.0          # ... and this many times larger than the narrow thing it stands on is a floater ...
TOP_FLOATER_SEEN = 0.5          # ... when the mast sees the surface beneath it under this share of it or more
TOP_POST_NEAR_M = 0.5           # what held a floater - within this of where it was - is lowered when it is ...
TOP_POSTS = ((0.35, 0.2), (0.7, 0.7), (1.4, 2.1))    # ... narrower than (width m) and taller than (height m): a post


def under_floaters(rc, base: np.ndarray, h: np.ndarray, hit: np.ndarray, inside: np.ndarray, pivot: np.ndarray,
                   up: np.ndarray, step_m: float) -> Tuple[np.ndarray, Dict[str, Any]]:
    """1.0.5 (Christian, 22 Nov 2026, Wildcat Ridge Sol0502: "a bad floater attached to the ground in front of the
    rover" - a sheet 5.4 m long and 1.3 m wide hanging 2 m over the slope at the mast's height, held to the ground
    by a thin post, so that no rule for loose pieces took it; Rockytop has one 17 m out on a pillar).  ``h`` (n,):
    the top surface's height above the pivot along ``up`` over the places ``base`` (n, 3; at the pivot's level),
    which are the True cells of the grid ``inside``; returned lowered to the surface beneath where the top one
    FLOATS:

    * a place floats when under it, within ``TOP_FLOATER_THICK_M``, the mesh ends and ``TOP_FLOATER_AIR_M`` or more
      of air follows before the next surface (up to ``TOP_FLOATER_LAYERS`` surfaces are looked at);
    * the floating places that touch are one piece, and a piece is a floater when the ground does not hold it:
      along its rim, the cells beside it that are at its height (``TOP_FLOATER_JOIN_M``) AND are broad ground
      (not narrower than ``TOP_FLOATER_BROAD_M``) are less than ``TOP_FLOATER_HELD`` of the rim, AND the piece
      is more than ``TOP_FLOATER_OVER`` times as large as the narrow thing it is joined to.  A ledge of an outcrop
      floats too, but the hill holds it along its back, and a boulder's overhang is smaller than the boulder: both
      stay whole (the first rule lowered every floating place the mast saw under - Skinner Ridge's ledges came out
      as teeth; the second took the overhang off a boulder 3.5 m from the rover there);
    * and the mast SEES the surface beneath it under ``TOP_FLOATER_SEEN`` of the piece or more: the ground under a
      floater was measured through the place where the floater would be solid - so it is not.  What lies inside or
      beneath a solid thing (another sheet of the mesh, the fill) is hidden by the thing and does not pass;
    * what held a floater is lowered with it: within ``TOP_POST_NEAR_M`` of where it was, a thing narrower and
      taller than a pair of ``TOP_POSTS`` goes down to the ground around it.

    Returns (h, record)."""
    from scipy import ndimage as ndi
    n = len(h)
    cur = np.asarray(h, float).copy()                           # the surface the walk is at
    roof = cur.copy()                                           # the top one
    out = cur.copy()
    alive = np.asarray(hit, bool).copy()
    low = np.zeros(n, bool)
    seen = np.zeros(n, bool)
    for _ in range(int(TOP_FLOATER_LAYERS)):
        i = np.flatnonzero(alive)
        if not len(i):
            break
        o = base[i] + (cur[i] - 0.02)[:, None] * up
        t, _ = _cast(rc, o, np.broadcast_to(-up, o.shape))
        nxt = cur[i] - 0.02 - t
        got = np.isfinite(t)
        air = got & (t + 0.02 >= TOP_FLOATER_AIR_M) & (roof[i] - cur[i] <= TOP_FLOATER_THICK_M)
        j = i[air]
        out[j] = nxt[air]
        low[j] = True
        roof[j] = out[j]                                        # the walk goes on from there: a floater over a floater
        if len(j):                                              # does the mast see the surface beneath?
            seen[j] = seen_from(rc, base[j] + (out[j] + 0.03)[:, None] * up, pivot)
        cur[i] = np.where(got, nxt, cur[i])
        alive[i] = got
    rec: Dict[str, Any] = {"floating_places": int(low.sum()), "air_m": TOP_FLOATER_AIR_M, "thick_m": TOP_FLOATER_THICK_M,
                           "held": TOP_FLOATER_HELD, "pieces": 0, "pieces_kept": 0, "places": 0, "m2": 0.0, "posts_lowered": 0}
    if not low.any():
        return np.asarray(h, float).copy(), rec
    g = float(step_m)
    H = np.full(inside.shape, -1e4)
    H[inside] = np.asarray(h, float)
    Hl = H.copy()
    Hl[inside] = out
    M = np.zeros(inside.shape, bool)
    M[inside] = low
    Sn = np.zeros(inside.shape, bool)
    Sn[inside] = seen
    have = H > -5e3

    def opening(Z, k):                                          # an opening (gray level) that leaves the grid's edge alone: no
        er = ndi.grey_erosion(np.where(have, Z, 1e4), size=(k, k))     # cell outside the disc pulls the ground down
        return ndi.grey_dilation(np.where(have, er, -1e4), size=(k, k))
    kb = max(3, int(round(TOP_FLOATER_BROAD_M / g)) | 1)
    Hop = opening(H, kb)                                        # the ground without what is narrower than "broad"
    lab, k = ndi.label(M, structure=np.ones((3, 3), bool))
    sizes = np.bincount(lab.ravel(), minlength=k + 1)
    least = max(2, int(np.ceil(TOP_FLOATER_MIN_M2 / (g * g))))
    gone = np.zeros(inside.shape, bool)
    took = []
    pad = kb // 2 + 2
    proud_all = have & (H - Hop > TOP_FLOATER_PROUD_M)          # what stands on the ground and is narrower than "broad"
    for c, sl in enumerate(ndi.find_objects(lab), start=1):
        if sl is None or sizes[c] < least:
            continue
        sl = tuple(slice(max(0, a.start - pad), min(dim, a.stop + pad)) for a, dim in zip(sl, inside.shape))
        comp = lab[sl] == c
        stand = 0.0
        rim = ndi.binary_dilation(comp, structure=np.ones((3, 3), bool)) & ~comp & have[sl]
        if not rim.any():
            held = 0.0
        else:
            beside = ndi.grey_dilation(np.where(comp, H[sl], -1e4), size=(3, 3))      # the piece's height next to a rim cell
            joined = rim & (np.abs(H[sl] - beside) <= TOP_FLOATER_JOIN_M)
            broad = joined & (H[sl] - Hop[sl] <= TOP_FLOATER_PROUD_M)
            held = float(broad.sum()) / float(rim.sum())
            if held < TOP_FLOATER_HELD and (joined & ~broad).any():      # the narrow thing it is joined to: how large?
                body, _ = ndi.label(proud_all[sl] & ~comp, structure=np.ones((3, 3), bool))
                ids = np.unique(body[joined & ~broad])
                stand = float(np.isin(body, ids[ids > 0]).sum())
        under = float(Sn[sl][comp].mean())
        if held >= TOP_FLOATER_HELD or float(comp.sum()) <= TOP_FLOATER_OVER * stand or under < TOP_FLOATER_SEEN:
            rec["pieces_kept"] += 1
            continue
        gone[sl] |= comp
        ii, jj = np.nonzero(comp)
        took.append({"m2": round(float(comp.sum()) * g * g, 2), "held": round(held, 2), "stands_on_m2": round(stand * g * g, 2),
                     "seen_under": round(under, 2),
                     "lowered_by_m_max": round(float((H[sl] - Hl[sl])[comp].max()), 2),
                     "cell": [int(ii.mean()) + sl[0].start, int(jj.mean()) + sl[1].start]})
    if not gone.any():
        return np.asarray(h, float).copy(), rec
    H2 = np.where(gone, Hl, H)
    near = ndi.binary_dilation(gone, iterations=max(1, int(round(TOP_POST_NEAR_M / g)))) & have
    posts = np.zeros(inside.shape, bool)
    for width_m, tall_m in TOP_POSTS:                           # the narrowest first: a thin post, then a pillar
        ks = max(3, int(round(width_m / g)) | 1)
        Ho = opening(H2, ks)
        post = near & (Ho > -5e3) & (H2 - Ho > tall_m)
        H2 = np.where(post, Ho, H2)
        posts |= post
    took.sort(key=lambda r: -r["m2"])
    rec.update(pieces=len(took), places=int(gone.sum()), m2=round(float(gone.sum()) * g * g, 2),
               posts_lowered=int(posts.sum()), largest=took[:5])
    return H2[inside], rec


SKY_CEILING = True              # 1.0.6: the terrain is held under the mast's skyline (see pano_skyline, sky_ceiling)
SKY_CEILING_MARGIN_DEG = 0.1    # ... this much above it at the crest (where the terrain meets the skyline) ...
SKY_CEILING_BEHIND_DEG = 0.3    # ... and this much under it behind the crest (seen from the mast it is then hidden)
SKY_CEILING_BEHIND_M = 0.25     # behind: farther than the crest of its azimuth by this much
SKY_CEILING_BIN_DEG = 0.25      # the crest's range is found per this much azimuth
SKY_CEILING_SMOOTH_DEG = 0.3    # the skyline smoothed over this much azimuth (Gaussian sigma) before it is used
SKY_CEILING_MEDIAN_DEG = 0.5    # ... after a median over this much (a speck of sky or terrain in one column)
SKY_CEILING_FROM_M = 3.0        # nearer than this nothing is carved (the rover's own parts, the deck, the mast's shadow)
SKY_CEILING_MIN_EL_DEG = 0.0    # ... nor under a skyline lower than this (below the horizon a bright far slope looks like sky)


def pano_skyline(pano: np.ndarray) -> Optional[np.ndarray]:
    """1.0.6: the skyline of an equirectangular eye (row 0 the zenith; linear or 8-bit): per column, the elevation (deg)
    of the highest pixel that is not sky.  The sky is what is joined to the zenith through pixels as bright as the
    sky - brighter than midway (log) between the sky high up and the ground below the horizon - and not much redder
    than the sky's own color in that row (the terrain is redder).  None when the eye has too little sky or ground."""
    import cv2
    from scipy import ndimage as ndi
    P = np.ascontiguousarray(np.asarray(pano, np.float32)[..., :3])
    H0, W0 = P.shape[:2]
    W = min(W0, 8192)
    H = max(2, int(round(H0 * W / W0)))
    small = cv2.resize(P, (W, H), interpolation=cv2.INTER_AREA) if W != W0 else P
    el = 90.0 - (np.arange(H) + 0.5) / H * 180.0
    lum = np.log1p(small.mean(axis=2))
    rb = np.log1p(small[..., 0]) - np.log1p(small[..., 2])
    hi, lo = el >= 45.0, (el < -5.0) & (el > -40.0)
    if not hi.any() or not lo.any():
        return None
    sky_l, gnd_l = float(np.median(lum[hi])), float(np.median(lum[lo]))
    if not sky_l > gnd_l + 0.05:
        return None
    cut = 0.5 * (sky_l + gnd_l)
    rb_sky = np.median(np.where(lum > cut, rb, np.nan)[el > 10.0], axis=1)        # the sky's red / blue by row
    rb_sky = np.where(np.isfinite(rb_sky), rb_sky, float(np.nanmedian(rb_sky)) if np.isfinite(rb_sky).any() else 0.0)
    rb_gnd = float(np.median(rb[lo]))
    rb_cut = np.full(H, np.inf)
    rows10 = np.flatnonzero(el > 10.0)
    if rb_gnd > float(np.median(rb_sky)) + 0.03:                 # the sky is told from the terrain by color too
        rb_cut[rows10] = rb_sky + 0.5 * (rb_gnd - rb_sky)
        rb_cut[el <= 10.0] = float(rb_sky[-1]) + 0.5 * (rb_gnd - float(rb_sky[-1]))
    cand = (lum > cut) & (rb < rb_cut[:, None]) & (el > -10.0)[:, None]
    lab_, n = ndi.label(cand)
    ids = np.unique(lab_[0][lab_[0] > 0])
    if not len(ids):
        return None
    sky = np.isin(lab_, ids)
    first = np.where(sky.all(axis=0), H - 1, np.argmax(~sky, axis=0))
    sk = el[first]
    k = max(3, int(round(SKY_CEILING_MEDIAN_DEG / 360.0 * W)) | 1)
    sk = ndi.median_filter(sk, size=k, mode="wrap")
    sk = ndi.gaussian_filter1d(sk, max(SKY_CEILING_SMOOTH_DEG / 360.0 * W, 0.5), mode="wrap")
    return sk.astype(np.float64)


class SkyCeiling:
    """1.0.6 (Christian, 22 Nov 2026: "the white fill behind Skinner's crest" - the mesh's top surfaces behind the crest
    stand up to a meter above the line where the frames see sky; seen from the mast they take the sky's white): free-
    space carving from the mast.  Where the panorama shows sky in a direction, nothing solid lies along that ray.

    ``skyline_deg`` per panorama column (:func:`pano_skyline`), ``azimuth0_deg`` the azimuth of column 0's left edge.
    :meth:`limit` gives, for points (n, 3) with heights ``h`` above the pivot, the height each may have:

    * at the crest of its azimuth (the nearest place where the terrain reaches the skyline's ray) and before it,
      the ray plus ``SKY_CEILING_MARGIN_DEG``: the crest that makes the skyline stays;
    * behind the crest (farther by ``SKY_CEILING_BEHIND_M``), ``SKY_CEILING_BEHIND_DEG`` under the ray: what the mast
      did not see stays hidden from it - the ridge's top beyond takes the crest's colors, not the sky's;
    * nothing nearer than ``SKY_CEILING_FROM_M``, nor under a skyline lower than ``SKY_CEILING_MIN_EL_DEG``."""

    def __init__(self, skyline_deg, azimuth0_deg: float, pivot, up, north, east):
        self.sk = np.asarray(skyline_deg, float)
        self.az0 = float(azimuth0_deg)
        self.P, self.u, self.n, self.e = (np.asarray(x, float) for x in (pivot, up, north, east))

    def where(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(horizontal distance r, azimuth from column 0 in deg, the skyline's elevation there in deg) of points."""
        v = np.asarray(X, float) - self.P
        x, y = v @ self.e, v @ self.n
        r = np.hypot(x, y)
        az = (np.degrees(np.arctan2(x, y)) - self.az0) % 360.0
        W = len(self.sk)
        c = az / 360.0 * W - 0.5
        i0 = np.floor(c).astype(np.int64)
        f = c - i0
        return r, az, self.sk[i0 % W] * (1.0 - f) + self.sk[(i0 + 1) % W] * f

    def limit(self, X: np.ndarray, h: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        r, az, el = self.where(X)
        h = np.asarray(h, float)
        use = (r >= SKY_CEILING_FROM_M) & (el >= SKY_CEILING_MIN_EL_DEG)
        e_pt = np.degrees(np.arctan2(h, np.maximum(r, 1e-6))) - el          # the point's elevation over the skyline
        nb = int(round(360.0 / SKY_CEILING_BIN_DEG))
        b = np.minimum((az / 360.0 * nb).astype(np.int64), nb - 1)
        crest = np.full(nb, np.inf)
        touch = use & (e_pt > -0.05)
        np.minimum.at(crest, b[touch], r[touch])
        crest = np.minimum.reduce([np.roll(crest, k) for k in (-2, -1, 0, 1, 2)])    # (a neighbor bin's crest counts)
        behind = r > crest[b] + SKY_CEILING_BEHIND_M
        lim = r * np.tan(np.radians(np.clip(el + np.where(behind, -SKY_CEILING_BEHIND_DEG, SKY_CEILING_MARGIN_DEG), -80.0, 80.0)))
        lim = np.where(use, lim, np.inf)
        over = h > lim
        return lim, {"cells": int(over.sum()), "behind_the_crest": int((over & behind).sum())}


def top_sheet(V: np.ndarray, F: np.ndarray, pivot, up, radius_m: float, target: int, fill: Optional[np.ndarray] = None,
              step_m: Optional[float] = None, ceiling=None) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """1.0.5 (Christian, 21 and 22 Nov 2026, Van Zyl: "the same rocks in van zyl have holes"; "Van zyl looks a lot
    better. There are still some holes though"): the viewer's terrain as ONE sheet - the top surface of the mesh
    (V, F), sampled straight down on a grid of ``step_m`` and simplified to ``target`` triangles.

    The station's mesh is several surfaces that are not sewn: the height field near the rover, the Poisson patches on
    its steep faces, the zones beyond, the fill and its underlay.  Simplified as they were (2.5 million triangles to
    500,000) their rims, cracks and overlaps became the arcs, flaps and see-through holes at Van Zyl's rocks, and the
    triangles came out one size (10 cm) from the wheels to 20 m.  A sheet with one height per place has no rims inside
    it and no second sheet to show through; what it gives up is the underside of an overhang.

    * a grid cell takes the highest surface under it; a narrow pit (a crack fell through to the sheet beneath) is
      raised to its rim (``TOP_PIT_WIDTH_M``, ``TOP_PIT_DEPTH_M``);
    * each cell is cut along the diagonal of the smaller height step, so a rock's edge stays straight;
    * the triangles are simplified in a space scaled by the range (:func:`_range_warp`): small near the rover, larger
      far off, where the texture is coarser too.

    ``fill``: True for the triangles of the fill (reported only).  Returns (V, F, record)."""
    import open3d as o3d
    from scipy import ndimage as ndi
    P, u = np.asarray(pivot, float), _unit(up)
    e1 = _unit(np.cross(u, [1.0, 0.0, 0.0]) if abs(u[0]) < 0.9 else np.cross(u, [0.0, 1.0, 0.0]))
    e2 = np.cross(u, e1)
    R, g = float(radius_m), float(TOP_STEP_M if step_m is None else step_m)
    n = int(2 * R / g) + 1
    ax = -R + g * np.arange(n)
    A, B = np.meshgrid(ax, ax)
    inside = np.hypot(A, B) <= R
    hv = (np.asarray(V, float) - P) @ u
    top = float(hv.max()) + 5.0
    o = P + A[inside][:, None] * e1 + B[inside][:, None] * e2 + top * u
    rc = _raycaster(V, F)
    t = np.empty(len(o))
    pid = np.empty(len(o), np.int64)
    for i in range(0, len(o), 2_000_000):
        t[i:i + 2_000_000], pid[i:i + 2_000_000] = _cast(rc, o[i:i + 2_000_000], np.broadcast_to(-u, o[i:i + 2_000_000].shape))
    hit = np.isfinite(t)
    h = np.where(hit, top - t, -1e4)
    rec: Dict[str, Any] = {"step_m": g, "cells": int(inside.sum()), "no_surface": int((~hit).sum())}
    if fill is not None and len(fill) == len(F):
        rec["on_fill"] = int(fill[pid[hit]].sum())
    if TOP_FLOATERS:
        try:
            h, rec["floaters"] = under_floaters(rc, o - top * u, h, hit, inside, P, u, g)
        except Exception as e:                                  # noqa: BLE001 - the top surface as it is
            log.warning("station mesh: the floaters' check failed (%s) - the top surface as it is", e)
    H = np.full(A.shape, -1e4, np.float32)
    H[inside] = h
    k = max(3, int(round(TOP_PIT_WIDTH_M / g)) | 1)
    Hc = ndi.grey_closing(H, size=(k, k))
    pit = (Hc - H > TOP_PIT_DEPTH_M) & (H > -5e3)
    H = np.where(pit, Hc, H)
    rec["pits_raised"] = int(pit.sum())
    if ceiling is not None:                                     # 1.0.6: under the mast's skyline (SkyCeiling)
        try:
            ok_ = inside & (H > -5e3)
            top_h = np.full(A.shape, np.inf)
            top_h[ok_], info = ceiling.limit(P + A[ok_][:, None] * e1 + B[ok_][:, None] * e2, H[ok_])
            over = ok_ & (H > top_h)
            dh = (H - top_h)[over]
            H = np.where(over, top_h, H).astype(np.float32)
            rec["sky_ceiling"] = {"cells": int(over.sum()), "m2": round(float(over.sum()) * g * g, 2),
                                  "behind_the_crest_m2": round(info["behind_the_crest"] * g * g, 2),
                                  "lowered_by_m_median": round(float(np.median(dh)), 3) if len(dh) else 0.0,
                                  "lowered_by_m_max": round(float(dh.max()), 3) if len(dh) else 0.0,
                                  "margin_deg": SKY_CEILING_MARGIN_DEG, "behind_deg": SKY_CEILING_BEHIND_DEG,
                                  "from_m": SKY_CEILING_FROM_M}
        except Exception as e:                                  # noqa: BLE001 - the sheet as it is
            log.warning("station mesh: the sky ceiling was not applied (%s)", e)
    ok = inside & (H > -5e3)
    idx = np.full(A.shape, -1, np.int64)
    idx[ok] = np.arange(int(ok.sum()))
    Vn = P + A[ok][:, None] * e1 + B[ok][:, None] * e2 + H[ok].astype(float)[:, None] * u
    a_, b_, c_, d_ = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
    q = (a_ >= 0) & (b_ >= 0) & (c_ >= 0) & (d_ >= 0)
    dg = np.abs(H[:-1, :-1] - H[1:, 1:]) <= np.abs(H[:-1, 1:] - H[1:, :-1])
    q1, q2 = q & dg, q & ~dg
    Fn = np.concatenate([np.stack([a_[q1], d_[q1], c_[q1]], 1), np.stack([a_[q1], b_[q1], d_[q1]], 1),
                         np.stack([a_[q2], b_[q2], c_[q2]], 1), np.stack([b_[q2], d_[q2], c_[q2]], 1)])
    if float(np.cross(e1, e2) @ u) < 0:                         # the winding's normals up
        Fn = Fn[:, ::-1]
    rec["grid_triangles"] = int(len(Fn))
    # the rocks by the rover (Christian, 22 Nov 2026: "Make sure not to simply the rocks in front of the rover too
    # much"): the grid's own heights where the ground is rough within TOP_ROCKS_TO_M - the simplified sheet is held to
    # them, with more triangles when it strays
    rough = (ndi.maximum_filter(np.where(ok, H, -1e4), size=max(3, int(round(0.25 / g)) | 1))
             - ndi.minimum_filter(np.where(ok, H, 1e4), size=max(3, int(round(0.25 / g)) | 1))) > TOP_ROCK_RELIEF_M
    rock = ok & rough & (np.hypot(A, B) <= TOP_ROCKS_TO_M)
    rk = np.flatnonzero(rock.ravel())
    if len(rk) > 60000:
        rk = rk[:: len(rk) // 60000 + 1]
    Vg, Fg, goal = Vn, Fn, int(target)
    for attempt in range(3):
        Vn, Fn, rec["passes"] = simplify_in_steps(Vg, Fg, goal, P, u)
        if not len(rk):
            break
        pts2 = P + A.ravel()[rk][:, None] * e1 + B.ravel()[rk][:, None] * e2 + H.ravel()[rk].astype(float)[:, None] * u
        err = _raycaster(Vn, Fn).compute_distance(o3d.core.Tensor(np.ascontiguousarray(pts2, np.float32))).numpy().astype(float)
        err = err[np.isfinite(err)]                             # (the distance to the sheet: a wall moved sideways by a
        #                                                         centimeter is a centimeter off, not its height)
        if not len(err):
            break
        rec["near_rocks"] = {"within_m": TOP_ROCKS_TO_M, "places": int(len(err)), "p95_mm": round(1000 * float(np.percentile(err, 95)), 2),
                             "p99_mm": round(1000 * float(np.percentile(err, 99)), 2), "max_mm": round(1000 * float(err.max()), 1),
                             "limit_p95_mm": TOP_ROCK_P95_MM, "triangles": int(len(Fn))}
        if rec["near_rocks"]["p95_mm"] <= TOP_ROCK_P95_MM or attempt == 2 or len(Fg) <= goal:
            break
        goal = int(goal * TOP_ROCK_MORE)
        log.info("station mesh: the rocks by the rover are %.1f mm off at 95 %% of places (limit %.1f) - simplified again to %d triangles",
                 rec["near_rocks"]["p95_mm"], TOP_ROCK_P95_MM, goal)
    rec.update(triangles=int(len(Fn)), near_m=TOP_NEAR_M, range_power=TOP_RANGE_POWER)
    return Vn, np.asarray(Fn, np.int64), rec


def repair_sheet(V: np.ndarray, F: np.ndarray, pivot, up) -> Tuple[np.ndarray, np.ndarray, Dict[str, int]]:
    """A simplified sheet put right before it is simplified further: triangles without area, repeated triangles and
    vertices and edges of more than two triangles are removed; a triangle folded over (its normal turned down) is
    smoothed out - its corners moved to the mean of their neighbors - and dropped if it stays folded, and the small
    holes these leave are closed with a fan.  Returns (V, F, counts)."""
    import open3d as o3d
    from .mesh import close_small_loops
    n0 = len(F)
    m = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(np.asarray(V, float)), o3d.utility.Vector3iVector(np.asarray(F, np.int32)))
    m.remove_degenerate_triangles()
    m.remove_duplicated_triangles()
    m.remove_duplicated_vertices()
    m.remove_non_manifold_edges()
    V2, F2 = np.asarray(m.vertices).copy(), np.asarray(m.triangles).astype(np.int64)
    removed = n0 - len(F2)
    u = _unit(up)
    fold = (triangle_normals(V2, F2)[0] @ u) <= 0.0
    folded = int(fold.sum())
    if folded:                                                   # a fold is first smoothed out: its corners to the
        from scipy.sparse import coo_matrix                      # mean of their neighbors (a few rounds) ...
        E = np.concatenate([F2[:, [0, 1]], F2[:, [1, 2]], F2[:, [2, 0]]])
        nv = np.int64(len(V2))
        ke = np.unique(np.concatenate([E[:, 0] * nv + E[:, 1], E[:, 1] * nv + E[:, 0]]))      # each neighbor once
        A = coo_matrix((np.ones(len(ke)), (ke // nv, ke % nv)), shape=(len(V2), len(V2))).tocsr()
        deg = np.maximum(np.asarray(A.sum(axis=1)).ravel(), 1.0)
        rim = np.zeros(len(V2), bool)                            # (the sheet's own edge stays where it is)
        kb, cb = np.unique(np.minimum(E[:, 0], E[:, 1]) * nv + np.maximum(E[:, 0], E[:, 1]), return_counts=True)
        rim[kb[cb == 1] // nv] = True
        rim[kb[cb == 1] % nv] = True
        for _ in range(REPAIR_SMOOTH_ROUNDS):
            mv = np.unique(F2[fold])
            mv = mv[~rim[mv]]
            if not len(mv):
                break
            V2[mv] = (A[mv] @ V2) / deg[mv][:, None]
            fold = (triangle_normals(V2, F2)[0] @ u) <= 0.0
            if not fold.any():
                break
    F2 = F2[~fold]                                               # ... and what is still folded is dropped
    V3, Fc, loops = close_small_loops(V2, F2, np.asarray(pivot, float), max_edges=REPAIR_LOOP_EDGES, max_diameter_m=REPAIR_LOOP_M)
    if len(Fc):
        F2 = np.vstack([F2, Fc])
    used = np.zeros(len(V3), bool)
    used[F2.ravel()] = True
    remap = np.cumsum(used) - 1
    return V3[used], remap[F2], {"removed": int(removed), "folded": folded, "folds_dropped": int(fold.sum()), "holes_closed": int(loops)}


REPAIR_SMOOTH_ROUNDS = 5        # rounds of moving a fold's corners to the mean of their neighbors
REPAIR_LOOP_EDGES = 60          # a hole the repair closes: at most this many edges ...
REPAIR_LOOP_M = 0.5             # ... and this wide (x (1 + range / 10 m))
SIMPLIFY_STEP = 0.5             # 1.0.5: each pass keeps this share of the triangles, then the sheet is repaired


def simplify_in_steps(V: np.ndarray, F: np.ndarray, target: int, pivot, up, step: float = SIMPLIFY_STEP
                      ) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, int]]]:
    """1.0.5 (Christian, 22 Nov 2026: "The simplification should simplify iteratively, reducing polygon count by ~50%
    repairing the mesh, then repeat until target poly count is met"): the sheet (V, F) simplified to ``target``
    triangles in passes that each keep ``step`` of the triangles (the last one what is left to the target); after
    every pass the sheet is repaired (:func:`repair_sheet`), so a fold or a hole is put right while it is one triangle
    and is not built upon.  Each pass works in the space scaled by the range (:func:`_range_warp`).  Returns
    (V, F, one record per pass)."""
    import open3d as o3d
    P = np.asarray(pivot, float)
    V, F = np.asarray(V, float), np.asarray(F, np.int64)
    passes: List[Dict[str, int]] = []
    target = int(target)
    while len(F) > target and len(passes) < 16:
        goal = int(len(F) * float(step))
        if goal <= target:                                       # the last pass: room for the repair's fans
            goal = int(target * (0.99 if not passes or passes[-1]["from"] > target * 1.02 else 0.97))
        m = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(_range_warp(V, P)), o3d.utility.Vector3iVector(F.astype(np.int32)))
        m = m.simplify_quadric_decimation(target_number_of_triangles=max(goal, 4))
        n_in = len(F)
        V, F, fix = repair_sheet(_range_warp(np.asarray(m.vertices), P, back=True), np.asarray(m.triangles), P, up)
        passes.append(dict({"from": int(n_in), "to": int(len(F))}, **fix))
        if len(F) >= n_in:                                       # nothing went: no further pass would do better
            break
    return V, F, passes


def terrain_mesh(scene, pivot, up, radius_m: float = RADIUS_M, target: int = TARGET_TRIANGLES, ceiling=None,
                 ceiling_key=None) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """(V, F, record) of the scene's mesh within ``radius_m`` of the mast axis, without the rover model, simplified:
    as one sheet (1.0.5, :func:`top_sheet`), or - ``TOP_SHEET`` off, or the sheet failed - its triangles simplified."""
    from .mesh import decimate_and_smooth, horizontal_distance, keep_triangles
    V, F = np.asarray(scene.mesh_V, float), np.asarray(scene.mesh_F, np.int64)
    keep = np.ones(len(F), bool)
    rt = getattr(scene, "rover_triangles", None)
    if rt is not None:
        keep[rt[0]:rt[1]] = False
    near = horizontal_distance(V, pivot, up) <= float(radius_m)
    keep &= near[F].all(axis=1)
    if not keep.any():
        raise ValueError(f"station mesh: no terrain within {radius_m:g} m of the mast axis")
    if TOP_SHEET:
        try:
            tt = getattr(scene, "terrain_triangles", None)
            fill = None
            if tt is not None:
                fill = np.ones(len(F), bool)
                fill[tt[0]:tt[1]] = False
            wide = horizontal_distance(V, pivot, up) <= float(radius_m) + 0.5      # the sheet's rim has ground under it
            kw = wide[F].any(axis=1)
            if rt is not None:
                kw[rt[0]:rt[1]] = False
            key = (float(radius_m), int(target), TOP_STEP_M, TOP_RANGE_POWER, tuple(np.round(np.asarray(pivot, float), 6)),
                   ceiling_key)
            cache = getattr(scene, "_top_sheet", None)
            if cache is not None and cache[0] == key:           # the terrain and the scape parts ask for the same sheet
                Vt, Ft, top = cache[1]
            else:
                Vt, Ft, top = top_sheet(V, F[kw], pivot, up, radius_m, target, fill=None if fill is None else fill[kw],
                                        ceiling=ceiling)
                try:
                    scene._top_sheet = (key, (Vt, Ft, top))
                except Exception:                               # noqa: BLE001 - a scene that takes no attribute
                    pass
            if len(Ft):
                return Vt, Ft, {"triangles_within_radius": int(keep.sum()), "triangles": int(len(Ft)),
                                "radius_m": float(radius_m), "top_sheet": top}
        except Exception as e:                                  # noqa: BLE001 - the mesh's own triangles, as before 1.0.5
            log.warning("station mesh: the one-sheet terrain failed (%s) - the mesh's triangles are simplified instead", e)
    V2, F2 = keep_triangles(V, F, keep)
    n0 = len(F2)
    V2, F2, rep = decimate_and_smooth(V2, F2, target_triangles=int(target), taubin_iterations=0)
    return np.asarray(V2, float), np.asarray(F2, np.int64), {"triangles_within_radius": int(n0), "triangles": int(len(F2)),
                                                            "radius_m": float(radius_m)}


def _raycaster(V: np.ndarray, F: np.ndarray):
    import open3d as o3d
    sc = o3d.t.geometry.RaycastingScene()
    sc.add_triangles(o3d.core.Tensor(np.asarray(V, np.float32)), o3d.core.Tensor(np.asarray(F, np.uint32)))
    return sc


def _cast(rc, o: np.ndarray, d: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    import open3d as o3d
    rays = np.concatenate([np.broadcast_to(np.asarray(o, np.float32), np.shape(d)), np.asarray(d, np.float32)], axis=1)
    ans = rc.cast_rays(o3d.core.Tensor(np.ascontiguousarray(rays)))
    return ans["t_hit"].numpy().astype(np.float64), ans["primitive_ids"].numpy().astype(np.int64)


def triangle_normals(V: np.ndarray, F: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """(unit normals, areas) of the triangles (the winding's normal)."""
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    n = np.cross(b - a, c - a)
    ln = np.linalg.norm(n, axis=1)
    return n / np.maximum(ln, 1e-15)[:, None], 0.5 * ln


def test_points(V: np.ndarray, F: np.ndarray, shrink: float = 0.25) -> np.ndarray:
    """(m, 4, 3): the centroid and the three corners moved ``shrink`` of the way to it, per triangle."""
    tri = V[F]
    cen = tri.mean(axis=1)
    return np.concatenate([cen[:, None], tri + shrink * (cen[:, None] - tri)], axis=1)


UNDER_SHEET_M = 0.35            # 1.0.2: a triangle with the mesh this near straight above it lies under another sheet


def under_a_sheet(rc, pts: np.ndarray, up, max_m: float = UNDER_SHEET_M, off_m: float = 0.003) -> np.ndarray:
    """1.0.2: True where the mesh in ``rc`` lies within ``max_m`` straight above each point (k, 3) - the fill's
    underlay beneath the measured surface, the patch under the rover where the two overlap."""
    u = _unit(up)
    o = np.asarray(pts, float) + off_m * u
    t, _ = _cast(rc, o, np.broadcast_to(u, o.shape))
    return t < float(max_m)


def seen_from(rc, pts: np.ndarray, viewpoint: np.ndarray, tol_rel: float = 2e-3, tol_m: float = 2e-3) -> np.ndarray:
    """True where nothing of the mesh in ``rc`` lies between ``viewpoint`` and each point (k, 3)."""
    v = np.asarray(pts, float) - viewpoint
    r = np.linalg.norm(v, axis=1)
    t, _ = _cast(rc, viewpoint, v / np.maximum(r, 1e-12)[:, None])
    return ~(t < r * (1.0 - tol_rel) - tol_m)


# ------------------------------------------------------------------------------------------- the disc
def _theta_of_rho(rho: np.ndarray, rpx: float, theta_max: float, knee) -> np.ndarray:
    """The angle from straight down of a texel ``rho`` px from the map's center.  ``knee`` (0.99.32) = (angle, share):
    the angles up to it fill the share of the radius evenly, the rest - the sky, to the zenith - the remainder."""
    if not knee:
        return rho / rpx * theta_max
    tk, fr = float(knee[0]), float(knee[1])
    x = rho / rpx
    return np.where(x <= fr, x / fr * tk, tk + (np.clip(x, fr, 1.0) - fr) / (1.0 - fr) * (np.pi - tk))


def _rho_of_theta(th: np.ndarray, rpx: float, theta_max: float, knee) -> np.ndarray:
    if not knee:
        return th / theta_max * rpx
    tk, fr = float(knee[0]), float(knee[1])
    return rpx * np.where(th <= tk, th / tk * fr, fr + (th - tk) / (np.pi - tk) * (1.0 - fr))


def disc_dirs(rows: np.ndarray, cols: np.ndarray, size: int, rpx: float, theta_max: float, up, north, east, knee=None) -> Tuple[np.ndarray, np.ndarray]:
    """(unit directions (n, 3), texel radius (n,) px) of the texels (rows, cols) of the azimuthal map (see the module)."""
    c = size / 2.0
    dx = np.asarray(cols, float) + 0.5 - c
    dy = c - (np.asarray(rows, float) + 0.5)
    rho = np.hypot(dx, dy)
    th = _theta_of_rho(rho, rpx, theta_max, knee)
    ph = np.arctan2(dx, dy)
    s = np.sin(th)
    d = (np.cos(th)[:, None] * -_unit(up) + (s * np.sin(ph))[:, None] * _unit(east) + (s * np.cos(ph))[:, None] * _unit(north))
    return d, rho


def disc_uv(X: np.ndarray, C, size: int, rpx: float, theta_max: float, up, north, east, knee=None) -> np.ndarray:
    """Texture coordinates (0..1, v down from the top) of the points (n, 3) on the azimuthal map about C."""
    v = np.asarray(X, float) - np.asarray(C, float)
    r = np.linalg.norm(v, axis=1)
    v = v / np.maximum(r, 1e-12)[:, None]
    th = np.arccos(np.clip(v @ -_unit(up), -1.0, 1.0))
    ph = np.arctan2(v @ _unit(east), v @ _unit(north))
    rho = _rho_of_theta(th, rpx, theta_max, knee)
    c = size / 2.0
    return np.stack([(c + rho * np.sin(ph)) / size, (c - rho * np.cos(ph)) / size], axis=1)


# ------------------------------------------------------------------------------------------- the cells
def triangle_layout(V: np.ndarray, F: np.ndarray, normals: np.ndarray) -> Dict[str, np.ndarray]:
    """Each triangle laid flat in its own plane: "e1", "e2" (unit, in the plane; e1 along the first edge, e2 = n x e1),
    "a" (the first corner), "p" (m, 3, 2) the corners in (e1, e2) meters, "lo", "hi" (m, 2) their box."""
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    e1 = b - a
    e1 = e1 / np.maximum(np.linalg.norm(e1, axis=1), 1e-15)[:, None]
    e2 = np.cross(normals, e1)
    e2 = e2 / np.maximum(np.linalg.norm(e2, axis=1), 1e-15)[:, None]
    p = np.stack([np.zeros((len(F), 2)), np.stack([((b - a) * e1).sum(1), ((b - a) * e2).sum(1)], 1),
                  np.stack([((c - a) * e1).sum(1), ((c - a) * e2).sum(1)], 1)], axis=1)
    return {"e1": e1, "e2": e2, "a": a, "p": p, "lo": p.min(axis=1), "hi": p.max(axis=1)}


def cell_sizes(lay: Dict[str, np.ndarray], texel_m: float, gutter: int = GUTTER_PX, max_px: int = MAX_CELL_PX) -> Tuple[np.ndarray, np.ndarray]:
    """((m, 2) int cell width and height in texels, (m,) the texel size of each cell, m)."""
    ext = lay["hi"] - lay["lo"]
    s = np.full(len(ext), float(texel_m))
    big = ext.max(axis=1) / s > (max_px - 2 * gutter)
    s[big] = ext[big].max(axis=1) / (max_px - 2 * gutter)
    wh = np.ceil(ext / s[:, None]).astype(np.int64) + 1 + 2 * gutter
    return wh, s


def free_intervals(y0: int, y1: int, size: int, disc: Optional[Tuple[float, float]]) -> List[Tuple[int, int]]:
    """The column intervals [a, b) of the rows [y0, y1) that are clear of the disc (center, radius in px)."""
    if disc is None:
        return [(0, size)]
    c, R = disc
    lo, hi = float(y0), float(y1)
    dmin = 0.0 if lo <= c <= hi else min(abs(lo - c), abs(hi - c))
    if dmin >= R:
        return [(0, size)]
    half = float(np.sqrt(R * R - dmin * dmin))
    return [iv for iv in ((0, int(np.floor(c - half))), (int(np.ceil(c + half)), size)) if iv[1] > iv[0]]


def shelf_pack(wh: np.ndarray, size: int, disc: Optional[Tuple[float, float]] = None,
               reserved: Sequence[Tuple[int, int, int, int]] = ()) -> Optional[np.ndarray]:
    """(m, 2) top-left corners of the cells ``wh`` in a ``size`` square, shelves from the top, the tallest first, clear
    of the disc and of the ``reserved`` rectangles (x, y, w, h); None when they do not fit."""
    n = len(wh)
    pos = np.full((n, 2), -1, np.int64)
    order = np.argsort(-wh[:, 1], kind="stable")
    i, y = 0, 0
    while i < n:
        h = int(wh[order[i], 1])
        if y + h > size:
            return None
        ivs = free_intervals(y, y + h, size, disc)
        cut = []
        for a, b in ivs:                                        # the reserved rectangles split the intervals further
            parts = [(a, b)]
            for (rx, ry, rw, rh) in reserved:
                if ry < y + h and y < ry + rh:
                    nxt = []
                    for p0, p1 in parts:
                        if rx >= p1 or rx + rw <= p0:
                            nxt.append((p0, p1))
                        else:
                            nxt += [q for q in ((p0, rx), (rx + rw, p1)) if q[1] > q[0]]
                    parts = nxt
            cut += parts
        for a, b in cut:
            x = a
            while i < n and x + int(wh[order[i], 0]) <= b:
                pos[order[i]] = (x, y)
                x += int(wh[order[i], 0])
                i += 1
        y += h
    return pos


def layout_cells(lay: Dict[str, np.ndarray], areas: np.ndarray, size: int, disc: Optional[Tuple[float, float]] = None,
                 reserved: Sequence[Tuple[int, int, int, int]] = (), fill: float = 0.8) -> Dict[str, Any]:
    """The cells of the triangles of ``lay`` at the finest texel size that fits: {"pos", "wh", "s" (texel m per
    cell), "texel_m", "A" (m, 3, 3: texel center (x + 0.5, y + 0.5, 1) -> the point in the block), "uv" (m, 3, 2)}."""
    m = len(areas)
    if m == 0:
        return {"pos": np.zeros((0, 2), np.int64), "wh": np.zeros((0, 2), np.int64), "s": np.zeros(0), "texel_m": None,
                "A": np.zeros((0, 3, 3)), "uv": np.zeros((0, 3, 2))}
    free = size * size - (np.pi * disc[1] ** 2 if disc else 0.0) - sum(r[2] * r[3] for r in reserved)
    ext = lay["hi"] - lay["lo"]
    t = float(np.sqrt(max(2.2 * float((ext[:, 0] * ext[:, 1]).sum()), 1e-12) / max(fill * free, 1.0)))
    for _ in range(60):
        wh, s = cell_sizes(lay, t)
        pos = shelf_pack(wh, size, disc, reserved)
        if pos is not None:
            break
        t *= 1.12
    else:
        raise RuntimeError("station mesh: the cells do not fit the texture")
    g = GUTTER_PX
    ox = pos[:, 0] + g - lay["lo"][:, 0] / s                  # texel x of the plane's origin (corner a)
    oy = pos[:, 1] + g - lay["lo"][:, 1] / s
    A = np.zeros((m, 3, 3))
    A[:, :, 0] = lay["e1"] * s[:, None]
    A[:, :, 1] = lay["e2"] * s[:, None]
    A[:, :, 2] = lay["a"] - lay["e1"] * (ox * s)[:, None] - lay["e2"] * (oy * s)[:, None]
    px = ox[:, None] + lay["p"][:, :, 0] / s[:, None]
    py = oy[:, None] + lay["p"][:, :, 1] / s[:, None]
    uv = np.stack([px / size, py / size], axis=2)
    return {"pos": pos, "wh": wh, "s": s, "texel_m": float(t), "A": A, "uv": uv}


def band_cells(cells: Dict[str, Any], normals: np.ndarray, r0: int, r1: int) -> Dict[str, np.ndarray]:
    """The cells that meet the rows [r0, r1): {"rect" (k, 4) x, y, w, h, "A", "n"}.  1.0: of a chart layout
    (:func:`layout_charts`, "tri_map"), the band's texels by triangle instead: {"tmap" (r1 - r0, S) the band's own
    triangle numbers (-1: none), "tA" (k, 3, 3), "tn" (k, 3)}."""
    if cells.get("tri_map") is not None:
        rows = np.asarray(cells["tri_map"][r0:r1])
        ids = np.unique(rows[rows >= 0])
        tmap = np.full(rows.shape, -1, np.int32)
        tmap[rows >= 0] = np.searchsorted(ids, rows[rows >= 0])
        return {"rect": np.zeros((0, 4), np.int64), "A": np.zeros((0, 3, 3)), "n": np.zeros((0, 3)), "tmap": tmap,
                "tA": np.asarray(cells["tri_A"])[ids], "tn": np.asarray(normals)[ids]}
    if not len(cells["pos"]):
        return {"rect": np.zeros((0, 4), np.int64), "A": np.zeros((0, 3, 3)), "n": np.zeros((0, 3))}
    y, h = cells["pos"][:, 1], cells["wh"][:, 1]
    k = np.flatnonzero((y < r1) & (y + h > r0))
    return {"rect": np.concatenate([cells["pos"][k], cells["wh"][k]], axis=1), "A": cells["A"][k], "n": normals[k]}


# ------------------------------------------------------------------------------------------- the texels
def texture_rows(scene, sources: Sequence[Any], args: Dict[str, Any], r0: int, r1: int) -> Dict[str, Any]:
    """The rows [r0, r1) of a station mesh texture (the band of a worker, :mod:`rpp.ibr.parallel`): the fields of
    :data:`rpp.ibr.ods.BAND_FIELDS`, (r1 - r0, size) each."""
    from .ods import BAND_FIELDS, shade_rays
    S = int(args["size"])
    nrow = r1 - r0
    flat, O, D = [], [], []
    dsc = args.get("disc")
    if dsc:
        rr, cc = np.mgrid[r0:r1, 0:S]
        d, rho = disc_dirs(rr.ravel(), cc.ravel(), S, dsc["rpx"], dsc["theta_max"], dsc["up"], dsc["north"], dsc["east"], knee=dsc.get("knee"))
        inside = rho <= dsc["rpx"] + GUTTER_PX
        flat.append(np.flatnonzero(inside))
        D.append(d[inside])
        O.append(np.broadcast_to(np.asarray(dsc["C"], float), (int(inside.sum()), 3)))
    bc = args.get("cells") or {}
    off = float(args.get("offset_m", TERRAIN_OFFSET_M))
    for (x, y, w, h), A, n in zip(bc.get("rect", ()), bc.get("A", ()), bc.get("n", ())):
        ya, yb = max(int(y), r0), min(int(y + h), r1)
        if yb <= ya:
            continue
        yy, xx = np.mgrid[ya:yb, int(x):int(x + w)]
        q = np.stack([xx.ravel() + 0.5, yy.ravel() + 0.5, np.ones(xx.size)], axis=1)
        X = q @ np.asarray(A).T
        flat.append((yy.ravel() - r0) * S + xx.ravel())
        O.append(X + off * np.asarray(n))
        D.append(np.broadcast_to(-np.asarray(n, float), X.shape))
    tm = bc.get("tmap")
    if tm is not None and len(bc.get("tA", ())):                # 1.0: a chart texel's point on its own triangle's plane
        yy, xx = np.nonzero(tm >= 0)
        tt = tm[yy, xx]
        q = np.stack([xx + 0.5, yy + r0 + 0.5, np.ones(len(xx))], axis=1)
        X = np.einsum("nij,nj->ni", np.asarray(bc["tA"])[tt], q)
        nn = np.asarray(bc["tn"], float)[tt]
        flat.append(yy * S + xx)
        O.append(X + off * nn)
        D.append(-nn)
    linear = bool(args.get("linear"))
    band: Dict[str, Any] = {"rgb": np.zeros((nrow * S, 3), np.float32 if linear else np.uint8),
                            "source": np.full(nrow * S, -1, np.int16), "label": np.zeros(nrow * S, np.uint8),
                            "range": np.zeros(nrow * S, np.float32), "hidden": np.zeros(nrow * S, bool),
                            "ground": np.zeros(nrow * S, bool), "rover": np.zeros(nrow * S, bool),
                            "rej_map": np.zeros(nrow * S, bool), "prov": np.zeros((nrow * S, 3), np.uint8),
                            "rejected": [0, 0], "neff": None}
    if flat:
        idx = np.concatenate(flat)
        o, d = np.concatenate(O).astype(float), np.concatenate(D).astype(float)
        fam = args.get("families")
        srcs = [s for s in sources if s.name[:1] in fam] if fam else list(sources)
        fallback = bool(args.get("rover_fallback"))
        if fallback:                                             # 1.0.5: the station's own frames only (see rover_part)
            srcs = [s for s in srcs if not (getattr(s, "context", False) or getattr(s, "no_rover", False)
                                            or getattr(s, "fill_only", False))]
        if len(idx) and srcs:
            from . import ods as _ods
            keep_check = _ods.SURFACE_CHECK
            try:
                if fallback:                                     # ... without the rover mask's say
                    _ods.SURFACE_CHECK = False
                res = shade_rays(scene, srcs, o, d, up=args.get("up", (0, 0, 1)), linear=linear)
            finally:
                _ods.SURFACE_CHECK = keep_check
            for k in BAND_FIELDS:
                band[k][idx] = res[k]
            band["rejected"] = res["rejected"]
    for k in BAND_FIELDS:
        band[k] = band[k].reshape((nrow, S) + band[k].shape[1:])
    return band


def render_texture(scene, sources: Sequence[Any], args: Dict[str, Any], pool=None, rows_per_chunk: int = 128) -> Dict[str, np.ndarray]:
    """{"rgb" (S, S, 3), "source" (S, S) int16} of a texture (``args`` as :func:`texture_rows` takes them, without
    "cells": ``args["all_cells"]`` and ``args["normals"]``)."""
    S = int(args["size"])
    spans = [(r0, min(S, r0 + rows_per_chunk)) for r0 in range(0, S, rows_per_chunk)]
    base = {k: v for k, v in args.items() if k not in ("all_cells", "normals", "want_sky")}
    per = [dict(base, cells=band_cells(args["all_cells"], args["normals"], r0, r1)) for r0, r1 in spans]
    rgb = np.zeros((S, S, 3), np.float32 if args.get("linear") else np.uint8)
    src = np.full((S, S), -1, np.int16)
    sky = np.zeros((S, S), bool) if args.get("want_sky") else None      # 0.99.32: the far surface's texels

    def here(todo):
        for r0, r1 in todo:
            yield r0, r1, texture_rows(scene, sources, per[spans.index((r0, r1))], r0, r1)

    bands = pool.run("texture", per, spans, S, S, bool(args.get("linear")), here, "texture") if pool is not None else here(spans)
    for r0, r1, band in bands:
        rgb[r0:r1] = band["rgb"]
        src[r0:r1] = band["source"]
        if sky is not None:                                      # 0.99.32: the sky's texels (not the far terrain's)
            from .raycast import LABEL_FAR                       # beyond the mesh and the plane: the sky and the far hills
            sky[r0:r1] = band["label"] == LABEL_FAR
    band = bands = None
    return {"rgb": rgb, "source": src, "sky": sky}


SKY_REF_EL_DEG = 15.0           # the sky's brightness: the far texels the frames colored above this elevation


def sky_texels(rgb: np.ndarray, far: np.ndarray, have: np.ndarray, in_disc: np.ndarray, size: int, rpx: float, knee) -> np.ndarray:
    """0.99.41: the texels of the fifth mode's texture that are sky.  ``far`` (the rays that met neither the mesh nor
    the ground plane) holds the sky AND the hills beyond the mesh, so it is not whitened whole: a far texel is sky
    when it is brighter than midway (in log) between the sky above SKY_REF_EL_DEG and the mesh's ground - or no frame
    colored it - and is joined through such texels to the zenith (the disc's rim).  Darker far texels (distant hills,
    a crater rim) keep their colors.  Without enough sky above SKY_REF_EL_DEG to measure: the far texels beyond the
    skyline's circle."""
    import cv2
    ax = (np.arange(size, dtype=np.float32) + 0.5 - size / 2.0) ** 2
    rho2 = ax[None, :] + ax[:, None]
    lum = rgb.mean(axis=2)
    r_ref = float(_rho_of_theta(np.array([np.pi / 2 + np.radians(SKY_REF_EL_DEG)]), rpx, np.pi, knee)[0])
    hi = far & have & (rho2 > np.float32(r_ref ** 2))
    ground = in_disc & have & ~far
    r_pole = float(_rho_of_theta(np.array([np.pi / 2 + np.radians(POLE_WHITE_EL_DEG)]), rpx, np.pi, knee)[0])
    if hi.sum() < 100 or ground.sum() < 100:
        return (far & (rho2 > np.float32((knee[1] * rpx + 1.0) ** 2))) | (in_disc & (rho2 > np.float32(r_pole ** 2)))
    cut = float(np.exp(0.5 * (np.log(max(float(np.median(lum[hi][::17])), 1e-6)) + np.log(max(float(np.median(lum[ground][::97])), 1e-6)))))
    like = (far & (~have | (lum > cut))).astype(np.uint8)
    del lum
    _, comp = cv2.connectedComponents(like, connectivity=8)
    ring = (rho2 > np.float32((rpx - 4.0) ** 2)) & (like > 0)      # the zenith: the disc's last texels
    ids = np.unique(comp[ring])
    # 0.99.52 (Christian, 20 Nov 2026: "the top pole in the ods and full 3d models are visible as a convergent
    # discolored point"): every texel above POLE_WHITE_EL_DEG is sky - the zenith is the disc's rim, one point
    out = np.isin(comp, ids[ids > 0]) | (in_disc & (rho2 > np.float32(r_pole ** 2)))
    # 0.99.52 (Christian, 20 Nov 2026: "the oeb enhanced tone skin has really bad sky artifacts" - a dark wavy band at the
    # frames' tops and patches afloat over the horizon, which the tone mapping brought out): beyond the skyline's
    # circle (the knee: the highest mesh plus its margin) every far texel is sky; inside it a far patch that is not
    # sky stays only when it stands on the ground (touches texels of the mesh) - a hill does, a floater does not
    out |= far & (rho2 > np.float32((knee[1] * rpx + 1.0) ** 2))
    rest = (far & ~out).astype(np.uint8)
    if rest.any():
        n, comp2 = cv2.connectedComponents(rest, connectivity=8)
        near = cv2.dilate(ground.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        stands = np.zeros(n, bool)
        stands[np.unique(comp2[near & (rest > 0)])] = True
        stands[0] = True
        out |= ~stands[comp2] & (rest > 0)
    if SKYLINE_ONE:
        out = one_skyline(rgb, out, far, have, in_disc, rho2, size, rpx, knee)
    return out


# 1.0 (Christian, 20 Nov 2026, Van Zyl: "the van zyl sky looks really bad here too" - the far hills' tops torn, white
# holes in them and hill patches standing in the sky; "Make sure to improve the horizon and sky boundary problem"):
# the white sky of the fifth mode's texture ends at ONE skyline - per SKYLINE_BIN_DEG of azimuth the highest texel that
# is not sky (the mesh, or a far hill), median filtered over SKYLINE_MEDIAN_BINS: above it every far texel is white,
# below it none is, and a far texel below it that was taken for sky takes the colors of the hills around it
SKYLINE_ONE = True
SKY_IMAGED = True                # 1.0.1: the sky as the frames show it (the panorama's own), not white - see smooth_sky
SKY_FEATHER_DEG = 1.5            # ... sharp to smoothed over this below the skyline's circle
SKY_SMOOTH_DEG = 3.0             # ... the Gaussian mean above it (the panoramas' enhanced views smooth their sky by 3 deg too)
SKYLINE_BIN_DEG = 0.25
SKYLINE_MEDIAN_BINS = 9          # 2.25 deg
SKYLINE_LOW_EL_DEG = -5.0        # the skyline is looked for above this elevation


def one_skyline(rgb: np.ndarray, sky: np.ndarray, far: np.ndarray, have: np.ndarray, in_disc: np.ndarray,
                rho2: np.ndarray, size: int, rpx: float, knee) -> np.ndarray:
    """The sky texels of :func:`sky_texels` made to end at one skyline (above); the far texels below it that were sky
    are filled from the hills (``rgb`` in place).  Returns the new sky mask."""
    from scipy.ndimage import median_filter
    lo = float(_rho_of_theta(np.array([np.pi / 2 + np.radians(SKYLINE_LOW_EL_DEG)]), rpx, np.pi, knee)[0])
    hi = (knee[1] * rpx + 1.0) if knee else rpx
    band = in_disc & (rho2 > np.float32(lo * lo)) & (rho2 < np.float32(hi * hi))
    ys, xs = np.nonzero(band & ~sky)
    if len(ys) < 100:
        return sky
    nb = int(round(360.0 / SKYLINE_BIN_DEG))
    c = size / 2.0

    def bins(yy, xx):
        return (((np.arctan2(c - (yy + 0.5), (xx + 0.5) - c) + np.pi) / (2 * np.pi) * nb).astype(np.int64)) % nb
    top = np.full(nb, lo, np.float64)
    np.maximum.at(top, bins(ys, xs), np.sqrt(rho2[ys, xs].astype(np.float64)))
    top = median_filter(top, size=SKYLINE_MEDIAN_BINS, mode="wrap")
    by, bx = np.nonzero(band | (far & in_disc & (rho2 >= np.float32(hi * hi))))
    above = np.sqrt(rho2[by, bx].astype(np.float64)) > top[bins(by, bx)]
    new = sky.copy()
    keep_far = far[by, bx]
    new[by[above & keep_far], bx[above & keep_far]] = True        # above the skyline: every far texel is sky
    new[by[~above], bx[~above]] = False                          # below it: none is
    holes = sky & ~new
    if holes.any():                                              # far texels below the skyline taken for sky: the hills'
        src = in_disc & have & ~new & ~holes                     # colors (all the texture's ground, pulled coarse to fine)
        push_pull(rgb, src, holes)
    log.info("station mesh: one skyline - %d far texels above it white, %d below it from the hills",
             int((new & ~sky).sum()), int(holes.sum()))
    return new


def pano_sky(pano: np.ndarray, azimuth0_deg: float, d: np.ndarray, up, north, east) -> np.ndarray:
    """1.0.2: the colors (n, 3) an equirectangular eye ``pano`` (row 0 the zenith, the left edge of column 0 at
    ``azimuth0_deg`` east of north) shows along the unit directions ``d`` (n, 3) - bilinear, wrapped in azimuth."""
    u, n_, e = _unit(up), _unit(north), _unit(east)
    H, W = pano.shape[:2]
    el = np.degrees(np.arcsin(np.clip(d @ u, -1.0, 1.0)))
    az = np.degrees(np.arctan2(d @ e, d @ n_))
    x = ((az - float(azimuth0_deg)) / 360.0 % 1.0) * W - 0.5
    y = np.clip((90.0 - el) / 180.0 * H - 0.5, 0.0, H - 1.0)
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    xa, xb = x0 % W, (x0 + 1) % W
    ya, yb = y0, np.minimum(y0 + 1, H - 1)
    P = np.asarray(pano, np.float32)
    return (P[ya, xa, :3] * (1 - fx) + P[ya, xb, :3] * fx) * (1 - fy) + (P[yb, xa, :3] * (1 - fx) + P[yb, xb, :3] * fx) * fy


SKY_MODEL = True                # 1.0.5: above the skyline's circle the sky is a model of the panorama's (see sky_model)
SKY_MODEL_OUTLIER = 0.2         # a sky pixel this far (relative) from its row's median brightness is left out
SKY_MODEL_FADE_DEG = 12.0       # the sky's own color along the circle fades into the rows' color over this elevation


def sky_model(pano: np.ndarray, circle_el_deg: float) -> np.ndarray:
    """1.0.5 (Christian, 22 Nov 2026, Rockytop in the headset: "the top pole has artifacts in the sky" - a dark red
    patch by the zenith where the panorama has no sky of its own; Wildcat Ridge: a violet oval over the ridge, the
    sky the frames show beside the white the panorama fills in): the panorama's sky above ``circle_el_deg`` as a
    smooth model, (180, 360, 3) at one degree per pixel in the panorama's layout.

    * every degree of elevation has ONE color: the median of its pixels over all azimuths, without those that are
      empty or more than ``SKY_MODEL_OUTLIER`` off the row's brightness; a row with too few takes the row beneath;
    * along the circle the sky keeps the color the panorama has there in each direction (smoothed over azimuth), so
      it meets the imaged sky below the circle without a step, and that difference fades out over
      ``SKY_MODEL_FADE_DEG`` above it."""
    import cv2
    from scipy import ndimage as ndi
    P = np.ascontiguousarray(np.asarray(pano, np.float32)[..., :3])
    small = cv2.resize(P, (360, 180), interpolation=cv2.INTER_AREA).astype(np.float64)
    lum = small.sum(axis=2)
    ec = int(np.clip(round(90.0 - float(circle_el_deg)), 2, 178))        # the circle's row (row 0: the zenith)
    prof = np.full((180, 3), np.nan)
    for r in range(0, ec + 3):
        v = lum[r] > 0
        if v.sum() < 30:
            continue
        med = np.median(lum[r][v])
        inl = v & (np.abs(lum[r] - med) <= SKY_MODEL_OUTLIER * med)
        if inl.sum() >= 30:
            prof[r] = np.median(small[r][inl], axis=0)
    have = np.flatnonzero(np.isfinite(prof[:, 0]))
    if not len(have):
        raise ValueError("the panorama has no sky above the skyline's circle")
    for r in range(ec + 2, -1, -1):                              # an empty row: the row beneath it (toward the circle)
        if not np.isfinite(prof[r, 0]):
            below = have[have > r]
            prof[r] = prof[below.min()] if len(below) else prof[have.max()]
    prof[: ec + 3] = ndi.uniform_filter1d(prof[: ec + 3], size=5, axis=0, mode="nearest")
    # the sky's own color along the circle, by azimuth: a robust band just above it, smoothed around the compass
    band = small[max(ec - 3, 0): ec + 1]
    anchor = np.median(band, axis=0)                             # (360, 3)
    ref = prof[max(ec - 1, 0)]
    okc = (anchor.sum(axis=1) > 0) & (np.abs(anchor.sum(axis=1) - ref.sum()) <= 2 * SKY_MODEL_OUTLIER * ref.sum())
    delta = np.where(okc[:, None], anchor - ref, 0.0)
    wgt = ndi.gaussian_filter1d(okc.astype(float), 8.0, mode="wrap")
    delta = ndi.gaussian_filter1d(delta, 8.0, axis=0, mode="wrap") / np.maximum(wgt, 1e-3)[:, None] * (wgt > 0.05)[:, None]
    out = np.repeat(prof[:, None, :], 360, axis=1)
    rows = np.arange(180)
    fade = np.exp(-np.clip(ec - rows, 0, None) / float(SKY_MODEL_FADE_DEG))
    out += delta[None, :, :] * fade[:, None, None]
    return np.maximum(out, 0.0).astype(np.float32)


def smooth_sky(rgb: np.ndarray, far: np.ndarray, size: int, rpx: float, knee, feather_deg: float = SKY_FEATHER_DEG,
               sigma_deg: float = SKY_SMOOTH_DEG, pano=None, frame=None) -> int:
    """1.0.1 (Christian, 21 Nov 2026: "use the panoramas own sky instead of white. Make sure that artifacts above the sky
    line are smoothed out"): the far texels (``far``: the sky and the hills beyond the mesh, colored by the frames or
    filled from them) keep their colors below the skyline's circle - the hills, as in the panorama - and above it are
    the far texels' own Gaussian mean (``sigma_deg`` at the circle's texel scale), which takes out the frames' edges
    and blemishes; the two are mixed over ``feather_deg`` below the circle.  ``rgb`` float in place.  Returns the
    texels changed.

    ``pano`` = (an eye of the station's panorama, linear, in the texture's units; its azimuth0_deg) with ``frame`` =
    (up, north, east): above the circle the texels take the PANORAMA'S sky in their direction, not the mean
    (Christian, 21 Nov 2026: "fix the streaks in the full-3d. it isn't an issue in the ods" - the panorama's sky is one
    smooth fit; the texture's own far texels, filled column by column where no frame saw the sky, ran as streaks to
    the zenith, tens of degrees wide - wider than any mean of a few degrees)."""
    import cv2
    if not knee or not far.any():
        return 0
    tk = float(knee[0])
    r1 = float(knee[1]) * rpx
    r0 = float(_rho_of_theta(np.array([tk - np.radians(feather_deg)]), rpx, np.pi, knee)[0])
    if not r1 > r0:
        return 0
    k = max(1, int(round(size / 1024.0)))                      # the mean at about 1024 px: the sky has no detail to keep
    n = size // k
    w = cv2.resize(far.astype(np.float32), (n, n), interpolation=cv2.INTER_AREA)
    px_per_deg = (r1 / max(np.degrees(tk), 1e-6)) / k
    sig = float(max(sigma_deg * px_per_deg, 2.0))
    wb = cv2.GaussianBlur(w, (0, 0), sig)
    ys, xs = np.nonzero(far)
    c = size / 2.0
    rho = np.hypot(xs + 0.5 - c, c - (ys + 0.5))
    t = np.clip((rho - r0) / (r1 - r0), 0.0, 1.0).astype(np.float32)
    m = t > 0
    if not m.any():
        return 0
    ys, xs, t = ys[m], xs[m], t[m]
    t = t * t * (3.0 - 2.0 * t)                                 # smoothstep
    if pano is not None and frame is not None:
        try:
            d, _ = disc_dirs(ys, xs, size, rpx, np.pi, frame[0], frame[1], frame[2], knee=knee)
            src = pano[0]
            if SKY_MODEL:                                        # 1.0.5: not the panorama's pixels - a model of its sky
                try:
                    src = sky_model(pano[0], float(np.degrees(tk)) - 90.0)
                except Exception as e:                           # noqa: BLE001 - the panorama's own pixels
                    log.warning("station mesh: no model of the panorama's sky (%s) - its own pixels", e)
            col = pano_sky(src, float(pano[1]), np.asarray(d, float), *frame)
            ok = np.isfinite(col).all(axis=1) & (col.max(axis=1) > 0)
            t = np.where(ok, t, 0.0).astype(np.float32)          # where the panorama has nothing, the texel stays
            rgb[ys, xs] = rgb[ys, xs] * (1.0 - t[:, None]) + np.nan_to_num(col).astype(np.float32) * t[:, None]
            return int((t > 0).sum())
        except Exception as e:                                   # noqa: BLE001 - then the mean, as before
            log.warning("station mesh: the panorama's sky was not used (%s: %s) - the far texels' mean instead", type(e).__name__, e)
    gx, gy = np.clip(xs // k, 0, n - 1), np.clip(ys // k, 0, n - 1)
    den = np.maximum(wb[gy, gx], 1e-6)
    for ch in range(3):
        a = cv2.resize(np.where(far, rgb[..., ch], 0.0).astype(np.float32), (n, n), interpolation=cv2.INTER_AREA)
        mean = cv2.GaussianBlur(a, (0, 0), sig)[gy, gx] / den
        rgb[ys, xs, ch] = rgb[ys, xs, ch] * (1.0 - t) + mean * t
    return int(len(ys))


def push_pull(rgb: np.ndarray, have: np.ndarray, region: np.ndarray) -> np.ndarray:
    """The texels of ``region`` that are not ``have`` filled from the ones that are, coarse to fine (a pull-push
    pyramid); ``rgb`` float (H, W, 3) changed in place.  Returns the texels filled."""
    import cv2
    todo = region & ~have
    if not todo.any() or not have.any():
        return np.zeros(have.shape, bool)
    w = have.astype(np.float32)
    a = rgb.astype(np.float32) * w[..., None]
    pyr = [(a, w)]
    while min(pyr[-1][1].shape) > 8:
        a_, w_ = pyr[-1]
        size = (max(1, w_.shape[1] // 2), max(1, w_.shape[0] // 2))
        pyr.append((cv2.resize(a_, size, interpolation=cv2.INTER_AREA), cv2.resize(w_, size, interpolation=cv2.INTER_AREA)))
    a_, w_ = pyr[-1]
    mean = (rgb[have].mean(axis=0) if have.any() else np.zeros(3)).astype(np.float32)
    cur = np.where(w_[..., None] > 1e-6, a_ / np.maximum(w_, 1e-6)[..., None], mean)   # a coarsest cell without data: the mean
    for a_, w_ in reversed(pyr[:-1]):
        up_ = cv2.resize(cur, (w_.shape[1], w_.shape[0]), interpolation=cv2.INTER_LINEAR)
        k = np.clip(w_, 0, 1)[..., None]
        cur = np.where(w_[..., None] > 1e-6, a_ / np.maximum(w_, 1e-6)[..., None], 0) * k + up_ * (1 - k)
    rgb[todo] = cur[todo]
    return todo


def fill_cells(rgb: np.ndarray, have: np.ndarray, cells: Dict[str, Any], default: Sequence[float]) -> int:
    """A cell's texels no frame colored take the mean of its colored ones (``default`` where it has none)."""
    n = 0
    for (x, y), (w, h) in zip(cells["pos"], cells["wh"]):
        sl = (slice(int(y), int(y + h)), slice(int(x), int(x + w)))
        hv = have[sl]
        if hv.all():
            continue
        col = rgb[sl][hv].mean(axis=0) if hv.any() else np.asarray(default, np.float32)
        blk = rgb[sl]
        blk[~hv] = col
        n += int((~hv).sum())
    return n


GROW_COLORS = True              # 1.0.5: a cell's texels no frame colored take colors grown in from the patch's seen edges


def _bilinear(rgb: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """``rgb`` (H, W, 3) at the texel coordinates (x, y) of texel centers (x + 0.5 is a center), bilinear."""
    H, W = rgb.shape[:2]
    x = np.clip(np.asarray(x, float) - 0.5, 0, W - 1.001)
    y = np.clip(np.asarray(y, float) - 0.5, 0, H - 1.001)
    x0, y0 = x.astype(np.int64), y.astype(np.int64)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    return ((1 - fy) * ((1 - fx) * rgb[y0, x0] + fx * rgb[y0, x0 + 1])
            + fy * ((1 - fx) * rgb[y0 + 1, x0] + fx * rgb[y0 + 1, x0 + 1]))


def grown_vertex_colors(F: np.ndarray, vis: np.ndarray, color: np.ndarray, default: Sequence[float]) -> np.ndarray:
    """Colors (n, 3) for all the vertices: ``color`` at the vertices of the visible triangles (``vis``), and over the
    hidden triangles' other vertices the harmonic interpolation of those - every free vertex the mean of its
    neighbors along the hidden triangles' edges.  A patch that touches no visible triangle takes ``default``."""
    from scipy.sparse import coo_matrix, identity
    from scipy.sparse.linalg import spsolve
    n = len(color)
    out = np.asarray(color, np.float64).copy()
    fixed = np.zeros(n, bool)
    fixed[np.unique(F[vis])] = True
    Fh = F[~vis]
    free = np.unique(Fh)
    free = free[~fixed[free]]
    if not len(free):
        return out
    idx = np.full(n, -1, np.int64)
    idx[free] = np.arange(len(free))
    E = np.concatenate([Fh[:, [0, 1]], Fh[:, [1, 2]], Fh[:, [2, 0]]]).astype(np.int64)
    ke = np.unique(np.concatenate([E[:, 0] * np.int64(n) + E[:, 1], E[:, 1] * np.int64(n) + E[:, 0]]))    # each neighbor once
    E = np.stack([ke // n, ke % n], axis=1)
    E = E[idx[E[:, 0]] >= 0]
    to_free = idx[E[:, 1]] >= 0
    m = len(free)
    eps = 1e-4                                                  # a weak pull to the default: an island has a solution
    deg = np.bincount(idx[E[:, 0]], minlength=m).astype(np.float64)
    A = (coo_matrix((np.r_[deg, -np.ones(int(to_free.sum()))],
                     (np.r_[np.arange(m), idx[E[to_free, 0]]], np.r_[np.arange(m), idx[E[to_free, 1]]])), shape=(m, m)).tocsc()
         + eps * identity(m, format="csc"))
    b = eps * np.tile(np.asarray(default, np.float64), (m, 1))
    np.add.at(b, idx[E[~to_free, 0]], out[E[~to_free, 1]])
    out[free] = np.stack([spsolve(A, b[:, k]) for k in range(3)], axis=1)
    return out


def grow_cells(rgb: np.ndarray, have: np.ndarray, cells: Dict[str, Any], corner_colors: np.ndarray) -> int:
    """1.0.5 (Christian, 21 Nov 2026, Van Zyl: flat, jagged shards on the ground behind rocks): a cell's texels no
    frame colored take the color interpolated between its triangle's corners (``corner_colors`` (m, 3, 3), from
    :func:`grown_vertex_colors`), not one flat color per cell - neighboring hidden triangles then agree along their
    shared edges and with the seen surface around the patch.  Returns the texels colored."""
    n = 0
    size = rgb.shape[0]
    for k, ((x, y), (w, h)) in enumerate(zip(cells["pos"], cells["wh"])):
        sl = (slice(int(y), int(y + h)), slice(int(x), int(x + w)))
        hv = have[sl]
        if hv.all():
            continue
        p = cells["uv"][k] * size                               # the corners in texels
        d = (p[1, 1] - p[2, 1]) * (p[0, 0] - p[2, 0]) + (p[2, 0] - p[1, 0]) * (p[0, 1] - p[2, 1])
        yy, xx = np.nonzero(~hv)
        if abs(d) < 1e-9:
            col = corner_colors[k].mean(axis=0)[None]
        else:
            px, py = xx + int(x) + 0.5, yy + int(y) + 0.5
            w0 = ((p[1, 1] - p[2, 1]) * (px - p[2, 0]) + (p[2, 0] - p[1, 0]) * (py - p[2, 1])) / d
            w1 = ((p[2, 1] - p[0, 1]) * (px - p[2, 0]) + (p[0, 0] - p[2, 0]) * (py - p[2, 1])) / d
            wgt = np.clip(np.stack([w0, w1, 1.0 - w0 - w1], 1), 0.0, 1.0)      # the gutter: the nearest of the triangle
            wgt /= np.maximum(wgt.sum(1), 1e-9)[:, None]
            col = wgt @ corner_colors[k]
        blk = rgb[sl]
        blk[yy, xx] = col.astype(rgb.dtype)
        n += len(yy)
    return n


# ------------------------------------------------------------------------------------------- charts (1.0)
def _adjacency(F: np.ndarray, V: np.ndarray, weld_m: float = WELD_M) -> List[List[int]]:
    """For each triangle, the triangles that share an edge with it (vertices within ``weld_m`` are one)."""
    q = np.round(np.asarray(V, float) / weld_m).astype(np.int64)
    _, wid = np.unique(q, axis=0, return_inverse=True)
    Fw = wid.reshape(-1)[F]
    e = np.concatenate([Fw[:, [0, 1]], Fw[:, [1, 2]], Fw[:, [2, 0]]])
    e.sort(axis=1)
    tri = np.tile(np.arange(len(F)), 3)
    key = e[:, 0] * (int(Fw.max()) + 1) + e[:, 1]
    o = np.argsort(key, kind="stable")
    key, tri = key[o], tri[o]
    adj: List[List[int]] = [[] for _ in range(len(F))]
    cut = np.flatnonzero(np.diff(key)) + 1
    for grp in np.split(tri, cut):
        if 2 <= len(grp) <= 4:                                  # an edge of two (a seam of a few, at most)
            for i in grp:
                adj[int(i)].extend(int(j) for j in grp if j != i)
    return adj


def _clean_normals(normals: np.ndarray) -> np.ndarray:
    """1.0 (Van Zyl, 20 Nov 2026: "the station mesh's part was not made (OverflowError: int too big to convert)"): a
    triangle of no area has no normal (0 or NaN) - it takes +z, so its chart's size is not NaN."""
    nk = np.nan_to_num(np.asarray(normals, float), nan=0.0, posinf=0.0, neginf=0.0)
    bad = np.linalg.norm(nk, axis=1) < 1e-12
    if bad.any():
        nk = nk.copy()
        nk[bad] = (0.0, 0.0, 1.0)
    return nk


def _plane_basis(n: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    n = np.nan_to_num(np.asarray(n, float))
    if float(np.linalg.norm(n)) < 1e-12:
        n = np.array([0.0, 0.0, 1.0])
    a = np.asarray(n, float) / max(float(np.linalg.norm(n)), 1e-15)
    h = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(a, h)
    u /= np.linalg.norm(u)
    return u, np.cross(a, u)


def triangle_charts(V: np.ndarray, F: np.ndarray, normals: np.ndarray, areas: np.ndarray, max_deg: float = CHART_MAX_DEG,
                    max_m: float = CHART_MAX_M) -> List[Dict[str, Any]]:
    """Charts of triangles: grown from the largest triangle not yet in one, over shared edges, while a triangle faces
    within ``max_deg`` of the first one's ``normals`` (the side that is seen) and the chart, projected along that
    normal, stays within ``max_m``.  Each chart: {"tris" (list), "axis" (3,), "u", "v" (its plane's axes, the longer
    side along u)}.  A chart that folds over itself in projection (its triangles cover more than its outline) is
    split into one chart per triangle."""
    from collections import deque
    import cv2
    m = len(F)
    if m == 0:
        return []
    VF = np.asarray(V, float)[np.asarray(F)]                     # (m, 3, 3)
    nk = _clean_normals(normals)
    adj = _adjacency(np.asarray(F), V)
    cosmax = float(np.cos(np.radians(max_deg)))
    owner = np.full(m, -1, np.int64)
    charts: List[Dict[str, Any]] = []
    for s in np.argsort(-np.asarray(areas), kind="stable"):
        s = int(s)
        if owner[s] >= 0:
            continue
        ax = nk[s] / max(float(np.linalg.norm(nk[s])), 1e-15)
        u, v = _plane_basis(ax)
        P = VF[s]
        lo = np.array([float((P @ u).min()), float((P @ v).min())])
        hi = np.array([float((P @ u).max()), float((P @ v).max())])
        cid = len(charts)
        owner[s] = cid
        tris = [s]
        todo = deque([s])
        while todo:
            t_ = todo.popleft()
            for nb in adj[t_]:
                if owner[nb] >= 0 or float(nk[nb] @ ax) < cosmax:
                    continue
                Q = VF[nb]
                qu, qv = Q @ u, Q @ v
                nlo = np.minimum(lo, (qu.min(), qv.min()))
                nhi = np.maximum(hi, (qu.max(), qv.max()))
                if float((nhi - nlo).max()) > max_m:
                    continue
                lo, hi = nlo, nhi
                owner[nb] = cid
                tris.append(nb)
                todo.append(nb)
        charts.append({"tris": tris, "axis": ax, "u": u, "v": v})
    out: List[Dict[str, Any]] = []
    for c in charts:
        tris = np.asarray(c["tris"])
        P2 = np.stack([VF[tris] @ c["u"], VF[tris] @ c["v"]], axis=-1)        # (k, 3, 2)
        if len(tris) >= 3:                                                   # the longer side along u
            X = P2.reshape(-1, 2) - P2.reshape(-1, 2).mean(axis=0)
            w_, vec = np.linalg.eigh(X.T @ X)
            d = vec[:, int(np.argmax(w_))]
            u2 = d[0] * c["u"] + d[1] * c["v"]
            c["u"], c["v"] = u2, np.cross(c["axis"], u2)
            P2 = np.stack([VF[tris] @ c["u"], VF[tris] @ c["v"]], axis=-1)
            lo2 = P2.reshape(-1, 2).min(axis=0)
            ext = float((P2.reshape(-1, 2).max(axis=0) - lo2).max())
            px = max(ext / 256.0, 1e-6)
            sz = (np.ceil((P2.reshape(-1, 2).max(axis=0) - lo2) / px).astype(int) + 3)
            img = np.zeros((int(sz[1]), int(sz[0])), np.uint8)
            pts = [np.round(((p - lo2) / px + 1.0) * 16).astype(np.int32) for p in P2]
            cv2.fillPoly(img, pts, 1, shift=4)
            e1, e2 = P2[:, 1] - P2[:, 0], P2[:, 2] - P2[:, 0]
            proj = float(np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum() / 2.0) / (px * px)
            if proj > (1.0 + CHART_OVERLAP_TOL) * float(img.sum()) + 4.0:       # folds over itself: one chart per triangle
                for t_ in tris:
                    u_, v_ = _plane_basis(nk[t_])
                    out.append({"tris": [int(t_)], "axis": nk[t_] / max(float(np.linalg.norm(nk[t_])), 1e-15), "u": u_, "v": v_})
                continue
        out.append(c)
    return out


def layout_charts(V: np.ndarray, F: np.ndarray, normals: np.ndarray, areas: np.ndarray, size: int,
                  reserved: Sequence[Tuple[int, int, int, int]] = (), fill: float = 0.8,
                  max_deg: float = CHART_MAX_DEG, max_m: float = CHART_MAX_M) -> Dict[str, Any]:
    """The triangles of (V, F) in charts (:func:`triangle_charts`), packed into a ``size`` square at the finest texel
    size that fits: {"pos", "wh" (the charts' rectangles), "s" (texel m per chart), "texel_m", "uv" (m, 3, 2),
    "tri_A" (m, 3, 3: a texel center (x + 0.5, y + 0.5, 1) -> the point on the triangle's own plane under it),
    "tri_map" (size, size) int32 (the triangle each texel of a chart's rectangle takes its point from: the one it is in,
    else the nearest; -1 outside the charts), "charts" (the number), "chart_of" (m,)}."""
    import cv2
    m = len(F)
    empty = {"pos": np.zeros((0, 2), np.int64), "wh": np.zeros((0, 2), np.int64), "s": np.zeros(0), "texel_m": None,
             "uv": np.zeros((0, 3, 2)), "tri_A": np.zeros((0, 3, 3)), "tri_map": None, "charts": 0,
             "chart_of": np.zeros(0, np.int64), "A": np.zeros((0, 3, 3))}
    if m == 0:
        return empty
    VF = np.asarray(V, float)[np.asarray(F)]
    nk = _clean_normals(normals)
    areas = np.nan_to_num(np.asarray(areas, float))
    charts = triangle_charts(V, F, nk, areas, max_deg, max_m)
    P2, lo, ext = [], [], []
    for c in charts:
        p = np.stack([VF[c["tris"]] @ c["u"], VF[c["tris"]] @ c["v"]], axis=-1)
        P2.append(p)
        lo.append(p.reshape(-1, 2).min(axis=0))
        ext.append(p.reshape(-1, 2).max(axis=0) - lo[-1])
    lo, ext = np.nan_to_num(np.asarray(lo)), np.nan_to_num(np.asarray(ext), nan=0.0, posinf=0.0, neginf=0.0)
    g = GUTTER_PX * max(1, int(size) // ROVER_GLB_PX)            # 1.0.1: GUTTER_PX texels are left in the reduced .glb texture
    mcp = MAX_CHART_PX * max(1, int(size) // ROVER_GLB_PX)
    free = size * size - sum(r[2] * r[3] for r in reserved)
    t = float(np.sqrt(max(1.3 * float((ext[:, 0] * ext[:, 1]).sum()), 1e-12) / max(fill * free, 1.0)))
    for _ in range(80):
        s = np.full(len(charts), t)
        big = ext.max(axis=1) / s > (mcp - 2 * g)
        s[big] = ext[big].max(axis=1) / (mcp - 2 * g)
        wh = np.ceil(ext / s[:, None]).astype(np.int64) + 1 + 2 * g
        pos = shelf_pack(wh, size, None, reserved)
        if pos is not None:
            break
        t *= 1.08
    else:
        raise RuntimeError("station mesh: the charts do not fit the texture")
    uv = np.zeros((m, 3, 2))
    tri_A = np.zeros((m, 3, 3))
    chart_of = np.zeros(m, np.int64)
    tri_map = np.full((size, size), -1, np.int32)
    for ci, c in enumerate(charts):
        tris = np.asarray(c["tris"])
        chart_of[tris] = ci
        ox = float(pos[ci, 0]) + g - lo[ci, 0] / s[ci]
        oy = float(pos[ci, 1]) + g - lo[ci, 1] / s[ci]
        px = ox + P2[ci][..., 0] / s[ci]
        py = oy + P2[ci][..., 1] / s[ci]
        uv[tris] = np.stack([px / size, py / size], axis=-1)
        a, u, v = c["axis"], c["u"], c["v"]
        n = nk[tris] / np.maximum(np.linalg.norm(nk[tris], axis=1), 1e-15)[:, None]
        an = np.maximum(n @ a, 1e-6)
        k0 = (VF[tris, 0] * n).sum(1) / an
        ku, kv = (n @ u) / an, (n @ v) / an
        Eu = u[None, :] - a[None, :] * ku[:, None]
        Ev = v[None, :] - a[None, :] * kv[:, None]
        tri_A[tris, :, 0] = s[ci] * Eu
        tri_A[tris, :, 1] = s[ci] * Ev
        tri_A[tris, :, 2] = -ox * s[ci] * Eu - oy * s[ci] * Ev + a[None, :] * k0[:, None]
        x0, y0 = int(pos[ci, 0]), int(pos[ci, 1])
        w, h = int(wh[ci, 0]), int(wh[ci, 1])
        sub = np.full((h, w), -1.0, np.float32)
        for j, tt in enumerate(tris):                            # cv2 pixel centers are at whole numbers
            pts = np.stack([px[j] - x0 - 0.5, py[j] - y0 - 0.5], axis=1)
            cv2.fillPoly(sub, [np.round(pts * 16).astype(np.int32)], float(tt), shift=4)
        empty_ = sub < 0
        if empty_.all():                                         # a sliver smaller than a texel: its first corner's
            cx = int(np.clip(np.floor(px[0, 0] - x0), 0, w - 1))  # texel stands for it
            cy = int(np.clip(np.floor(py[0, 0] - y0), 0, h - 1))
            sub[cy, cx] = float(tris[0])
            empty_ = sub < 0
        if empty_.any():                                         # the gutter and the gaps: the nearest triangle's
            _, lab = cv2.distanceTransformWithLabels(empty_.astype(np.uint8), cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL)
            lut = np.full(int(lab.max()) + 1, -1.0, np.float32)
            lut[lab[~empty_]] = sub[~empty_]
            sub = lut[lab]
        tri_map[y0:y0 + h, x0:x0 + w] = sub.astype(np.int32)
    return {"pos": pos, "wh": wh, "s": s, "texel_m": float(t), "uv": uv, "tri_A": tri_A, "tri_map": tri_map,
            "charts": len(charts), "chart_of": chart_of, "A": np.zeros((0, 3, 3))}


def fill_charts(rgb: np.ndarray, have: np.ndarray, cells: Dict[str, Any], default: Sequence[float]) -> int:
    """A chart's texels no frame colored are filled from its colored ones (pull-push within the chart's rectangle;
    ``default`` where it has none)."""
    n = 0
    for (x, y), (w, h) in zip(cells["pos"], cells["wh"]):
        sl = (slice(int(y), int(y + h)), slice(int(x), int(x + w)))
        hv = have[sl]
        if hv.all():
            continue
        blk = rgb[sl]
        if hv.any():
            n += int(push_pull(blk, hv, np.ones(hv.shape, bool)).sum())
        else:
            blk[...] = np.asarray(default, np.float32)
            n += int(hv.size)
    return n


# ------------------------------------------------------------------------------------------- to the horizon (0.99.32)
def horizon_shell(scene, C, pivot, up, north, east, from_m: float = SHELL_FROM_M, az_step_deg: float = SHELL_AZ_STEP_DEG,
                  step_deg: float = SHELL_STEP_DEG, sky_rings: int = SHELL_SKY_RINGS, dome_m: float = DOME_M,
                  margin_deg: float = SKYLINE_MARGIN_DEG, near=None) -> Dict[str, Any]:
    """The surface seen from C beyond the near terrain, as one sheet: on rings of equal angle from straight down, a
    vertex per ``az_step_deg`` where its ray from C meets the scene (the mesh, the ground plane, the far surface -
    the sky sphere or the far field, which also carries the sky) or, where it meets nothing, at ``dome_m``.  The
    rings run from the angle of ``from_m`` on the ground up to the map's knee (the highest ray that meets the mesh
    or the plane plus ``margin_deg``, at least ``SKYLINE_MIN_DEG`` above the horizontal) every ``step_deg``, then
    ``sky_rings`` more to the zenith.  Seen from C the sheet has no fold; its parallax for a head off C is the true one out to the far
    field and none on the sky.  Returns {"V" (n, 3), "F" (m, 3) - the outer rings first, so a viewer that draws them
    in order without a depth buffer draws the near ones over the far ones -, "knee" rad, "theta0" rad, "rings", "az"}.

    ``near`` (1.0.5) = (a raycaster of the near terrain AS IT IS DRAWN, its radius about the mast axis): the scene's
    mesh can hold what the drawn terrain does not - a floater that :func:`under_floaters` took out (Wildcat Ridge:
    a sheet 6 m out at the mast's height).  A ray that met it was "near terrain" to the shell, the terrain drew
    nothing there, and the place was black.  With ``near`` a ray is followed to what IS drawn: where it meets the
    scene before the drawn terrain (by more than ``SHELL_NEAR_TOL_M``) the vertex is on the drawn terrain; where it
    meets the scene inside the radius and never the drawn terrain, it is cast again from where it leaves the radius."""
    from .raycast import LABEL_FAR, LABEL_MESH, LABEL_NONE, SKY_RANGE_M
    C, up, north, east = np.asarray(C, float), _unit(up), _unit(north), _unit(east)

    def cast(th, ph):
        s = np.sin(th)
        d = np.cos(th)[:, None] * -up + (s * np.sin(ph))[:, None] * east + (s * np.cos(ph))[:, None] * north
        o = np.broadcast_to(C, d.shape).copy()
        h = scene.cast(o, d)
        t = np.asarray(h["t"], float).copy()
        label = np.asarray(h["label"]).copy()
        if near is not None:                                     # 1.0.5: to what the near terrain draws, or past it
            rc_t, rad = near[0], float(near[1])
            tt, _ = _cast(rc_t, o, d)
            hit = np.isfinite(t) & (label != LABEL_NONE)
            inside = hit & (t * s < rad - 1e-3)                  # (s: the ray's horizontal share - C is on the mast axis)
            before = inside & np.isfinite(tt) & (t < tt - SHELL_NEAR_TOL_M)
            t[before] = tt[before]
            label[before] = LABEL_MESH
            past = inside & ~np.isfinite(tt)
            if past.any():
                out_at = rad / np.maximum(s[past], 1e-9) + 0.01
                h2 = scene.cast(C + d[past] * out_at[:, None], d[past])
                t2 = np.asarray(h2["t"], float)
                t[past] = np.where(np.isfinite(t2), out_at + t2, np.inf)
                label[past] = np.asarray(h2["label"])
        open_ = (label == LABEL_NONE) | ~np.isfinite(t) | (t >= dome_m)             # nothing there: the dome
        return d, np.where(open_, dome_m, t), open_ | (label == LABEL_FAR)         # ..., beyond the mesh and the plane
    _, t_down, _ = cast(np.zeros(1), np.zeros(1))
    h_c = float(t_down[0]) if t_down[0] < dome_m else 2.5
    th0 = max(np.radians(20.0), float(np.arctan2(from_m, h_c)) - np.radians(3.0))
    ph_c = np.radians(np.arange(0.0, 360.0, 1.0))
    # 1.0.5 (Christian, 22 Nov 2026, Skinner Ridge and Wildcat Ridge: "a black semi circle"): the first ring was at
    # the angle of ``from_m`` on LEVEL ground under C, the same for every azimuth.  Where the ground falls away, the
    # surface at that angle is far beyond the near terrain's end (Skinner Ridge, to the south: 32 m at -10 deg, the
    # terrain ends at 20 m) and the band between had no triangle - black in the viewer from east through south to
    # west.  The first ring is now the lowest angle at which any azimuth's ray is ``from_m`` away (the quads nearer
    # than that are left out below, as before)
    th_s = np.arange(np.radians(20.0), th0 + 1e-9, np.radians(0.5))
    if len(th_s):
        TS, PS = np.meshgrid(th_s, ph_c, indexing="ij")
        d_s, t_s, _ = cast(TS.ravel(), PS.ravel())
        Xs = d_s * t_s[:, None]
        hd_s = np.linalg.norm(Xs - (Xs @ up)[:, None] * up, axis=1).reshape(TS.shape)
        reach = (hd_s >= from_m - 1.0) & (t_s.reshape(TS.shape) < dome_m)
        if reach.any():
            th0 = max(np.radians(20.0), float(th_s[np.flatnonzero(reach.any(axis=1)).min()]) - np.radians(1.0))
    th_c = np.arange(th0, np.pi - 1e-6, np.radians(0.25))
    TT, PP = np.meshgrid(th_c, ph_c, indexing="ij")
    _, _, sky_c = cast(TT.ravel(), PP.ravel())
    ground = ~sky_c.reshape(TT.shape)
    top = float(th_c[np.flatnonzero(ground.any(axis=1)).max()]) if ground.any() else np.pi / 2
    knee = float(np.clip(max(top + np.radians(margin_deg), np.pi / 2 + np.radians(SKYLINE_MIN_DEG)), th0 + np.radians(5.0),
                         np.pi - np.radians(20.0)))
    ths = np.r_[np.arange(th0, knee - 1e-9, np.radians(step_deg)), knee, np.linspace(knee, np.pi, int(sky_rings) + 1)[1:]]
    phs = np.radians(np.arange(0.0, 360.0, az_step_deg))
    nr, na = len(ths), len(phs)
    TT, PP = np.meshgrid(ths, phs, indexing="ij")
    d, t, sky_f = cast(TT.ravel(), PP.ravel())
    low = (t >= dome_m) & (TT.ravel() < np.pi / 2 - 1e-3)        # a ray below the horizontal that meets nothing (a gap
    t[low] = np.minimum(dome_m, h_c / np.cos(TT.ravel()[low]))   # in the scene): on the level ground under C, not the sky
    t2, low2 = t.reshape(nr, na), low.reshape(nr, na)            # 1.0.5: ... and not nearer than the ring beneath it -
    for i in range(1, nr):                                       # where the ground falls away, level ground under C is
        t2[i] = np.where(low2[i], np.maximum(t2[i], t2[i - 1]), t2[i])   # nearer than the terrain's end: a gap again
    V = C + d * t[:, None]
    hd = np.linalg.norm((V - np.asarray(pivot, float)) - ((V - np.asarray(pivot, float)) @ up)[:, None] * up, axis=1).reshape(nr, na)
    F = []
    j = np.arange(na)
    j1 = (j + 1) % na
    # 1.0.5: a corner on the far surface or the sky is the shell's however near the mast axis it is (Skinner Ridge: the
    # far surface is 105 m overhead, 15 m from the axis at 82 deg - no sky in a wedge at the zenith)
    beyond = sky_f.reshape(nr, na)
    for i in range(nr - 2, -1, -1):                              # the outer rings first
        a_, b_, c_, d_ = i * na + j, i * na + j1, (i + 1) * na + j1, (i + 1) * na + j
        far = (hd[i, j] >= from_m) | (hd[i, j1] >= from_m) | (hd[i + 1, j] >= from_m) | (hd[i + 1, j1] >= from_m)
        far |= beyond[i, j] | beyond[i, j1] | beyond[i + 1, j] | beyond[i + 1, j1]
        F.append(np.stack([a_[far], b_[far], c_[far]], 1))
        F.append(np.stack([a_[far], c_[far], d_[far]], 1))
    F = np.vstack(F).astype(np.int64)
    used = np.zeros(len(V), bool)
    used[F.ravel()] = True
    remap = np.cumsum(used) - 1
    return {"V": V[used], "F": remap[F], "knee": knee, "theta0": float(th0), "rings": int(nr), "az": int(na)}


# ------------------------------------------------------------------------------------------- 0.99.51: small hidden patches
def hidden_patches(F: np.ndarray, hidden: np.ndarray, area: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """(component label per triangle, -1 where not ``hidden``; the area of each component) - the hidden triangles
    joined across their shared edges."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    h = np.flatnonzero(hidden)
    lab = np.full(len(F), -1, np.int64)
    if len(h) == 0:
        return lab, np.zeros(0)
    Fh = np.asarray(F, np.int64)[h]
    e = np.concatenate([Fh[:, [0, 1]], Fh[:, [1, 2]], Fh[:, [2, 0]]])
    e.sort(axis=1)
    t = np.tile(np.arange(len(h)), 3)
    key = e[:, 0] * (int(e.max()) + 1) + e[:, 1]
    o = np.argsort(key, kind="stable")
    ks, ts = key[o], t[o]
    same = ks[1:] == ks[:-1]
    a, b = ts[:-1][same], ts[1:][same]
    g = coo_matrix((np.ones(len(a)), (a, b)), shape=(len(h), len(h)))
    n, comp = connected_components(g, directed=False)
    lab[h] = comp
    return lab, np.bincount(comp, weights=np.asarray(area, float)[h], minlength=n)


def warp_small_patches(V: np.ndarray, F: np.ndarray, uv: np.ndarray, vis: np.ndarray, area: np.ndarray,
                       max_m2: float = WARP_MAX_M2) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """(uv, vis): the hidden patches smaller than ``max_m2`` that touch seen triangles join the disc - their vertices
    shared with seen triangles keep their texture coordinates, the others are the mean of their neighbors' (the
    harmonic map over the patch, solved at once), so a patch shows the disc's texels between its seen edges with no
    seam.  A patch with no seen neighbor keeps its cells."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import spsolve
    F = np.asarray(F, np.int64)
    lab, areas = hidden_patches(F, ~vis, area)
    rec = {"patches": int(len(areas)), "max_m2": float(max_m2)}
    if not len(areas):
        return uv, vis, dict(rec, warped_patches=0, warped_triangles=0)
    small_c = areas < float(max_m2)
    cand = (lab >= 0) & small_c[np.maximum(lab, 0)]
    on_seen = np.zeros(len(V), bool)
    on_seen[F[vis].ravel()] = True
    touch = np.zeros(len(areas), bool)                          # the patches with a vertex on a seen triangle
    ct = np.flatnonzero(cand)
    touch[np.unique(lab[ct][on_seen[F[ct]].any(axis=1)])] = True
    take = cand & touch[np.maximum(lab, 0)]
    if not take.any():
        return uv, vis, dict(rec, warped_patches=0, warped_triangles=0)
    Ft = F[take]
    verts = np.unique(Ft)
    inner = verts[~on_seen[verts]]
    uv = np.array(uv, float, copy=True)
    if len(inner):
        idx = -np.ones(len(V), np.int64)
        idx[inner] = np.arange(len(inner))
        e = np.concatenate([Ft[:, [0, 1]], Ft[:, [1, 2]], Ft[:, [2, 0]]])
        e = np.unique(np.sort(e, axis=1), axis=0)
        e = np.concatenate([e, e[:, ::-1]])                     # both ways: i's neighbor j
        i_in = idx[e[:, 0]] >= 0
        e = e[i_in]
        deg = np.bincount(idx[e[:, 0]], minlength=len(inner)).astype(float)
        jin = idx[e[:, 1]] >= 0
        rows = np.concatenate([np.arange(len(inner)), idx[e[jin, 0]]])
        cols = np.concatenate([np.arange(len(inner)), idx[e[jin, 1]]])
        vals = np.concatenate([deg, -np.ones(int(jin.sum()))])
        A = coo_matrix((vals, (rows, cols)), shape=(len(inner), len(inner))).tocsr()
        b = np.zeros((len(inner), 2))
        np.add.at(b, idx[e[~jin, 0]], uv[e[~jin, 1]])
        ok = deg > 0
        sol = np.column_stack([spsolve(A, b[:, k]) for k in range(2)]) if len(inner) > 1 else b / np.maximum(deg, 1)[:, None]
        sol = np.asarray(sol, float).reshape(len(inner), 2)
        good = ok & np.isfinite(sol).all(axis=1)
        uv[inner[good]] = sol[good]
    vis2 = vis | take
    return uv, vis2, dict(rec, warped_patches=int(np.unique(lab[take]).size), warped_triangles=int(take.sum()),
                          warped_m2=round(float(area[take].sum()), 4), inner_vertices=int(len(inner)))


def border_fill(rgb: np.ndarray, used: np.ndarray, border_px: int = BORDER_PX) -> Tuple[np.ndarray, int]:
    """0.99.51: the texels within ``border_px`` of the ``used`` ones (the disc and the cells) take the colors about
    them (:func:`push_pull`) - JPEG and the viewer's mipmaps blur into the surroundings' own colors, not white or
    black.  Returns (the texels farther out - the fifth mode's white; the texels filled)."""
    import cv2
    k = 2 * int(border_px) + 1
    near = cv2.dilate(used.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))).astype(bool)
    band = near & ~used
    filled = push_pull(rgb, used, band)
    return ~near, int(filled.sum())


# ------------------------------------------------------------------------------------------- the two parts
def terrain_part(scene, sources, station, pool=None, size: int = TEXTURE_PX, radius_m: float = RADIUS_M,
                 center_above_m: float = CENTER_ABOVE_M, target: int = TARGET_TRIANGLES, linear: bool = False,
                 rows_per_chunk: int = 128, full: bool = False, sky_pano=None) -> Dict[str, Any]:
    """The terrain mesh and its texture (see the module): {"V" block (n, 3), "F", "uv" (n, 2), "texture" (S, S, 3)
    float or uint8 as the sources, "record"}.

    ``full`` (0.99.32, the fifth mode): the texture's disc is the whole view from C - the angles up to the skyline on
    ``HORIZON_FRAC`` of its radius, the sky to the zenith on the rest - and the part also holds "shell", the surface
    from ``SHELL_FROM_M`` to the far field and the sky (:func:`horizon_shell`: {"V", "F", "uv"}), on the same texture."""
    t0 = time.time()
    P, up, north, east = (np.asarray(x, float) for x in (station.pivot, station.up, station.north, station.east))
    up = _unit(up)
    ceiling = ceiling_key = None
    if SKY_CEILING and sky_pano is not None:                    # 1.0.6: held under the mast's skyline
        try:
            sk = pano_skyline(sky_pano[0])
            if sk is not None:
                ceiling = SkyCeiling(sk, float(sky_pano[1]), P, up, north, east)
                ceiling_key = ("sky", round(float(np.sum(sk)), 3), float(sky_pano[1]))
        except Exception as e:                                  # noqa: BLE001 - the terrain as the mesh has it
            log.warning("station mesh: no skyline from the panorama (%s) - the terrain is not held under it", e)
    V, F, rec = terrain_mesh(scene, P, up, radius_m, target, ceiling=ceiling, ceiling_key=ceiling_key)
    C = P + float(center_above_m) * up
    nrm, area = triangle_normals(V, F)
    rc = _raycaster(V, F)
    pts = test_points(V, F)
    seen = np.ones(len(F), bool)
    for j in range(pts.shape[1]):
        seen &= seen_from(rc, pts[:, j], C)
    view = pts[:, 0] - C
    view /= np.maximum(np.linalg.norm(view, axis=1), 1e-12)[:, None]
    grazing = np.abs((nrm * view).sum(1)) < GRAZING_COS
    from .mesh import horizontal_distance
    # 1.0.2 (Christian, 21 Nov 2026, Van Zyl: "the mesh still has a hole in front of the rover"; "here is the mesh
    # discontinuity" - gray slivers along the outline of the patch under the rover): the mesh's sheets are not sewn
    # where the fill meets the measured ground, and through the cracks one saw the sheet beneath - hidden from C, so
    # textured from a cell, in a fill's tone (within 6 m of Van Zyl's mast 119 m2 of level ground was in cells).  A
    # hidden triangle that lies right under another sheet takes the disc like the sheet above it: seen through a
    # crack it shows the picture that belongs there
    under = np.ones(len(F), bool)
    for j in range(pts.shape[1]):
        under &= under_a_sheet(rc, pts[:, j], up)
    under &= ~seen
    if rec.get("top_sheet"):                                    # 1.0.5: one sheet has nothing beneath it - what is
        under[:] = False                                        # hidden there is a rock's far side, not a crack
    vis = (seen & ~grazing) | (under & ~grazing) | (horizontal_distance(pts[:, 0], P, up) > CELL_RADIUS_M)
    used = np.unique(F[vis])
    th = np.arccos(np.clip(((V[used] - C) / np.linalg.norm(V[used] - C, axis=1)[:, None]) @ -up, -1, 1))
    theta_max = float(min(np.pi * 0.995, th.max() + np.radians(0.5)))
    shell = knee = None
    if full:
        shell = horizon_shell(scene, C, P, up, north, east, near=(rc, float(radius_m)))
        knee = (max(shell["knee"], theta_max), HORIZON_FRAC)
        theta_max = float(np.pi)
    rpx = size / 2.0 - GUTTER_PX - 2
    disc = (size / 2.0, rpx + GUTTER_PX + 3)
    if float((nrm * area[:, None]).sum(0) @ up) < 0:            # the winding's normals point down: turned up (rays
        nrm = -nrm                                              # start above the surface)
    uv_v = disc_uv(V, C, size, rpx, theta_max, up, north, east, knee=knee)
    uv_v, vis, warp = warp_small_patches(V, F, uv_v, vis, area)  # 0.99.51: small hidden patches keep the disc
    # 1.0.5: the cells have to fit beside the disc.  A site of many rocks has more hidden triangles than the corners
    # hold (each cell has its gutter): then only those nearer the mast get cells, the others the disc's picture
    rh = horizontal_distance(pts[:, 0], P, up)
    cell_radius = CELL_RADIUS_M
    for cell_radius in (CELL_RADIUS_M, 7.5, 5.0, 3.5, 2.5, 0.0):
        v2 = vis | (rh > cell_radius)
        hid = np.flatnonzero(~v2)
        nh = nrm[hid].copy()
        lay = triangle_layout(V, F[hid], nh)
        try:
            cells = layout_cells(lay, area[hid], size, disc=disc)
        except RuntimeError:
            if cell_radius == 0.0:
                raise
            continue
        vis = v2
        break
    if cell_radius < CELL_RADIUS_M:
        log.info("station mesh: the hidden triangles' cells fit only within %.1f m of the mast axis (%d cells)", cell_radius, len(hid))
    args = {"size": size, "linear": linear, "up": tuple(up), "offset_m": TERRAIN_OFFSET_M,
            "disc": {"C": tuple(C), "rpx": rpx, "theta_max": theta_max, "up": tuple(up), "north": tuple(north), "east": tuple(east),
                     "knee": knee},
            "all_cells": cells, "normals": nh, "want_sky": bool(full)}
    tex = render_texture(scene, sources, args, pool, rows_per_chunk)
    rgb, have = np.asarray(tex.pop("rgb"), np.float32), tex.pop("source") >= 0
    sky = tex.pop("sky", None)
    ax = (np.arange(size, dtype=np.float32) + 0.5 - size / 2.0) ** 2
    in_disc = (ax[None, :] + ax[:, None]) <= np.float32((rpx + GUTTER_PX) ** 2)
    del ax
    seen_disc = in_disc & have
    if full and sky is not None and (sky & have & in_disc).any():
        # the sky's unseen texels from the seen sky, the ground's from the ground: no terrain color runs up the sky
        ground = in_disc & ~sky
        filled = push_pull(rgb, have & ground, ground)
        filled |= push_pull(rgb, have & sky & in_disc, sky & in_disc)
        del ground
    else:
        filled = push_pull(rgb, have & in_disc, in_disc)
    sky_white = None
    sky_smoothed = 0
    if full and SKY_IMAGED and sky is not None:                  # 1.0.1: the panorama's own sky, smoothed above the skyline
        sky_smoothed = smooth_sky(rgb, sky & in_disc, size, rpx, knee, pano=sky_pano, frame=(up, north, east))
    elif full and SKY_WHITE and sky is not None:                 # 0.99.41: the sky white
        sky_white = sky_texels(rgb, sky & in_disc, have, in_disc, size, rpx, knee)
    sky = None
    med = np.median(rgb[seen_disc][::97], axis=0) if seen_disc.any() else np.full(3, 128.0)
    cell_grown = 0
    if GROW_COLORS and len(hid):
        try:                                                    # 1.0.5: colors grown in from the patch's seen edges
            vcol = grown_vertex_colors(F, vis, _bilinear(rgb, uv_v[:, 0] * size, uv_v[:, 1] * size), med)
            cell_grown = grow_cells(rgb, have, cells, vcol[F[hid]])
        except Exception as e:                                  # noqa: BLE001 - the flat fill below
            log.warning("station mesh: growing the hidden cells' colors failed (%s) - they take one color each", e)
    cell_filled = cell_grown or fill_cells(rgb, have, cells, med)
    used = in_disc.copy()                                        # 0.99.51: a band about the disc and the cells takes
    for (x, y), (w, h) in zip(cells["pos"], cells["wh"]):        # their colors; beyond it, the fifth mode's white
        used[int(y):int(y + h), int(x):int(x + w)] = True
    far_out, border_filled = border_fill(rgb, used)
    del used
    white = None
    if full and SKY_WHITE:                                       # 0.99.41: what no triangle uses, and the sky
        white = far_out
        if sky_white is not None:
            white |= sky_white
    del far_out, sky_white
    # the mesh: the disc's triangles share their vertices (0.99.51: the small hidden patches' too, warped); a cell's
    # triangle has its own three
    Fv = F[vis]
    nv = len(V)
    Vo = np.concatenate([V, V[F[hid]].reshape(-1, 3)])
    UVo = np.concatenate([uv_v, cells["uv"].reshape(-1, 2)])
    Fo = np.concatenate([Fv, nv + np.arange(3 * len(hid)).reshape(-1, 3)])
    keep = np.zeros(len(Vo), bool)
    keep[Fo.ravel()] = True
    remap = np.cumsum(keep) - 1
    n_disc_texels = int(in_disc.sum())
    rec.update(texture_px=size, center_above_pivot_m=float(center_above_m), theta_max_deg=round(float(np.degrees(theta_max)), 2),
               triangles_from_center=int(vis.sum()), triangles_in_cells=int(len(hid)),
               hidden_from_center=int((~seen).sum()), edge_on_from_center=int((seen & grazing).sum()),
               under_a_sheet=int(under.sum()), cell_radius_m=float(cell_radius),
               cell_texel_mm=None if cells["texel_m"] is None else round(1000 * cells["texel_m"], 2),
               disc_texels_colored=round(float(seen_disc.sum() / max(n_disc_texels, 1)), 4),
               disc_texels_filled=int(filled.sum()), cell_texels_filled=int(cell_filled),
               cell_fill="grown in from the patch's seen edges" if cell_grown else "one color per cell",
               border_texels_filled=int(border_filled), warped=warp,
               mrad_per_texel=round(1000 * (knee[0] / (knee[1] * rpx) if knee else theta_max / rpx), 4))
    out_shell = None
    if shell is not None:
        out_shell = {"V": shell["V"], "F": shell["F"], "uv": disc_uv(shell["V"], C, size, rpx, theta_max, up, north, east, knee=knee)}
        rec.update(full=True, skyline_deg=round(float(np.degrees(knee[0])) - 90.0, 2), horizon_frac=HORIZON_FRAC,
                   texels_per_deg=round(float(knee[1] * rpx / np.degrees(knee[0])), 1),
                   texels_per_deg_around_horizon=round(float(2 * np.pi * knee[1] * rpx * (np.pi / 2 / knee[0]) / 360.0), 1),
                   shell={"triangles": int(len(shell["F"])), "from_m": SHELL_FROM_M, "rings": shell["rings"], "az": shell["az"],
                          "dome_m": DOME_M}, fade_m=list(FADE_M))
    rec["seconds"] = round(time.time() - t0, 1)
    log.info("station mesh: terrain %d triangles (%d from the center, %d in cells at %s mm), texture %d px, %.1f %% of the "
             "disc colored by the frames (%.0f s)", len(Fo), int(vis.sum()), len(hid), rec["cell_texel_mm"], size,
             100 * rec["disc_texels_colored"], rec["seconds"])
    if white is not None:
        rec.update(white_texels=int(white.sum()))
    if sky_smoothed:
        rec.update(sky=("as imaged below the skyline's circle; above it the panorama's sky" if sky_pano is not None else
                        "as imaged; the far texels above the skyline's circle smoothed"), sky_texels_smoothed=int(sky_smoothed))
    return {"V": Vo[keep], "F": remap[Fo], "uv": UVo[keep], "texture": rgb, "record": rec, "shell": out_shell, "white": white}


def viewpoints(pivot, radius_m: float = VIEW_RADIUS_M, n: int = VIEWPOINTS) -> np.ndarray:
    """The pivot and ``n`` points on spheres of half ``radius_m`` and ``radius_m`` about it (a Fibonacci sphere)."""
    k = np.arange(n) + 0.5
    z = 1 - 2 * k / n
    ph = np.pi * (1 + 5 ** 0.5) * k
    r = np.sqrt(1 - z * z)
    d = np.stack([r * np.cos(ph), r * np.sin(ph), z], axis=1)
    P = np.asarray(pivot, float)
    return np.concatenate([P[None], P + 0.5 * radius_m * d, P + radius_m * d])


def rover_families(sources) -> str:
    """The frames that color the rover: the Navcams.  0.99.27-0.99.45: and a Mastcam-Z run's own frames first.
    0.99.46 (Christian, 19 Nov 2026: "the rover texture should come from the ncam images unless and there is a dedicated
    zcam deck pan in stereo"): the run's own other cameras only for the sources marked as a deck pan - none are, unless
    the run is given ``--rover-zcam`` (rpp ods; then its Mastcam-Z frames color the rover, the Navcam ones where they do
    not see it); a source with ``no_rover`` never does."""
    own = "".join(sorted({s.name[:1] for s in sources if not getattr(s, "fill_only", False) and s.name
                          and not getattr(s, "no_rover", False)}))
    return ROVER_FAMILIES + "".join(f for f in own if f not in ROVER_FAMILIES and f != "F" and f != "R")


ROVER_UNMASKED_PASS = True      # 1.0.5: the rover's texels no frame colored, colored again without the rover masks


def rover_sources(sources, families: str) -> List[Any]:
    """1.0.5: the frames that may color the rover model: of ``families``, the station's own (not a context frame,
    not a fill-only one, not one marked ``no_rover``)."""
    return [s for s in sources if s.name[:1] in families and not (getattr(s, "context", False)
            or getattr(s, "no_rover", False) or getattr(s, "fill_only", False))]


def rover_part(scene, sources, station, pool=None, size: int = ROVER_TEXTURE_PX, view_radius_m: float = VIEW_RADIUS_M,
               families: Optional[str] = None, linear: bool = False, rows_per_chunk: int = 128) -> Dict[str, Any]:
    """The rover model and its texture (see the module): {"V", "F", "uv", "texture", "record"}.  ``families``: the
    frames that color it (default :func:`rover_families`)."""
    t0 = time.time()
    if families is None:
        families = rover_families(sources)
    rt = getattr(scene, "rover_triangles", None)
    if rt is None:
        raise ValueError("station mesh: the scene holds no rover model (rpp mesh --rover)")
    up = _unit(station.up)
    Fall = np.asarray(scene.mesh_F, np.int64)[rt[0]:rt[1]]
    used = np.unique(Fall)
    remap = -np.ones(len(scene.mesh_V), np.int64)
    remap[used] = np.arange(len(used))
    V, F = np.asarray(scene.mesh_V, float)[used], remap[Fall]
    nrm, area = triangle_normals(V, F)
    rc_all = _raycaster(np.asarray(scene.mesh_V, float), np.asarray(scene.mesh_F, np.int64))   # terrain and rover
    rc_rov = _raycaster(V, F)
    vps = viewpoints(station.pivot, view_radius_m)
    axes = np.concatenate([np.eye(3), -np.eye(3)])
    good = []
    for vp in vps:                                              # a viewpoint inside the model sees its inside
        t, _ = _cast(rc_rov, vp, axes)
        if int(np.isfinite(t).sum()) < INSIDE_HITS:
            good.append(vp)
    good = np.asarray(good)
    pts = test_points(V, F)
    seen = np.zeros(len(F), bool)
    side = np.zeros(len(F))
    for vp in good:
        for j in range(pts.shape[1]):
            s = seen_from(rc_all, pts[:, j], vp)
            side[s] += np.sign(((vp - pts[s, j]) * nrm[s]).sum(1))
            seen |= s
    # 1.0.5 (Christian, 22 Nov 2026: the rover model has more gray surfaces than it should - "Texture every
    # surface that the ncams see"): a triangle a frame of the station sees - in the frame, nothing of the mesh
    # between - is textured too, wherever the viewer may stand
    seen_vp = seen.copy()
    cam_srcs = rover_sources(sources, families)
    cam = np.zeros(len(F), bool)
    for src in cam_srcs:
        for j in range(pts.shape[1]):
            _, z, inside = src.project(pts[:, j])
            q = np.flatnonzero(inside)
            if not len(q):
                continue
            v = seen_from(rc_all, pts[q, j], src.C)
            q = q[v]
            cam[q] = True
            side[q] += np.sign(((src.C - pts[q, j]) * nrm[q]).sum(1))
    seen = seen_vp | cam
    k = np.flatnonzero(seen)
    nk = nrm[k] * np.where(side[k] < 0, -1.0, 1.0)[:, None]    # the side that is seen
    gw, gh = GRAY_STRIP
    cells = layout_charts(V, F[k], nk, area[k], size, reserved=[(0, 0, gw, gh)])      # 1.0: charts, not a cell each
    args = {"size": size, "linear": linear, "up": tuple(up), "offset_m": ROVER_OFFSET_M, "families": families,
            "all_cells": cells, "normals": nk}
    tex = render_texture(scene, sources, args, pool, rows_per_chunk)
    rgb, have = np.asarray(tex.pop("rgb"), np.float32), tex.pop("source") >= 0
    tex = None
    # 1.0.5: a texel of a triangle a frame sees that no frame colored - the frames' rover masks miss the thin parts
    # and the edges (a strut, a wheel's rim, the arm), and a pixel the mask calls terrain may not color the model -
    # is colored again by the station's own frames without that check (ROVER_UNMASKED_PASS)
    second = 0
    tm = cells.get("tri_map")
    if ROVER_UNMASKED_PASS and tm is not None and cam.any():
        want = (tm >= 0) & ~have
        want &= cam[k][np.where(tm >= 0, tm, 0)]
        if want.any():
            tex2 = render_texture(scene, sources, dict(args, all_cells=dict(cells, tri_map=np.where(want, tm, -1)),
                                                       rover_fallback=True), pool, rows_per_chunk)
            got = want & (tex2["source"] >= 0)
            rgb[got] = np.asarray(tex2["rgb"], np.float32)[got]
            have |= got
            second = int(got.sum())
            tex2 = None
    from .ods import ROVER_GRAY_REL
    from .rover_surface import GRAY_SHADE
    colored = np.zeros(have.shape, bool)
    for (x, y), (w, h) in zip(cells["pos"], cells["wh"]):
        colored[int(y):int(y + h), int(x):int(x + w)] = True
    base = rgb[colored & have]
    g0 = ROVER_GRAY_REL * float(np.mean(base)) if len(base) else ROVER_GRAY_REL * 128.0
    gray = np.full(3, g0, np.float32)
    cell_filled = fill_charts(rgb, have, cells, gray)
    shade = 1.0 - GRAY_SHADE * (1.0 - (np.arange(gh) + 0.5) / gh)   # row j: |n . up| = (j + 0.5) / gh
    rgb[0:gh, 0:gw] = (gray[None, None, :] * shade[:, None, None])
    un = np.flatnonzero(~seen)
    ny = np.clip(np.abs(nrm[un] @ up), 0, 1)
    uv_un = np.stack([np.full(len(un), gw / 2.0 / size), np.clip(ny * gh, 0.5, gh - 0.5) / size], axis=1)
    Vo = np.concatenate([V[F[k]].reshape(-1, 3), V[F[un]].reshape(-1, 3)])
    UVo = np.concatenate([cells["uv"].reshape(-1, 2), np.repeat(uv_un, 3, axis=0)])
    Fo = np.arange(len(Vo)).reshape(-1, 3)
    rec = {"triangles": int(len(F)), "textured_triangles": int(len(k)),
           "seen_by_frames": int(cam.sum()), "seen_by_frames_only": int((cam & ~seen_vp).sum()),
           "seen_from_viewpoints_only": int((seen_vp & ~cam).sum()), "frames": int(len(cam_srcs)),
           "texels_colored_without_rover_mask": second,
           "textured_area_share": round(float(area[k].sum() / max(area.sum(), 1e-12)), 4),
           "viewpoints": int(len(good)), "viewpoints_inside_the_model": int(len(vps) - len(good)),
           "view_radius_m": float(view_radius_m), "families": families, "texture_px": size,
           "texel_mm": None if cells["texel_m"] is None else round(1000 * cells["texel_m"], 2),
           "texels_colored": round(float((colored & have).sum() / max(colored.sum(), 1)), 4),
           "cell_texels_filled": int(cell_filled), "gray_rgb": [round(float(x), 1) for x in gray],
           "charts": int(cells["charts"]), "triangles_per_chart": round(len(k) / max(int(cells["charts"]), 1), 2),
           "chart_max_deg": CHART_MAX_DEG,
           "seconds": round(time.time() - t0, 1)}
    log.info("station mesh: rover %d of %d triangles textured (%.0f %% of the area; %d viewpoints within %.1f m) in %d charts, "
             "texel %s mm, %.0f %% of the texels colored by the frames (%.0f s)", len(k), len(F), 100 * rec["textured_area_share"],
             len(good), view_radius_m, rec["charts"], rec["texel_mm"], 100 * rec["texels_colored"], rec["seconds"])
    return {"V": Vo, "F": Fo, "uv": UVo, "texture": rgb, "record": rec}


def model_code() -> str:
    """1.0.5: a hash of this module - the code that makes the full 3D model's parts.  Every part's record carries it
    ("model_code"); the station runs (:mod:`rpp.ibr.single_sites`) make a station's model again when it differs, and
    leave the station's mesh and panoramas, which this module does not make, as they are."""
    import hashlib
    return hashlib.sha1(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]


def model_current(folder: PathLike, kinds: Sequence[str]) -> bool:
    """True when ``folder`` holds a part of each of ``kinds`` (keys of :data:`PART`) made by this code."""
    now = model_code()
    for kind in kinds:
        ok = False
        for f in Path(folder).glob(f"*{PART[kind]}.json"):
            try:
                ok = ok or json.loads(f.read_text(encoding="utf-8")).get("model_code") == now
            except (OSError, ValueError):
                pass
        if not ok:
            return False
    return True


def write_part(out_dir: PathLike, prefix: str, kind: str, part: Dict[str, Any], station, to8, to16=None) -> Dict[str, Any]:
    """``<prefix>_<PART[kind]>.npz`` (V in the viewer's frame, F, uv), ``.jpg`` (the texture, 8-bit by ``to8``), ``.json``.

    0.99.40 (Christian, 19 Nov 2026: "the ...mesh_terrain.jpg and full 3D texture should be made projected as 16-bit
    images and converted to 8-bit the same way as the ods"): the texture is projected from the 16-bit linear frames
    when the panoramas are (it was), and ``to16`` (the panoramas' 16-bit encoding: the linear value x 64 x exposure16)
    keeps it as ``<stem>_16.png`` beside the .jpg, so that ``rpp ods --retone`` (:func:`retone_textures`) makes the
    .jpg again from it with the panoramas' own 8-bit conversion."""
    import cv2
    out = Path(out_dir)
    stem = f"{prefix + '_' if prefix else ''}{PART[kind]}"
    white = part.get("white")                                    # 0.99.41: the fifth mode's sky and unused texels
    t16 = to16(part["texture"]) if to16 is not None else None
    files16 = []
    if t16 is not None:
        if white is not None:
            t16[white] = 65535
        cv2.imwrite(str(out / (stem + TEXTURE16_SUFFIX)), np.ascontiguousarray(t16[..., ::-1]))
        files16 = [stem + TEXTURE16_SUFFIX]
        del t16
    tex8 = to8(part["texture"])
    if white is not None:
        tex8[white] = 255
    ok, enc = cv2.imencode(".jpg", np.ascontiguousarray(tex8[..., ::-1]), [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise RuntimeError("station mesh: the texture could not be encoded")
    (out / (stem + ".jpg")).write_bytes(enc.tobytes())
    Vp = page_frame(part["V"], station.pivot, station.east, station.up, station.north)
    extra = {}
    sh = part.get("shell")
    if sh is not None:                                           # 0.99.32: the surface to the horizon, on the same texture
        extra = {"shell_V": page_frame(sh["V"], station.pivot, station.east, station.up, station.north),
                 "shell_F": np.asarray(sh["F"], np.uint32), "shell_uv": np.asarray(sh["uv"], np.float32)}
    np.savez_compressed(out / (stem + ".npz"), V=Vp, F=np.asarray(part["F"], np.uint32), uv=np.asarray(part["uv"], np.float32), **extra)
    rec = dict(part["record"], kind=kind, files=[stem + ".npz", stem + ".jpg"] + files16, vertices=int(len(Vp)), mesh_triangles=int(len(part["F"])),
               model_code=model_code())
    (out / (stem + ".json")).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


def copy_part(src_dir: PathLike, dst_dir: PathLike, prefix: str, kind: str = "rover") -> Optional[Dict[str, Any]]:
    """1.0.6 (Christian, 22 Nov 2026: "The z34 full 3d should use the ncam rover texture"): a part made by another run
    of the same station - the Navcam run's rover, for its Mastcam-Z version, whose own frames do not color the rover
    (they are not a deck pan) and whose context frames never do - copied in under this run's ``prefix``.  The two
    runs share the pivot (1.0.1) and the rover model, so the geometry is the same.  None when ``src_dir`` holds no
    such part."""
    src, dst = Path(src_dir), Path(dst_dir)
    recs = sorted(src.glob(f"*_{PART[kind]}.json"))
    if len(recs) != 1:
        return None
    sstem = recs[0].name[: -len(".json")]
    rec = json.loads(recs[0].read_text(encoding="utf-8"))
    dstem = f"{prefix + '_' if prefix else ''}{PART[kind]}"
    files = []
    for f in rec.get("files") or []:
        sf = src / f
        if not sf.is_file():
            if f.endswith((".npz", ".jpg")):
                return None
            continue
        df = dst / (dstem + f[len(sstem):] if f.startswith(sstem) else f)
        df.write_bytes(sf.read_bytes())
        files.append(df.name)
    rec = dict(rec, files=files, copied_from=str(recs[0]))
    (dst / (dstem + ".json")).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


TEXTURE16_SUFFIX = "_16.png"     # 0.99.40: a part's texture in the 16-bit panoramas' encoding


def retone_textures(folder: PathLike, tone8) -> List[str]:
    """0.99.40: the .jpg of every station mesh part in ``folder`` that has its 16-bit texture, made again by ``tone8``
    (a (h, w, 3) float array in the 16-bit units divided by 64 x exposure16 -> uint8: the panoramas' conversion,
    :func:`rpp.ibr.linear16.retone`).  The .glb files are put together again by the caller (:func:`assemble`)."""
    import cv2
    done = []
    for f in sorted(set(Path(folder).glob("*station_mesh_*" + TEXTURE16_SUFFIX)) | set(Path(folder).glob("*station_scape_*" + TEXTURE16_SUFFIX))):
        a = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        if a is None or a.dtype != np.uint16:
            continue
        v = tone8(a[..., :3].astype(np.float32))                 # BGR in, BGR out
        v[(a[..., :3] == 65535).all(axis=-1)] = 255              # 0.99.41: the white sky and unused texels stay white
        dst = f.with_name(f.name[:-len(TEXTURE16_SUFFIX)] + ".jpg")
        ok, enc = cv2.imencode(".jpg", np.ascontiguousarray(v), [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if ok:
            dst.write_bytes(enc.tobytes())
            done.append(dst.name)
        del a, v
    return done


SKIN_JPEG_QUALITY = 90


def write_skins(folder: PathLike, levels_file: Optional[PathLike] = None) -> Dict[str, Any]:
    """0.99.41: the color skins of the fifth mode's texture in ``folder`` - ``<stem>_<tag>.jpg`` beside
    ``<stem>.jpg`` for the tags of :data:`rpp.ibr.color_products.SKIN_TAGS` (enhanced color, enhanced tone, original
    color, decorrelation stretch), from its 16-bit texture with the station's own parameters
    (:func:`rpp.ibr.color_products.texture_products`).  The viewer puts a skin on the terrain and its shell in place of
    the file's texture, in the full 3D and the local 3D terrain.  {} when the folder has no 16-bit full 3D texture."""
    import cv2
    from .color_products import SKIN_TAGS, texture_products
    from .linear16 import UNITS_PER_8BIT, _exposure16
    d = Path(folder)
    done: Dict[str, Any] = {}
    for f in sorted(d.glob("*" + PART["scape"] + TEXTURE16_SUFFIX)):
        a = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        if a is None or a.dtype != np.uint16:
            continue
        stem = f.name[:-len(TEXTURE16_SUFFIX)]
        try:
            rec = json.loads((d / (stem + ".json")).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rec = {}
        tpd = rec.get("texels_per_deg") or (a.shape[1] / 2.0 * HORIZON_FRAC / 95.0)
        views = texture_products(a[..., :3], UNITS_PER_8BIT * _exposure16(d), d, levels_file, float(tpd))
        for tag, v in views.items():
            ok, enc = cv2.imencode(".jpg", np.ascontiguousarray(v), [cv2.IMWRITE_JPEG_QUALITY, SKIN_JPEG_QUALITY])
            if ok:
                (d / f"{stem}_{tag}.jpg").write_bytes(enc.tobytes())
                done[SKIN_TAGS[tag]] = f"{stem}_{tag}.jpg"
        del a, views
    if done:
        log.info("station mesh: the full 3D texture's color skins %s", ", ".join(done.values()))
    return done


def skin_files(folder: PathLike) -> Dict[str, Path]:
    """0.99.41: {view key: file} of the color skins of the fifth mode's texture in ``folder`` (:func:`write_skins`)."""
    from .color_products import SKIN_TAGS
    d = Path(folder)
    out = {}
    for tex in sorted(d.glob("*" + PART["scape"] + ".jpg")):
        for tag, key in SKIN_TAGS.items():
            f = tex.with_name(tex.name[:-4] + f"_{tag}.jpg")
            if f.is_file():
                out[key] = f
    return out


# ------------------------------------------------------------------------------------------- the file
def glb_bytes(parts: Sequence[Tuple[str, np.ndarray, np.ndarray, np.ndarray, bytes]], extras: Optional[Dict[str, Any]] = None) -> bytes:
    """A binary glTF 2.0 file of textured meshes ``(name, V, F, uv, jpeg)``: unlit, double-sided materials.  A part
    whose ``jpeg`` is a string uses the texture of the earlier part of that name."""
    chunks, views = [], []

    def add(b: bytes, target: Optional[int] = None) -> int:
        off = sum(len(p) for p in chunks)
        chunks.append(b + b"\x00" * (-len(b) % 4))
        v = {"buffer": 0, "byteOffset": off, "byteLength": len(b)}
        if target:
            v["target"] = target
        views.append(v)
        return len(views) - 1
    acc, meshes, mats, texs, imgs, nodes = [], [], [], [], [], []
    by_name: Dict[str, int] = {}
    for name, V, F, uv, jpg in parts:
        V = np.ascontiguousarray(V, "<f4")
        uv = np.ascontiguousarray(uv, "<f4")
        F = np.ascontiguousarray(F, "<u4").reshape(-1)
        a_v = len(acc)
        acc.append({"bufferView": add(V.tobytes(), 34962), "componentType": 5126, "count": int(len(V)), "type": "VEC3",
                    "min": [float(x) for x in V.min(axis=0)], "max": [float(x) for x in V.max(axis=0)]})
        acc.append({"bufferView": add(uv.tobytes(), 34962), "componentType": 5126, "count": int(len(uv)), "type": "VEC2"})
        acc.append({"bufferView": add(F.tobytes(), 34963), "componentType": 5125, "count": int(len(F)), "type": "SCALAR"})
        if isinstance(jpg, str):                                 # 0.99.32: the texture of the part of that name
            ti = by_name[jpg]
        else:
            imgs.append({"bufferView": add(bytes(jpg)), "mimeType": "image/jpeg", "name": name})
            texs.append({"source": len(imgs) - 1, "sampler": 0})
            ti = by_name[name] = len(texs) - 1
        mats.append({"name": name, "doubleSided": True, "extensions": {"KHR_materials_unlit": {}},
                     "pbrMetallicRoughness": {"baseColorTexture": {"index": ti}, "metallicFactor": 0.0, "roughnessFactor": 1.0}})
        meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": a_v, "TEXCOORD_0": a_v + 1}, "indices": a_v + 2,
                                                     "material": len(mats) - 1, "mode": 4}]})
        nodes.append({"mesh": len(meshes) - 1, "name": name})
    doc = {"asset": {"version": "2.0", "generator": "rpp.ibr.station_mesh"}, "extensionsUsed": ["KHR_materials_unlit"],
           "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes, "accessors": acc,
           "materials": mats, "textures": texs, "images": imgs,
           "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}],
           "bufferViews": views, "buffers": [{"byteLength": sum(len(p) for p in chunks)}]}
    from .xmp import author_fields, software                    # 0.99.53: the author and the RPP version
    doc["asset"]["generator"] = f"{software()} (rpp.ibr.station_mesh)"
    doc["asset"]["extras"] = dict(extras or {}, **author_fields())
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    binary = b"".join(chunks)
    total = 12 + 8 + len(js) + 8 + len(binary)
    return (struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(js), b"JSON") + js
            + struct.pack("<I4s", len(binary), b"BIN\x00") + binary)


def _part_files(folder: Path, kind: str) -> Optional[Tuple[Path, Path, Path]]:
    for npz in sorted(Path(folder).glob(f"*{PART[kind]}.npz")):
        jpg, js = npz.with_suffix(".jpg"), npz.with_suffix(".json")
        if jpg.is_file():
            return npz, jpg, js
    return None


def glb_texture(path: PathLike, kind: str) -> bytes:
    """The JPEG bytes of a part's texture for a .glb: the file itself, or - the rover's, made at ROVER_TEXTURE_PX - a
    copy reduced to ROVER_GLB_PX (1.0.1: the 8k texture stays beside the .glb, a headset is served 4k)."""
    data = Path(path).read_bytes()
    if kind != "rover":
        return data
    import cv2
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None or max(img.shape[:2]) <= ROVER_GLB_PX:
        return data
    k = ROVER_GLB_PX / float(max(img.shape[:2]))
    small = cv2.resize(img, (int(round(img.shape[1] * k)), int(round(img.shape[0] * k))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buf.tobytes() if ok else data


def assemble_scape(folder: PathLike, rover_folder: Optional[PathLike] = None, out: Optional[PathLike] = None) -> Optional[Dict[str, Any]]:
    """0.99.32: ``<prefix>_station_scape.glb`` in ``folder`` - the fifth mode's file: the meshes "terrain" (the near
    terrain), "horizon" (the shell, on the terrain's texture - so it comes after it in the file; the viewer draws it
    first, by its render order, without the depth test) and "rover" (the rover part of ``rover_folder``, default
    ``folder/with_rover``, with its own texture).  None without a scape part."""
    d = Path(folder)
    tp = _part_files(d, "scape")
    if tp is None:
        return None
    rp = _part_files(Path(rover_folder) if rover_folder else d / "with_rover", "rover")
    recs: Dict[str, Any] = {}
    with np.load(tp[0]) as z:
        if "shell_V" not in z:
            return None
        parts = [("terrain", z["V"], z["F"], z["uv"], tp[1].read_bytes()), ("horizon", z["shell_V"], z["shell_F"], z["shell_uv"], "terrain")]
    try:
        recs["terrain"] = json.loads(tp[2].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        recs["terrain"] = {}
    if rp is not None:
        with np.load(rp[0]) as z:
            parts.append(("rover", z["V"], z["F"], z["uv"], glb_texture(rp[1], "rover")))
        try:
            recs["rover"] = json.loads(rp[2].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            recs["rover"] = {}
    stem = tp[0].name[:-len(PART["scape"] + ".npz")]
    glb = Path(out) if out else d / (stem + SCAPE_SUFFIX)
    t = recs["terrain"]
    extras = {"station_scape": {"frame": "meters about the pivot: x east, y up, z south", "parts": [p[0] for p in parts],
                                "fade_m": t.get("fade_m") or list(FADE_M), "dome_m": (t.get("shell") or {}).get("dome_m", DOME_M),
                                "view_radius_m": (recs.get("rover") or {}).get("view_radius_m", VIEW_RADIUS_M)}}
    glb.write_bytes(glb_bytes(parts, extras))
    rec = {"file": glb.name, "bytes": glb.stat().st_size, "parts": recs, "triangles": int(sum(len(p[2]) for p in parts)),
           "fade_m": extras["station_scape"]["fade_m"], "dome_m": extras["station_scape"]["dome_m"]}
    glb.with_suffix(".json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    log.info("station mesh: %s - %s, %d triangles, %.1f MB", glb.name, " + ".join(p[0] for p in parts), rec["triangles"], rec["bytes"] / 1e6)
    return rec


def assemble(folder: PathLike, rover_folder: Optional[PathLike] = None, out: Optional[PathLike] = None) -> Optional[Dict[str, Any]]:
    """``<prefix>_station_mesh.glb`` in ``folder`` (the station's terrain-only folder) from its terrain part and the
    rover part of ``rover_folder`` (default ``folder/with_rover``; the rover is left out when it has none).  None
    without a terrain part."""
    d = Path(folder)
    tp = _part_files(d, "terrain")
    if tp is None:
        log.info("station mesh: no terrain part in %s (rpp ods --station-mesh)", d)
        return None
    rp = _part_files(Path(rover_folder) if rover_folder else d / "with_rover", "rover")
    parts, recs = [], {}
    for kind, files in (("terrain", tp), ("rover", rp)):
        if files is None:
            continue
        with np.load(files[0]) as z:
            parts.append((kind, z["V"], z["F"], z["uv"], glb_texture(files[1], kind)))
        try:
            recs[kind] = json.loads(files[2].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            recs[kind] = {}
    stem = tp[0].name[:-len(PART["terrain"] + ".npz")]
    glb = Path(out) if out else d / (stem + SUFFIX)
    extras = {"station_mesh": {"frame": "meters about the pivot: x east, y up, z south", "parts": list(recs),
                               "radius_m": recs["terrain"].get("radius_m"), "fade_m": list(FADE_M), "view_radius_m": (recs.get("rover") or {}).get("view_radius_m", VIEW_RADIUS_M)}}
    glb.write_bytes(glb_bytes(parts, extras))
    rec = {"file": glb.name, "bytes": glb.stat().st_size, "parts": recs,
           "triangles": int(sum(len(p[2]) for p in parts)), "fade_m": list(FADE_M)}
    glb.with_suffix(".json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    log.info("station mesh: %s - %s, %d triangles, %.1f MB", glb.name, " + ".join(recs), rec["triangles"], rec["bytes"] / 1e6)
    return rec


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="the station mesh file (.glb) of a station's terrain and rover parts")
    ap.add_argument("folder", help="the station's terrain-only folder (its with_rover folder holds the rover part)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    one, two = assemble(a.folder), assemble_scape(a.folder)
    return 0 if (one or two) else 1


if __name__ == "__main__":
    raise SystemExit(main())
