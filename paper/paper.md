---
title: 'Rover Photogrammetry Pipeline (MPP): beyond the fixed stereo baseline for Mars rover images'
tags:
  - Python
  - planetary science
  - Mars rover
  - photogrammetry
  - structure from motion (SfM)
  - convolutional neural networks (CNN)
authors:
  - name: Christian D. Tate
    orcid: 0000-0003-3467-0099
    affiliation: "1"
affiliations:
  - name: Malin Space Science Systems, San Diego, CA, USA
    index: 1
date: 20 November 2026
bibliography: paper.bib
---
# Summary
 
Each time a Mars rover parks, its mast cameras photograph the landscape in stereo, often in a full 360° panorama
[@Maki:2020; @Bell:2021]. The Mars 2020 Perseverance rover [@Farley:2020] has done this at hundreds of stops, and the
images are released to NASA's Planetary Data System (PDS). These images are not yet easy to use as 3D content: they are
in PDS formats, their camera models are in a convention that common 3D software does not read, and the rover's own
hardware fills part of most frames.
 
The Rover Photogrammetry Pipeline (RPP) turns these archive images into true-scale 3D assets that anyone can load: a
stereo 360° panorama and a textured 3D model of the terrain around each rover stop, and aligned point clouds and meshes
for groups of nearby stops. The outputs are plain files in open formats (PNG, JPEG, glTF, COLMAP projects and JSON),
each with a record of the PDS products and the code version that made it. RPP is written in Python and runs from
resumable commands over a list of rover stops.
 
# Statement of need
 
RPP is for researchers who want real Mars terrain in their own applications: scientists who want to see rocks in
context, educators and developers who build virtual-reality or browser experiences, and robotics groups that need
realistic terrain for simulation and training data. These users need 3D assets they can trust, not a photogrammetry
project to set up.
 
No open tool takes them from the archive to such assets. PDS readers, structure-from-motion (SfM) and multi-view
stereo engines, and renderers exist separately. Between them are rover-specific problems: removing the rover from
the images, replacing the mission's camera models with models that common software reads, putting the images of many
stops into one frame in meters, and making the colors of different cameras and times of day agree. RPP solves these
in code and connects the steps end to end (Figure 1). To our knowledge, it is the first open pipeline from public
rover archive products to aligned multi-station reconstructions and viewer-ready stereo panoramas and 3D models.
 
Three properties make the results usable beyond one site or one viewer:
 
- **Trustworthy geometry and color.** Assets are in true scale, oriented east-north-up, colored from
  radiance-calibrated images under one documented convention, and traceable to their source products.
- **Open outputs at every stage.** Processed images, aligned blocks and station assets are plain files that 3D
  software, game engines and web viewers read.
- **More than one rover and camera.** RPP supports Perseverance's Navcam, Hazcam and Mastcam-Z cameras; Curiosity
  support is experimental. The method applies to any rover whose images come with
  localization and camera models.
The same pipeline serves a second audience, researchers who study the cameras and the reconstructions themselves.
Every aligned block is also a measurement of the cameras. RPP's versioned camera, stereo-rig and mast models were
solved from such blocks. They vary with temperature, focus, zoom and sol, and they become the defaults for the next
run. Tie points and depth maps are kept for reconstruction-error analysis. These uses are described in follow-on
papers; this paper describes the software.
 
# State of the field
 
Several tools turn rover images into range maps, meshes or 3D models: VICAR [@VICAR], PRoViP [@Barnes:2018] and the
Ames Stereo Pipeline [@Beyer:2018]. Their published rover workflows start from fixed-baseline stereo pairs taken at
one rover position and use the camera models and poses delivered with the images. PRoViP merges products from several
rover positions, and the Ames Stereo Pipeline documents bundle adjustment and an SfM tool for rover images. To our knowledge, none of them has
a published pipeline that aligns the images of many rover stops in one bundle adjustment and refines the camera and
stereo-rig models in it, and none makes 360° stereo or viewer-ready assets.
 
JPL's Landform [@Vona:2025] is the terrain tool of Mars 2020 operations and is open source. It fuses the mission's
stereo range products from many rover stops into tiled terrain, with the camera models of the image labels and the
poses of the mission's localization. It aligns the terrain of different site drives to each other and to the orbital
elevation model as rigid bodies; it does not adjust the poses of the images within a site drive, and it does not refine
camera or rig models. Its surface is a Poisson reconstruction of a thinned point cloud, which is smooth by
construction. Several of its workflows need the mission's data systems, and its products are not in the PDS.
 
The nearest relative of RPP is the Metashape workflow of @Schmauss:2025 for Curiosity images. RPP is its Mars 2020
counterpart, but the masking, the camera models and the prior-weighted bundle adjustment are done in code, and the
reconstruction continues to finished 3D assets.
 
Panoramic and image-based 3D photography is a mature field [@Hedman:2017; @Hedman:2018]. RPP does not contribute a new
rendering method. It contributes the rover-specific steps that let standard methods work on archive data. RPP builds
on COLMAP [@Schoenberger:2016] rather than writing a new SfM engine, so that its projects open in COLMAP and in other
tools.
 
SfM needs many overlapping images, and rover image sets are sparse. However, Perseverance often parks within 10 m of
earlier or later stops. We call such a group of stops a block. RPP's site table defines several dozen blocks in the first
2,000 sols. In a block,
images from different stops triangulate the terrain over much wider baselines than one stereo pair (Figure 3).
 
# Software design
 
RPP has three stages (Figure 1). Each stage writes its products to disk with a JSON record of what they were made
from. A run can stop and resume at any stage. When the inputs or the settings of a product change, it and the
products built on it are made again.
 
**1. Preprocessing.** RPP reads radiance-calibrated PDS products with the Planetary Data Reader [@Brown:2024]. It
converts their colors to one convention for the Navcam, Hazcam and Mastcam-Z cameras, and it scales their brightness
for the Sun's height, the Sun's distance and the seasonal atmospheric opacity. A ConvNeXt
convolutional neural network [@Liu:2022; @Wightman:2019; @Paszke:2019], fine-tuned on thousands of rover image-mask
pairs from several cameras, masks the rover hardware and its shadows in every frame (Figure 2). Without the mask, a
feature matcher ties images together on the static rover deck instead of on the terrain. The weights are on Hugging
Face (<https://huggingface.co/ctate7163/rpp-mask>). Each image gets its camera model from RPP's versioned models,
evaluated at that image's temperature, focus, zoom and sol. These models replace the CAHV-family models of the PDS
labels. They are COLMAP cameras: a thin-prism fisheye model for the Navcam and Hazcams, and models that follow the
OpenCV standard for Mastcam-Z. They could be converted to the CAHVOR convention; RPP does not do so, because the
solved models fit the images better than the label models; that comparison is the subject of a separate calibration
paper. The initial position of
every stop comes from the mission's localized waypoints [@M2020:waypoints], in meters, east-north-up. The initial
attitude comes from the rover navigation frame in the image labels, which can drift in azimuth; the alignment corrects
it.
 
**2. SfM and MVS.** Features are matched with COLMAP through pycolmap. RPP's own bundle adjustment, on pyceres
[@Agarwal:2023], adds waypoint position priors, weak attitude priors, resolution-aware weights, and stereo rigs: the
two eyes of a stereo camera share one relative pose within an epoch of sols. A health report flags blocks whose
residuals, rig changes or camera shifts are out of the expected range. Dense stereo and fusion use COLMAP. The aligned
block is exported as a COLMAP project, point clouds and meshes (Figure 3).
 
**3. Image-based rendering.** For each end-of-drive station, RPP renders depth and normal maps, a terrain mesh and
the station assets from the block's geometry. The main trade-off in this stage is fidelity against completeness.
Where the images do not see the terrain, under the rover or behind rocks, RPP fills it by interpolation and records
where it did so in a provenance map. Users who need measured surfaces only can use the block's point clouds and the
provenance maps.
 
# Station assets
 
Two kinds of 3D asset are produced for each station (Figure 4):
 
1. **An omnidirectional stereo (ODS) panorama** [@Peleg:2001], left eye above right eye in one image, with the
   metadata that common 360° viewers and headsets use to show it in stereo.
2. **A full 3D station model:** one continuous mesh from under the rover out to the horizon, a separate textured
   rover model, and sky spheres beyond the terrain. It allows head motion and walking around near the mast, which a
   panorama cannot.
Four design choices follow from the users named above:
 
- The projection center is on the mast's axis of rotation, so the views match what the mast cameras saw.
- The rover is rendered separately, both as projected images and as a 3D model. A user can show or hide it.
- The terrain extends to the horizon, so the asset needs no backdrop from outside the data.
- The full 3D model uses one texture in a radial projection centered below the mast (Figure 4C). Texture resolution
  falls with distance, as the angular size of the terrain does. The model is small enough for a standalone headset.
# Research impact statement
 
- A demonstration set of station assets is hosted in the Rover Photogrammetry Viewer (RPV,
  <https://ctate7163.github.io/rpv/>), which shows them in a browser and in VR headsets. The original files of that
  set are available to developers on Hugging Face (<https://huggingface.co/datasets/ctate7163/rpp-rpv>). RPV is one
  application built on RPP's outputs, and the same files load in Blender, game engines and other 360° viewers.
- The Mastcam-Z landscape models of Jezero crater on Sketchfab [@Tate:Sketchfab] were made with an early version of
  the pipeline, then named MPPP, and aligned in Agisoft Metashape [@Agisoft:2024]. The current pipeline aligns in
  COLMAP.
- RPP's camera, stereo-rig and mast models are the basis of a Mastcam-Z and Navcam geometric calibration paper, in
  preparation.
- RPP 1.0 is archived on Zenodo [@Tate:RPP:zenodo] and is packaged for pip as `rover-photogrammetry`. Tests run in
  continuous integration, and a worked example notebook processes the Van Zyl Overlook block from public PDS products.
# AI usage disclosure
 
Claude Code (Anthropic) was used throughout the development of RPP: writing and refactoring code, writing tests,
writing the figure scripts, and drafting documentation and parts of this paper. The author designed the pipeline,
made the scientific and design decisions, and directed and reviewed the generated code and text. Correctness was
checked by the test suite and by running the pipeline on real data and inspecting the results: alignment residuals
and health reports for each block, consistency of the camera models across independent blocks and against the rover's
deck fiducials, and visual checks of the station assets in a browser and a headset.
 
# Figures
 
![The RPP pipeline. Inputs from outside RPP (gray) and models solved with RPP (tan) enter the preprocessing stage.
Each of the three stages (blue) writes open-format outputs (green), which 3D software, RPV, and other applications
can read.\label{fig:pipeline}](figure1.png)
 
![A Navcam stereo pair from sol 52 at Van Zyl Overlook (NLF/NRF_0052_0671568531, NCAM02052). A and B: the
processed images, with the area masked by the network grayed out. C and D: the same images undistorted to a 95°
pinhole camera, with the masked area removed.\label{fig:masks}](figure2.png)
 
![The aligned block at Van Zyl Overlook, centered on the sol 52 station. A: the dense point cloud from above, with
the camera centers. B: shaded relief of the same ground. C: an oblique view looking north, with rover models at the
end-of-drive stops. D: the terrain mesh from the same viewpoint. Panels C and D show the terrain to 50 m from the
center.\label{fig:block}](figure3.png)
 
![The 3D assets for the sol 52 station at Van Zyl Overlook. A: the omnidirectional stereo 360° panorama in
cylindrical projection, left eye, terrain only. B: the same with the rover. C: the full 3D model's texture, in a
radial projection centered below the mast. D: the full 3D model rendered from a head position near the
mast.\label{fig:assets}](figure4.png)
 
# Acknowledgements
 
We acknowledge contributions from the Mastcam-Z team at Arizona State University. [TODO: funding statement, as JOSS
requires.]
 
# References