# Changelog

All notable changes to RPP from 1.0 on. The format follows [Keep a Changelog](https://keepachangelog.com/), and the
versions follow [Semantic Versioning](https://semver.org/): within 1.x the command line, the `rpp.pipeline`
functions, the camera-model file format and the names RPP writes into a work folder stay compatible. Parts marked
experimental in the documentation may change in a minor release.

The development history before 1.0 is in
[`docs/history/`](https://github.com/ctate7163/rpp/tree/main/docs/history): `CHANGELOG_v0p95-v0p99.md`,
`CHANGELOG_v0p90-v0p94.md`, `CHANGELOG_v0p13-v0p85.md` and `CHANGELOG_v0p1-v0p12.md`.

## 1.0.1.dev0 — in development (branch v1p01)
- Brightness: the scale of every camera x 1.1 (`color.scale_rad_to_int16` 2e5 -> 2.2e5; for some hours of 21 Nov a
  key of its own, `color.brightness_gain`).  The level had been set on blocks imaged near perihelion; the
  Sun-distance term darkens those by 0.82, so the new scale puts them at 0.90 of their old level and the aphelion
  blocks at 1.31.  A block processed before 1.0.1 keeps its saved scale for its own images; its station frames get
  the factor with the distance term (`rpp.ibr.linear16.block_config`), the level of a block processed today.
- Freeze: `--zcam-sites SITE ...` runs the zjoints step's site runs for those sites alone (the pipeline's own
  `--zcam-sites`); the joints take the other sites' finished blocks as they are, and zfinal still runs every site.
  The list stays with the run (a restart at logon keeps it; `--zcam-sites all` ends it).  For the 21 Nov restart of
  freeze 3: Seitah Overlook, Issole / Seitah South and the four other blocks the Sun-distance term brightens by 16 %
  or more (Belva, Rochette, Chal Rocks large, South Arm).
- Publishing: a station run with no station to publish (its station skipped) rebuilds no entry.  An empty list
  was read as "every station": the viewer's list got local paths for the 17 stations of the output root and
  nothing was uploaded (21 Nov 17:14, from a 1.0.0rc1 run).
- Viewer: full 3D is the default terrain mode (a station opens in it where it has it, until the visitor chooses
  another); the welcome view shows Van Zyl's own pictures, not muted copies, and opens in the original (raw) color.
- Freeze: the blocks' own mask checkpoint file is passed to every site run (`Run.mask_set`).  A run whose chosen
  model was that same file recorded no setting, and on 1.0.1 the site runs took the default registry name
  `rpp_mask_v5`, which was not on the computer: every block of the 21 Nov restart failed within a minute.
- The 16-bit images 1.25 times lower, the 8-bit images the same: `color.scale_rad_to_int16` 1.76e5 and
  `color.scale_int8_to_int16` 51.2 (2.2e5 and 64 for some hours).  The 16-bit range reaches 5 x 8-bit white.  The
  station frames (`images16/`) keep 64 counts per 8-bit count (`linear16.block_config`).
- Mastcam-Z ZCAM08323 (sol 298, Issole; a focus sweep looking down 25 to 60 degrees) is in the low focus state
  (`298:ZCAM08323` in the shipped list): in the 21 Nov Z34 joint its left eye measured 4669.0 / 4677.5 / 4689.6 px
  at focus 138 / 516 / 786, on the low line (4678.8 / 4688.4 / 4695.2) and 1 % under the high line; run as high it
  failed the joint's sequence-offset check (-11,876 / -12,433 ppm) and Z34 was not promoted.
- Stale products: a dense workspace records the block model and the image and mask sets it was made from
  (`rpp.sfm.dense.workspace_source`) and is rebuilt when the block was aligned or processed again (a changed mask
  set keeps the depth maps); a station's steps are keyed to the block (`single_sites.block_stamp`: the model and the
  radiometric key) and the station code key covers `image.py`, `radiometry.py`, `sun.py` and the tau table.
- Docs: a page on the Mars coordinate systems (`docs/coordinates.md`: the IAU 2000 sphere, planetocentric latitude,
  east longitude, the site, rover navigation, world, camera and station frames, the pixel origin, what each file
  carries, how Metashape reads the PNG position).
- Station runs leave a block alone while a run of it is going on (`single_sites.block_busy`, the block's
  `mppp_status.json`): a block being processed or aligned again keeps the `run_done.json` of the run before, and a
  station made then would mix old and new images.  `--wait-for-blocks` comes back to it.
- Metadata: every 16-bit station frame and every station product carries its provenance - XMP fields (station,
  areocentric latitude, east longitude, elevation, frame, block and block model, radiometric key, scales) and, for the
  frames, the EXIF GPS position Metashape reads.
- The version is 1.0.1 (branch `v1p01`; called 1.1 for a day).  "1.01" is not a version of its own for Python
  packaging - it is read as 1.1.
- Station products follow the radiometric settings: a cached 16-bit frame (`images16/`) made under other settings - or
  before 1.0.1, without the Sun's distance - is made again from its PDS product (`rpp.ibr.linear16.radiometry_key`), and
  a station's stored levels (`tone_levels.json`) are found again.  So an `rpv_process` run of 1.0.1 remakes every
  station's source frames with the new brightness; before this a station would have kept its old frames, or mixed old
  and new ones.  The frames and the record are written as whole files (two station runs may share a block's frames).
  The blocks' 8-bit images, features and alignments are not touched.
- Radiometry: the zenith scale carries the Sun's distance, s = (d_ref/d)² μ exp[−(τ − τ_ref)/(6μ)] with d from the
  orbit at the image's L_s and d_ref = 1.5237 au (`radiometry.apply_sun_distance`, on by default;
  `rpp.radiometry.sun_distance_scale`).  Sunlight varies by a factor 1.45 between perihelion and aphelion; ten station
  panoramas' ground levels differed by 1.77 before and 1.22 with it.  The manifest records `scale_sun_distance`.
  Images come out up to 22 % darker (L_s 251) or 19 % brighter (L_s 71) than with 1.0; a block processed before keeps
  its 8-bit images until it is processed again, its station panoramas get the term (docs/methods.md, section 4).
- RPV: the page tells a PC, a phone or a headset apart (`?device=` overrides it) and shows that device's controls in
  the welcome view.  On a phone the tilt moves the eye about the pivot (8 cm at 15 degrees, slowly re-centered;
  `?tilt=-1` reverses it, `?tilt=0` turns it off), two fingers pinch the zoom, and while driving one finger drags the
  rover; the buttons are larger.  A headset's browser shows the VR button and the controller list before VR.
- `rpp dense --cameras NZ --zooms 34`: a station's Navcam and Mastcam-Z 34 mm frames in their own workspace
  (`dense_<station>_NZ34`); `rpp fusion-compare --cloud NAME=PATH` meshes and scores such a cloud beside the block's,
  and every variant reports its spike triangles and hole-fill checks (the Z34 spike test,
  `rpp_v1p01_z34_spike_test.cmd`).
- The landing frames of sols 1-4 come into Butler Landing: the site keeps the `AUT_` sequences (`SEQUENCE_PREFIXES`), and
  station S001D0052, which the waypoint table does not have, is placed at the S003D0000 waypoint
  (`rpp.waypoints.table.STATION_ALIASES`; the rover did not move until sol 14), with the looser prior of a station
  without its own waypoint.

Station meshes without the misshapen fill and the failed depth maps behind them (Christian, 21 Nov 2026: "a wrong
large rounded hill behind the rover", "mesh floaters and spikes in rockytop" - "How can we prevent these sorts of
misshapen mesh artifacts?").

- **Depth range.** New station workspaces search depth 0.5-300 m (`dense.STATION_DEPTH_RANGE`) instead of each
  frame's tie-point range. The Van Zyl frame looking behind the rover had tie points out to 1.9 km; its search ran to
  2.3 km, its map kept 8 % of the frame and no ground within 8 m, and the sector behind the rover had no measured
  surface at all.
- **Depth-map check and repair.** After the stereo step every frame's geometric map is checked against its terrain
  (`check_depth_maps`: under 20 % of the frame and under 0.4 x the median frame = failed); a failed frame is made again
  once with the depth range (`stereo/rpp_depth_repair.json`), also in a workspace whose maps are otherwise kept, and
  `rpp dense` keeps the stereo step for it. 1.0's fused clouds are still accepted (the fusion code is unchanged).
- **Hole fill bounded by what was seen** (`mesh.FILL_SEEN_RULES`). The nodes away from measured surface are a
  harmonic (membrane) surface over the hole, which cannot rise above its rim (the cubic made the Van Zyl hill);
  seen from the pivot the fill stays under the ray to any farther measured surface the pivot sees (the Skinner Ridge
  "cone" climbed an outcrop's shadow in front of measured terrain); and under the measured skyline, where the
  measured surface reaches out (the dark "teeth" on the horizon at Rockytop, Wildcat Ridge and Chal Rocks). On six
  real meshes (Rockytop, Skinner Ridge, Wildcat Ridge, two Chal Rocks stations): fill above the skyline in 0-2
  two-degree sectors instead of 14-48, none in front of measured terrain at Skinner Ridge (was 165); the Van Zyl hill
  becomes a flat fill (its sector still needs the depth repair and the new context pair for real ground). A first try,
  a cap at the highest covered cell within 25 deg, made plateaus and is off (`FILL_RIM_BOUND`).
- **Mesh checks** in `mesh_report.json` ("fill" -> "checks") and as warnings in the log: the share of each 10 deg
  sector at 8-30 m left to fill (flags Van Zyl 330-10 deg), fill above the skyline, spike-like triangles.
- `read_colmap_array` refuses a truncated map file instead of looping for ever.
- Van Zyl (Sol0052): + the context pair NCAM02049 0671302876 of the sol 49 end-of-drive 360, which sees most of the
  sector behind the rover.

## 1.0.0rc1 — 2026-11-20

The first release candidate of 1.0. The pipeline's features and the station products are those of 0.99.53. This release cleans the code,
removes what earlier studies left behind, and makes RPP easier to install and to start with. The camera models are
still those of 0.99; 1.0.0 will carry the models of the third freeze run.

### Changed

- **The default rover mask model is `rpp_mask_v5`** (it was `rpp_mask_v3`). The third freeze run uses it.
  - A run key now names the mask model, so a block made with the old default is processed and aligned again under
    the new one. `--set mask_checkpoint=rpp_mask_v3` gives the keys of 0.99 and earlier and reuses those blocks.
  - A block processed with the checkpoint file that `rpp_mask_v5` was exported from
    (`convnext_tiny_s4_seg_20261118_v5p2_2.pt`, as in the third freeze run) has the same processing configuration
    as the default: its images are not processed again.
  - The Curiosity blocks (`rpp_studies.msl`) use `rpp_mask_v5` by default.
- **The PyPI package holds the pipeline only.** `pip install rover-photogrammetry` installs `rpp`. The research
  studies (`rpp_studies`) come with a source checkout (`git clone`, then `pip install -e .`), as before. `rpp calib`,
  `rpp zcam-states` and `rpp maps` say so when the studies are not there.
- **The viewer page is part of the package**: `rpp.viewer` (`index.html`, `vendor/`), moved from `docs/ods/`. An
  installed RPP can now write a local copy of the viewer (`rpp single-sites ... --publish DIR`). Without
  `RPP_VIEWER_DIR` and without a checkout named `rpv` beside a source checkout, `--upload` publishes into `./rpv`.
- **Install groups**: `[pipeline]` (masks, alignment, plots) is what `rpp run` needs; `[stations]` is the station
  products and the viewer (`[ibr]` still works). `[all]` is unchanged in what it installs.
- `rpp --help` is grouped by task and starts with the first steps.
- **`scripts\windows\rpv_process.bat`** is the station run for the viewer: `rpv_products_0p99p53.bat` of 0.99.53,
  with `update_rpp_rpv.bat` and `unpublish_station.bat` in it (`--unpublish LABEL ...`). Each window takes the first
  free checkout of `D:\code\RPP_rpv`, `_rpv_b`, `_rpv_c`, `_rpv_d`, so several runs share the stations through their
  locks. A checkout follows the branch of the tree the batch file is in, not a bundle. Log:
  `rpv_process_log_<slot>.txt`.
- **No nadir mark in the panoramas** (0.99.53, `nadir.MARK_IN_PANORAMA`): the mark is the picture
  `<prefix>_nadir_mark.png` alone, which the viewer lays on the ground (`ods.json`: `in_panorama: false`).
- **The rover's texture in the 3D modes has larger islands** (Christian: "the mesh_rover texture should also have
  larger texture islands if possible"): connected triangles that face within 35° share a chart of up to 0.6 m
  (`station_mesh.layout_charts`), in place of a cell per triangle. About 5 times finer texels in the same 4096²
  texture on a test mesh, and seams only at the charts' edges.
- **Every RPV product says who made it** (0.99.53): XMP `dc:creator` and `xmp:CreatorTool` in every JPEG and PNG of a
  station, `asset.generator` and `asset.extras` in the `.glb` files, `author` and `software` in `ods.json` and the
  `panos.json` entries.
- **The fused cloud is keyed on its own code** (`sfm/dense.py`), not on the station steps' code: a change to the
  panorama or mesh code no longer fuses every block again. The clouds of 0.99.51 to 0.99.53 are kept.
- The station code changed (the rover's texture charts), so every station is made once again under 1.0, from the
  mesh step on.
- **RPV:** B (headset) and the B key switch between the stereo terrain and the full 3D terrain and show the standard
  color each time (Christian, 20 Nov 2026).
- The freeze run needs RPP 1.0 (`rpp_studies.calibration.freeze.REQUIRED_VERSION`).
- Documentation: a new README, home page, installation page and roadmap; new pages
  [What is validated and what is experimental](https://ctate7163.github.io/rpp/status/) and
  [RPV: the Rover Photogrammetry Viewer](https://ctate7163.github.io/rpp/viewer/); the navigation is grouped.
- `CITATION.cff` carries the abstract, the keywords and the author's ORCID, and is the only source of the Zenodo
  record's metadata.
- The tests run on Linux and Windows in GitHub Actions.
- **Faster depth maps and a two-pass fusion** (`rpp dense`, every station and block workspace):
  - New depth maps match each image against its 12 best-connected images (COLMAP's default is 20) and sample every
    other pixel of the 11 x 11 matching window (`window_step 2`). `--sources N` (0: COLMAP's 20) and
    `--window-step 1` give the full work. The speed-up is an estimate (about 2-4 x) until the first block is timed.
  - A workspace that already holds depth maps (the 0.99 blocks, a block stopped part way) keeps the options its maps
    were made with, so no map is made again. `--restereo` makes them again with the new options.
  - `rpp dense --two-pass-fusion` (experimental, off by default): a loose fusion (two agreeing pixels: the far
    terrain that one stereo pair sees) and a strict one (four pixels, 1 px, 8°), merged: every strict point plus the
    loose points more than 2 working pixels from any strict point (`fused_loose.ply`, `fused_strict.ply`,
    `rpp_fusion_merge.json`). The default fusion is 0.99's, and the fused clouds of 0.99.51 to 0.99.53 are kept.
- **`rpp fusion-compare`** (experimental): fusion and mesh variants of a station's block cloud, made from the existing
  depth maps into `compare/` beside the cloud, and scored against the block's tie points ring by ring, with a "worse",
  "not worse" or "better" verdict. The variants are the two-pass fusion, a depth-map filter before the fusion
  (`rpp.sfm.depth_filter`: depth edges, small islands, back-facing normals, an optional range limit per camera), both
  together, and COLMAP's Delaunay mesher. The station products, the block's depth maps and its `fused.ply` are not
  changed. See [Station products](docs/station-products.md).
- **The JOSS figures 1-4 are in the standard figure set** (`make_figures.bat`, `rpp_studies.paper.joss_figures`): the
  pipeline diagram, the Navcam pairs of sols 9 and 52, the aligned blocks of Butler Landing, Van Zyl Overlook and
  Rockytop, and the 3D assets of the stations of sols 9, 461 and 52, one entry per file at 400 dpi. An entry whose
  input is missing is skipped with one line saying why. The oblique views and renders are ray cast, and the rover
  models are RPP's own model with the arm in its stowed pose from the image labels.
- **Belva Crater (`belva_crater_large`) starts at sol 770**, with no nearby frames from before it
  (`NEARBY_FROM_FIRST_SOL`). The freeze-3 block, `mars2020_sol_0768_belva_crater_large_zcam`, held 42 frames of
  sols 766 and 768. The block made from now on is `mars2020_sol_0770_belva_crater_large_zcam`.
- The Sol 784 station (`Sol0784_S039D0926`) takes the sol 797 NCAM03795 and NCAM02797 pairs as context, besides
  the sol 784 NCAM00301 pair. A station's new `zcam_context` list is context for its Mastcam-Z 34 mm version only:
  `Sol0789_S039D0926_Z34` takes the ZCAM08826 frames (sol 805, 110 frames).
- `rpp dense --add-images` takes name patterns (`N?F_*_N0390926NCAM*.png`), as `rpp ods --context-images` does, so
  a Mastcam-Z version run with `--terrain own` meshes its station and context frames. A pattern that matches nothing
  is left out with a note.
- **A station is named by its sol** (Christian, 20 Nov 2026: "there cannot be two eod locations on one sol"):
  `Sol0052`, not `Sol0052_S003D2046`; a Mastcam-Z version is `Sol0789_Z34`. The site and drive stay in the station
  list's `"station"` field and in `station.json`. The old names still select a station (`rpv_process.bat
  Sol0052_S003D2046`, `--unpublish`), a station list with old names is read with the new ones (two stations of one
  sol keep their long names), the viewer lists a station once under its new name, and old viewer links
  (`#Sol0052_S003D2046/...`) open the renamed station.
- The full 3D model's texture charts take triangles without area (Van Zyl: "the station mesh's part was not made
  (OverflowError: int too big to convert)").
- RPP is archived on Zenodo: doi:10.5281/zenodo.24408629 for every version (README badge, `CITATION.cff`, `docs/citing.md`),
  doi:10.5281/zenodo.24408630 for v1.0.0rc1.
- Van Zyl (`Sol0052`) takes the sol 49 frames NCAM00302 (S003D1940) and NCAM03049 (S003D1950) as context instead of the
  sol 33 ones.
- **One skyline and a smooth sky** (Van Zyl: "the van zyl sky still has artifacts", "Make sure to improve the horizon
  and sky boundary problem"):
  - In each panorama eye the skyline is one row per column: the top of the terrain that stands on the ground (the mesh
    and the plane, and far pixels darker than midway between the sky and the ground, followed up from the horizon),
    median filtered over 1 deg of azimuth. Above it the sky is a smooth fit to its own pixels (the log of each color
    channel: a cubic in elevation times azimuth harmonics to the third, which fade out at the zenith), so the frames'
    footprints, their edges and the fills' seams are gone. Below it, far pixels as bright as the sky take the colors
    of the terrain on either side in their row.
  - In the full 3D texture the white sky ends at one skyline per 0.25 deg of azimuth (median filtered over 2.25 deg):
    above it every far texel is white, below it none is, and a far texel below it that was taken for sky is filled
    from the hills around it.
- The viewer's normal map of the 3D modes is black beyond 100 m from the mast axis, as the sky.
- The sky is told from the terrain by a first fit to the sky above 10 deg (a far pixel 5 % darker or redder than it
  is terrain), and kept as it is just above the skyline (the original up to 1.5 deg, the fit from 6 deg up; "it
  should have a softer touch near the horizon"): hazy distant mountains stay. Only small specks below the skyline are
  recolored. Checked on the 0.99 panoramas of Sol 9, 52, 86 and 362.
- CI: the docs build and the tests run again on Python 3.10 and 3.11 - three studies' f-strings used Python 3.12
  syntax (quotes reused inside, a backslash), so mkdocstrings could not read `rpp_studies.calibration.hazfit` and the
  3.11 tests could not import them; British spellings and an `RPP_` variable read outside `rpp.env` from today's
  changes fixed; a PDS test-data fetch that fails no longer stops the test session.
- RPV: the drive is back on the 2D page - the steering wheel above the rover button shows wherever the station has
  the drive (no longer only with `?experimental=1`); on a screen up / down arrows drive and left / right turn. In the
  headset, while driving, either thumbstick's left / right turns the rover (the viewer rides along) instead of the
  view; forward / back is still the track on that side.
- `RPP_BLOCK_ROOTS` (roots separated by `;`): a station whose block is not aligned in the run's root is looked for
  there, and its products still go to the run's output root (Van Zyl, aligned only in `D:\rover_blocks`, in a run
  on `D:\rover_blocks_f3`).

### Removed

- **The names from before 0.99**: the alias packages `mppp` and `mppp_studies`, the `mppp` command, `MPPPImage` and
  `scripts/windows/mppp_env.bat`. Use `rpp`, `rpp_studies` and `RPPImage`. Still read, so that earlier work is
  reused: the `MPPP_*` environment variables, the old mask-model names in a block's configuration, and the file
  names RPP writes into a work folder (`rpp.ondisk`).
- **Earlier studies** in `rpp_studies.misc`: the calibration scripts from before 0.91 (`calibration_old`), the lens
  and temperature-bin experiments (`experiments`), the Navcam calibration notes of 0.52 and 0.53, the
  site-appearance analysis and their tests. `zcam_lines` moved to `rpp_studies.calibration`.
- **Batch files and scripts of finished work**: `zcam_joints_097.bat`, `zcam_backlash_rerun.bat`,
  `run_zcam_states.bat`, `check_rpp_reuse.bat`, `sync_rpp.bat`, `sites_status.bat`, `scripts/check_reuse.py` and
  `scripts/_make_notebooks_0p96.py`. `scripts/windows` holds 23 files.
- `.zenodo.json`.

Everything removed is in the git history at the tag `pre-v1.0-archive` (0.99.53).
