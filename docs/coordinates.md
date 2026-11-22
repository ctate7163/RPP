# Mars coordinate systems

Every position RPP writes is in one of the frames below. They are the mission's own frames (the Mars 2020 camera
SIS and the PLACES localization) and one local frame of RPP's; nothing is converted to an Earth datum.

## The planet

| | |
|---|---|
| Body | Mars, the IAU 2000 sphere of radius 3,396,190 m (`rpp.waypoints.table.MARS_RADIUS_M`), the sphere of the Mars 2020 maps |
| Latitude | planetocentric, degrees, north positive |
| Longitude | east positive, degrees (0–360 in the waypoint table; −180 to 180 where a file format asks for it) |
| Elevation | meters above the areoid (the MOLA geoid), as the waypoint table gives it |
| Map frame | the waypoint table's `easting`, `northing` in meters, the mission's map projection of that sphere; RPP uses only differences of them, so a meter of easting is a meter on the ground at the landing site |

The rover's place on Mars comes from the mission's waypoint table (one row per site and drive: longitude, latitude,
easting, northing, elevation). A product's label gives the site and drive it was taken at and the rover's attitude;
RPP never takes a map position from the label alone when the table has the station.

## Frames

| Frame | Axes | Origin | Where it appears |
|---|---|---|---|
| Site frame (`SITE_FRAME`, index *n*) | North, East, Down | where the rover was when site *n* was declared | PDS labels (`ORIGIN_OFFSET_VECTOR` is the rover in this frame) |
| Rover navigation frame (`ROVER_NAV_FRAME`) | +X forward, +Y right, +Z down | on the nominal ground under the rover, moving with it | PDS labels: the camera models (CAHV…) are in it, and `ORIGIN_ROTATION_QUATERNION` (scalar first) turns it into the site frame |
| **World frame** (RPP) | **East, North, Up**, meters | the waypoint of site 3, drive 0 (the landing site frame); a block subtracts a rounded offset, kept in `project.json` | every block model, mesh, point cloud, camera pose and export |
| Camera frame | x right (increasing sample), y down (increasing line), z forward | the camera's center of projection | every camera pose: `R_w2c` has the camera axes in world coordinates as its rows |
| Station frame (RPV) | East, North, Up, meters | the station's pivot, on the mast axis at that stop | station meshes, depth maps and panoramas; the panorama's column 0 looks at the azimuth in `AzimuthOfColumn0Deg` (degrees east of north) |

North–East–Down and East–North–Up are exchanged by P = [[0,1,0],[1,0,0],[0,0,−1]], which is its own inverse:
x_ENU = P x_NED. The full chain from a label to a world pose is in [Methods](methods.md), section 2.

The attitude in a label is the rover's own estimate of its navigation frame. Its azimuth can drift between the
rover's attitude updates, so RPP uses the label attitude as a starting value that the alignment corrects, while the
waypoint positions tie the block to the map.

## Pixels

The center of the first pixel is (0, 0), as in the mission's CAHVOR models and in OpenCV. COLMAP and Metashape put
(0, 0) at the corner of the first pixel, so the exporters add 0.5 px to the principal point. Every product is padded
to its detector frame, so a pixel coordinate at downsample factor *s* is *s* times the full-resolution coordinate
(corner origin).

## What the files carry

| File | Position | Convention |
|---|---|---|
| Processed image PNG (8- or 16-bit) | EXIF GPS in the `eXIf` chunk; the full record as XMP and `iTXt` | `GPSLatitude` planetocentric, `GPSLongitude` east (−180 to 180 with its E/W reference), `GPSAltitude` meters above the areoid (`GPSAltitudeRef` 1 when negative), `GPSMapDatum` "Mars 2000 sphere (IAU), planetocentric" |
| 16-bit station frame (`images16/`) | the same EXIF GPS; XMP fields for the station, the block and its model, the radiometric key and the scales | as above |
| Station products (panoramas, depth maps, meshes' textures) | XMP fields `Station`, `Latitude`, `Longitude`, `Elevation`, `Datum`, `Frame`, `AzimuthOfColumn0Deg` | degrees and meters as in the first table; the frame is the station frame |
| `mppp_manifest_*.json` | per image: site, drive, the world position and rotation, longitude, latitude, elevation, `position_source` | world frame; `position_source` says which waypoint (or the label offset) gave the position |
| `project.json`, COLMAP model, Metashape XML and reference CSV | camera centers and rotations | world frame minus the block's offset (`offset` in `project.json`) |

Metashape reads the EXIF GPS of the PNGs when the images are added, as it does for any camera: the reference pane
then shows longitude, latitude and altitude. It labels them WGS 84 because EXIF has no field it reads for the body;
the numbers are the Mars values above. For metric work set the chunk's coordinate system to a local one and import
`references.txt` (East, North, Up in meters, with yaw, pitch and roll; see [The steps](pipeline.md)).

## Relation to other tools

- JPL's PLACES and the PDS labels: site and rover navigation frames as above; RPP reads them unchanged.
- Landform (Vona et al. 2025) works in the mission's site-drive frames with the PLACES poses and aligns its
  terrain to the orbital elevation model. RPP's world frame differs from the map frame by the constant easting,
  northing and elevation of the site 3, drive 0 waypoint.
- A HiRISE or CTX product in the mission's equirectangular projection is brought into the world frame by subtracting
  that same waypoint's easting and northing (and the areoid elevation).
