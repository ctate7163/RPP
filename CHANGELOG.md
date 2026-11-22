# Changelog

All notable changes to RPP from 1.0 on. The format follows [Keep a Changelog](https://keepachangelog.com/), and the
versions follow [Semantic Versioning](https://semver.org/): within 1.x the command line, the `rpp.pipeline`
functions, the camera-model file format and the names RPP writes into a work folder stay compatible. Parts marked
experimental in the documentation may change in a minor release.

The development history before 1.0 is in
[`docs/history/`](https://github.com/ctate7163/rpp/tree/main/docs/history): `CHANGELOG_v0p95-v0p99.md`,
`CHANGELOG_v0p90-v0p94.md`, `CHANGELOG_v0p13-v0p85.md` and `CHANGELOG_v0p1-v0p12.md`.

## 1.0.6 — 22 Nov 2026 (branch v1p01)
The panoramas change (the sky above the frames, small islands of other frames' colors), so every station is made
again, not only its model.

- **The panorama's sky is not extrapolated above what the frames saw** (`skyline_sky`, `SKY_HOLD`; Rockytop in the
  headset: "the top pole has artifacts in the sky").  The sky above the skyline is a fit - a cubic in elevation with
  three azimuth harmonics - to the sky the frames saw, which at Rockytop ends at about 33 deg; evaluated to the zenith
  it ran to a dark red patch at 50-75 deg (Sol0461) and to a violet oval (Wildcat Ridge).  Above the highest fitted
  elevation the fit is now held there, and its azimuth terms fade out over 15 deg: one color per row up high.
- **A small island colored only by a frame of another place or time takes its rim's colors** (`fill_islands`; "the
  white disc at Van Zyl's rock").  The station's own frames do not see that spot (the rover's deck is in front of it
  in the one frame that looks there), so a context frame of sol 49, taken 8 m away at another time of day, colored it:
  sunlit there, in the rock's shadow in the station's frames - a light disc in dark ground.  Islands of context or
  fill-only colors up to 0.6 deg² that the station's own frames ring are now filled from their rim.
- **The terrain is held under the mast's skyline** (`pano_skyline`, `SkyCeiling`; "the white fill behind Skinner's
  crest").  Behind Skinner Ridge's crest the mesh's top surfaces stood up to a meter above the line where the frames
  see sky; seen from the mast those directions are sky, so they took the sky's white (64 m² of the 1.0.4 model within
  19 m, 91 % of it in directions where the panorama shows sky).  Free-space carving from the mast: where the panorama
  shows sky nothing solid lies along the ray, so the one-sheet terrain is held under the skyline's ray of its azimuth -
  0.1 deg above it at the crest (the crest that makes the skyline stays), 0.3 deg under it behind the crest (what the
  mast did not see stays hidden from it and takes the crest's colors), nothing within 3 m or under a skyline below the
  horizon.  Skinner Ridge: 49 m² lowered by 0.17 m (median), all beyond 10 m in azimuths 270-30 deg; Rockytop,
  Wildcat Ridge and Van Zyl: nothing.
- **A Mastcam-Z version's full 3D rover is its Navcam station's** (`--rover-part-from`, `copy_part`; "The z34 full 3d
  should use the ncam rover texture").  Its own frames do not color the rover (they are no deck pan) and its context
  frames never do, so its rover was mostly gray; the two runs share the pivot and the rover model, so the Navcam run's
  rover part is copied in.
- **Viewer: no black screen between stations; the neighbors' 3D files fetched ahead.**  The old station's surfaces
  stay until the new ones are made, then the two are swapped in one frame (they were dropped before the new file was
  fetched).  Once a station is up, the 3D files of the stations before and after it are fetched in the background
  (four kept).  The headset holds two stations' textures for a moment during the swap.
- Bell Island Large's alignment "fail" is the attitude check, not the alignment: all 464 images registered at 0.56 px,
  but the frames' label attitudes differ from the solution by 2.8 deg at the 95th percentile (fail at 2), mostly the
  31 frames of S072D0000 (2.0 deg; the others 0.6-1.3) - the rover's pointing knowledge at that station.
- Not in this version: sewing `mesh.ply`'s sheets.  The viewer's terrain is one sheet; in the panoramas the rays that
  pass through a crack are a few hundred pixels of an 8k eye (Van Zyl 432, Rockytop 243, Skinner Ridge 236) - the thin
  light lines on Van Zyl's rock among them.

## 1.0.5 — 22 Nov 2026 (branch v1p01)
The full 3D model only; meshes, depth maps and panoramas are those of 1.0.4.

- **The viewer's terrain is one sheet** (`rpp.ibr.station_mesh.top_sheet`).  It was the station mesh's triangles
  simplified (2.5 million to 500,000), and that mesh is several surfaces that are not sewn - the height field near
  the rover, the Poisson patches on its steep faces, the zones beyond, the fill and its underlay.  Their rims, cracks
  and overlaps came out of the simplification as arcs, flaps and holes one could see through (Van Zyl, the rocks at
  3.9 m: 1.0.4 bridged some cracks in `mesh.ply`, the viewer model still showed them).  Now the mesh's top surface is
  sampled straight down on a 2.5 cm grid - one height per place, a narrow pit (a crack fallen through to the sheet
  beneath) raised to its rim - and that sheet is simplified to the same 500,000 triangles, in a space scaled by the
  range so that the triangles are smaller near the rover.  Measured against the top surface of `mesh.ply`:
  Van Zyl, 95 % of places within 1.3 mm at 1-4 m and 2.7 mm at 14-20 m (1.0.4: 6.4 and 30 mm); Rockytop Sol0461, median
  0.2 - 0.3 mm (1.0.4: 3.5 mm near, 19 mm far).  Triangle edges at Van Zyl: 5.6 cm at 2-4 m, 11 cm beyond 10 m (9 - 10 cm
  everywhere before).  The simplification goes in passes that each keep half of the triangles, and the sheet is
  repaired after every pass (`simplify_in_steps`, `repair_sheet`: triangles without area, repeated ones and edges
  of more than two triangles removed; a triangle folded over smoothed out, or dropped and its hole closed) - four
  passes from 4.0 million at Van Zyl, 1,409 / 628 / 313 / 4 folds put right, none left, no open edge inside the sheet.
  The rocks by the rover (within 6 m, where the ground rises 8 cm in 25 cm) are checked against the grid after the
  last pass and the record says how far off they are (`top_sheet.near_rocks`; Van Zyl: 1.0 mm at 95 % of 20,886
  places, 1.7 mm at 99 %, 17 mm at the worst one); over 3 mm at 95 % the sheet is simplified again with 1.3 times
  the triangles.  What one sheet gives up is the underside of an overhang.  `TOP_SHEET = False` is the terrain of
  before; a failure of the sheet falls back to it with a warning.
- **Hidden ground takes colors grown in from its seen edges** (`grown_vertex_colors`, `grow_cells`).  A triangle the
  mast does not see has a cell of its own; a cell's texels no frame colored took one flat color per cell - the flat,
  jagged shards behind rocks.  They now take the color interpolated between the triangle's corners, the corners'
  colors being the harmonic interpolation of the seen surface around the patch; the texels a frame colored stay.
- The rule of 1.0.2 that gave a hidden triangle under another sheet the mast's picture is off for the one sheet (it
  has nothing beneath it): at Rockytop 68,469 triangles took it, behind rocks the rock's lit face.
- When the hidden triangles' cells do not fit beside the disc (a site of many rocks), only those nearer the mast get
  cells (10, 7.5, 5, 3.5, 2.5 m), the others the disc's picture; it was an error that left the station without a model.
- **A station's model is made again alone when only the model's code changed.**  Every part's record carries
  `model_code` (a hash of `station_mesh.py`); `single-sites` runs `rpp ods ... --station-mesh-only` for a variant
  whose panorama is up to date and whose model is of other code (the step "model" in the status and the summary), and
  such a station is not "done".  `station_mesh.py` is out of the hash of the mesh / panorama code, and
  `SAME_PRODUCTS` names this code as making the same meshes, maps and panoramas as 1.0.4's (`9360937dcbf555b7`): the
  stations made on 1.0.4 get their models again (about a quarter of an hour each), not their panoramas (an hour).
  The model made alone reads the panorama's sky from the 16-bit file of the run before and writes the texture's
  color skins.
- Viewer: the Beta label is to the right of the steering wheel; B held for 0.7 s starts the drive where the station
  has it, or ends it (the keyboard's B and the right controller's B; a short press is still stereo / full 3D, done
  when the button comes up); the stick's click no longer starts the drive.
- Viewer: a station without the full 3D model is left out of the page (the list keeps it; `?all=1` shows every
  station); it shows again when a run uploads its model.
- **The horizon shell has no gap** (`horizon_shell`; in the headset "a black semi circle behind Skinner Ridge and the
  others").  Its first ring was at the angle of 17 m on level ground, the same at every azimuth; where the ground
  falls away the surface at that angle is far beyond the near terrain's end (Skinner Ridge, to the south: 32 m at
  -10 deg, the terrain ends at 20 m), and a ray below the horizontal that met nothing was put on level ground under
  the mast - nearer than 17 m, so its triangles were left out.  The first ring is now the lowest angle at which any
  azimuth is 17 m away, such a ray is no nearer than the ring beneath it, and a triangle with a corner on the far
  surface or the sky is always kept (the far surface 105 m overhead left a wedge of the zenith without sky).
  Directions with nothing drawn, seen from the mast (2.88 million): Skinner Ridge 32,637 to 30, Wildcat Ridge 4,699
  to 18 (the rest are cracks of the 1.0.4 terrain, which the one sheet does not have).
  Where a floater is taken out of the terrain (below) the shell follows a ray past it to what the terrain draws or,
  beyond the terrain's 20 m, to the surface out there (`horizon_shell(near=...)`): before, the shell left that
  direction to the near terrain, which no longer drew anything there (Wildcat Ridge: 4,026 directions black where the
  floater was; Rockytop Sol0461: 735; now none, from the mast or 0.5 m off it).
- **A floater is not taken into the terrain** (`under_floaters`; Wildcat Ridge: "a bad floater attached to the ground
  in front of the rover" - a sheet 5.4 m long, 2 m over the slope, on a thin post; Rockytop has one 17 m out).  The
  top surface is lowered to the surface beneath where it floats (0.4 m of air or more under 0.6 m of mesh or less),
  piece by piece: a piece goes when the ground does not hold it (less than a tenth of its rim is joined to ground
  1.5 m broad or more), it is more than twice as large as the narrow thing it stands on, and the mast sees the
  ground under half of it or more; its post goes with it.  Wildcat Ridge: 3.3 m2 lowered by up to 2.25 m; Rockytop
  Sol0461: 4.6 m2 by up to 2.9 m; Skinner Ridge: nothing (its ledges and the boulder by the rover stay whole).
- **The sky above the skyline is a model of the panorama's sky** (`sky_model`; Rockytop: "the top pole has artifacts
  in the sky").  The panorama of Sol0461 has a dark red patch at 60 - 75 deg and Wildcat Ridge's a violet oval over
  the ridge; the texture took the panorama's pixels.  Now: one color per degree of elevation (the median over the
  azimuths without empty and outlying pixels), and along the skyline's circle the panorama's own color in each
  direction, fading into it over 12 deg.  The panoramas themselves are not changed (see "Not in this version").
- **The rover is textured wherever the station's Navcam frames see it** (the rover model had more gray surfaces than
  it should).  A triangle was textured when it could be seen from within 1 m of the pivot; now also when a frame
  of the station sees it (in the frame, nothing of the mesh between).  And a texel no frame colored - the frames' rover
  masks miss thin parts and edges (struts, a wheel's rim, the arm), and a pixel the mask calls terrain may not color
  the model - is colored in a second pass by the station's own Navcam frames without the masks
  (`ROVER_UNMASKED_PASS`; context frames still never color the rover).  The record says how many triangles each way
  and how many texels the second pass colored.  Sol0461 on 1.0.4: 55 % of the rover's area textured and 77 % of those
  texels colored by a frame - the rest was gray.
- **`single-sites --terrain regular`**: the block's terrain as with `block`, but of a LARGE or HUGE block only a part,
  so that fewer depth maps are made - the alignment is the large block's.  The part: the frames of the sols of the
  regular block of the same place (`van_zyl_overlook`, sols 49-71, for a station of `van_zyl_overlook_huge`: 4 of its
  26 waypoints), when the station's sol is one of them; else (no regular block in the site definitions, or the
  station is not of its sols) the frames of the stations within 30 m of it; and always its own.  The cloud is
  `colmap/dense_block_<name>_<families>`.  `rpp dense --block-images` takes patterns (`???_0052_*`).  A station
  made before with the whole block's cloud is made again (its commands differ).
- `single-sites --check-done`: nothing run - exit 0 when every station of the run is made as these arguments would
  make it (every step after the cloud with these commands, the full 3D model of this code), else 1.  The batch file
  runs Van Zyl from its own frames only when the regular terrain did not make it - not when only its upload failed.
- Not in this version: the mesh's own cracks (`mesh.ply` is as 1.0.4 makes it; the panoramas, rendered from the mast,
  do not show them), the white disc at the base of the rock at Van Zyl (in the panorama itself; origin not found),
  the patches in the panoramas' own sky (the red one of Sol0461; they are in the ODS images, not only the model), and
  ground the fill puts above the real skyline behind a crest (Skinner Ridge: it takes the sky's white).

## 1.0.4 — 21 Nov 2026 (branch v1p01)
- Station mesh, one sheet (`rpp.ibr.mesh.tidy_sheets`, after the fill; `mesh_report.json` `fill.tidy`): within 10 m
  the long triangles seen edge-on from the pivot are dropped; a level measured triangle wholly under another piece of
  the measured surface within 0.35 m is dropped (the zones overlap by 0.6 m at 4, 12, 20 and 30 m: two sheets 5 mm
  apart); pieces of fewer than 60 triangles are dropped; holes of at most 80 edges and 0.3 m are closed with a fan.
  Measured on Van Zyl (Sol0052): 618 slivers, 91,135 triangles of a lower sheet, 7,680 in 1,020 small pieces, 2,407
  holes closed; rays from four eye places that end on the fill or on nothing: unchanged.
- Cracks bridged (`zip_cracks`): every boundary edge of the measured surface gets a triangle to the nearest boundary
  vertex of another boundary loop within 0.12 m (x range / 4 m beyond 4 m).  Found on the Van Zyl rock at 3.9 m,
  azimuth 45 deg: where the height field hands a steep face to the Poisson patch the two meet without shared
  vertices - rings of cracks around the rock's faces, the fill showing through, which the viewer mesh's
  simplification (500,000 triangles to 20 m, 10 cm edges) turns into arcs and flaps.  46,192 triangles on Van Zyl.
- Not done as first written, because it made holes on Van Zyl: dropping the lower sheet within one piece (it takes
  the ground under a rock's overhang; `TIDY_SAME_PIECE`), by the centroid alone (cracks where two sheets cross;
  `TIDY_WHOLLY`), and dropping the fill's underlay (`TIDY_DROP_FILL`: rays ending on nothing below -10 degrees went
  from 0 to 9,201).  The fill and the measured points are still meshed apart.

## 1.0.3 — 21 Nov 2026 (branch v1p01)
- A new version number, so that every station is made again on the code of this evening (a station is "done" only
  when it was made by the running code): the sky of the full 3D texture from the panorama, sheets under the surface
  textured like the surface, the hue-preserving 8-bit roll-off, the Navcam left / right factor, the 8192 px rover
  texture, the stern cross piece, the welcome view.
- JOSS figures (`make_figures.bat` stood still on them): a block's dense cloud is read in parts, cropped to the
  figure's area and thinned to 12 M points as it is read (it was loaded whole and sorted); isolated points are
  counted on the occupied cells (one far point made a very large grid); the manifest's camera models are read once,
  not at every stop; image names of `images.bin` are read in blocks.  Every figure with data prints its steps with
  the seconds since it began, so a slow step names itself.
- JOSS figures, the note of 21 Nov: figure 2 panel titles 8.5 pt and the Sol 52 left eye x 1.03 (figure only;
  `FIG2_LEFT_GAIN`); figure 3 tilt 1.5 deg (was 3) and the Van Zyl cloud's colors x 1.25 (colored from images of the
  earlier brightness); the paper's files `figure1.png` ... `figure4.png` are copies of the diagram and the Sol 52 /
  Van Zyl versions.
- Station runs: `--first rockytop oeb --reverse` runs the names of `--first` in the order given (they were mixed by
  sol), then the others from the latest sol back; `oeb` is the landing site's block (butler_landing).
- Viewer: the screen controls begin with the space bar, and the arrows are named apart (right: next site, left:
  previous site); the phone's two buttons too.

## 1.0.2 — 21 Nov 2026 (branch v1p01; numbered 1.0.1.dev0 and 1.0.2.dev0 during the day)
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
- Full 3D texture: projected from the pivot itself, the panorama's center (0.5 m above it until 1.0) - no sliver of
  unseen ground behind each rock, colored from other frames, outlines it.  The sky is the frames' own (not white):
  far texels keep their colors below the skyline's circle (the hazy crater rim and the delta at Van Zyl had been
  whitened as sky) and are a 3 deg Gaussian mean of the far texels above it (`station_mesh.smooth_sky`).
- A station rendered from Mastcam-Z frames (the Z34 versions) takes the pivot of its Navcam frames, not one fitted
  to the Mastcam-Z centers.
- Rover: charts to 50 deg and 1 m (35 deg, 0.6 m: 21,800 charts on the model, now 14,200); the texture is made
  and kept at 8192 px and reduced to 4096 px in the viewer's .glb files; the stern cross piece of the body (the 0.72 m
  wide piece at x -1.71..-1.47 and its fittings) 1 cm down and 2 deg clockwise (`rover_model.PART_NUDGE`, set by
  eye; for an hour it was on the high-gain antenna, the wrong piece).
- Publishing: a station run with no station to publish (its station skipped) rebuilds no entry.  An empty list
  was read as "every station": the viewer's list got local paths for the 17 stations of the output root and
  nothing was uploaded (21 Nov 17:14, from a 1.0.0rc1 run).
- Standard 8-bit view (`linear16.tone_pipeline`): above the knee (235) the brightest channel is rolled off and the
  others with it, and the color fades to white (`PIPELINE_FADE`).  Rolled off channel by channel, a sky at the knee
  changed hue - a white band over the horizon and purple columns above it in the brighter images of 1.0.1.  Nothing
  changes where no channel is above the knee.  The 16 bits had headroom throughout (Van Zyl: 448 of 1024 at most).
- Full 3D sky: above the skyline's circle the texture takes the panorama's sky in each texel's direction
  (`station_mesh.pano_sky`), not its own far texels - those, filled column by column where no frame saw the sky, ran
  as streaks to the zenith.  The panorama's sky is one smooth fit.
- Full 3D texture: a hidden triangle that lies within 0.35 m under another sheet of the mesh takes the disc like
  the sheet above it (`station_mesh.under_a_sheet`).  The fill's sheets are not sewn to the measured ground, and
  through the cracks one saw the sheet beneath in a cell's fill tone - gray slivers along the patch under the rover.
- Navcam left and right: `color.brightness_by_eye` {"NL": 0.980, "NR": 1.021} - right / left 0.96.  On 11 stereo
  pairs of sols 72-1601 (RAD products, matched points) the right eye's radiance is 0.955 of the left's (median;
  pairs 0.90-0.98); another measurement gave about 0.97.  Re-estimating the flat fields is parked.
- The version is 1.0.2.
- Welcome view: Van Zyl's own entry with every variant (stereo, rover, full 3D), opened in the original color, made
  again after an upload so its files have their dataset addresses; WEST in the sky only with the info page; the
  "Mars 2020 Perseverance rover" line lower, blue in orange; the home button 40 px, white at home, orange elsewhere.
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
