"""
Radiometric steps: DN -> radiance, first-order illumination/opacity
normalization, white balance, and integer quantization.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Tuple, Union

import numpy as np

PathLike = Union[str, Path]


def interpolate_table(csv_path: PathLike, x: float, period: float = 360.0) -> float:
    """
    Linear interpolation in a two-column CSV (header skipped).  The abscissa is
    periodic (solar longitude), so the query is wrapped instead of extrapolated.
    """
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)
    rows = []
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        rd = csv.reader(f)
        next(rd, None)
        for r in rd:
            try:
                rows.append((float(r[0]), float(r[1])))
            except (ValueError, IndexError):
                continue
    if len(rows) < 2:
        raise ValueError(f"Need at least two rows in {csv_path}")
    rows = sorted(dict(rows).items())
    xs, ys = np.array([r[0] for r in rows]), np.array([r[1] for r in rows])
    return float(np.interp(x % period, xs, ys, period=period))


SUN_DISTANCE_REFERENCE_AU = 1.5237      # Mars' mean distance from the Sun (its semi-major axis)


def sun_distance_scale(d_au: float, d_ref_au: float = SUN_DISTANCE_REFERENCE_AU) -> float:
    """1.0.1: the sunlight at the top of the atmosphere at ``d_au`` from the Sun, relative to ``d_ref_au``:
    (d_ref / d)^2.  Mars moves between 1.381 au (L_s 251) and 1.666 au (L_s 71): 1.22 to 0.84, a factor 1.45."""
    return float((float(d_ref_au) / float(d_au)) ** 2)


def zenith_scale(solar_elevation_deg: float, tau: float, tau_ref: float, mu_min: float,
                 d_au: float = None, d_ref_au: float = SUN_DISTANCE_REFERENCE_AU) -> Tuple[float, float]:
    """
    s = (d_ref / d)^2 * mu * exp(-(tau - tau_ref) / (6 mu)),   mu = max(sin(elevation), mu_min).

    Dividing radiance by ``s`` normalizes scene brightness to an overhead Sun at the reference opacity and at the
    reference distance from the Sun: the three first-order terms of the sunlight reaching a level surface -

    * (d_ref / d)^2: the inverse-square law for the Sun's distance ``d_au`` (1.0.1; left out when ``d_au`` is None);
    * mu: the Sun's height (the cosine of the incidence angle on level ground);
    * exp(-(tau - tau_ref) / (6 mu)): the dust.  The factor 6 is the empirical attenuation of the *total*
      (direct + diffuse) surface irradiance with optical depth - the direct beam alone falls as exp(-tau / mu), but
      most of the scattered light still reaches the ground.

    Returns (s, mu).
    """
    mu = max(float(np.sin(np.radians(solar_elevation_deg))), float(mu_min))
    s = float(mu * np.exp(-(tau - tau_ref) / 6.0 / mu))
    if d_au is not None:
        s *= sun_distance_scale(d_au, d_ref_au)
    return s, mu


def dn_to_radiance(dn: np.ndarray, scale: float, offset: float) -> np.ndarray:
    return dn.astype(np.float64) * scale + offset


def quantize(rad: np.ndarray, valid: np.ndarray, cfg_color: dict) -> Tuple[np.ndarray, np.ndarray]:
    """
    radiance (H,W,3, float) -> (uint16 linear, uint8) images.

    uint16 = rad * scale_rad_to_int16                      (linear, never gamma-encoded)
    uint8  = uint16 / scale_int8_to_int16 + offset         (optionally gamma-encoded)

    Zero is reserved for invalid pixels: valid pixels are clipped to >= 1.
    """
    s16 = float(cfg_color["scale_rad_to_int16"])
    s8 = float(cfg_color["scale_int8_to_int16"])
    o8 = float(cfg_color["offset_int8_to_int16"])
    v = valid[..., None]

    lin16 = rad * s16
    im16 = np.clip(np.rint(lin16), 1, 65535)
    im16 = np.where(v, im16, 0).astype(np.uint16)

    a = lin16 / s8 + o8
    if cfg_color.get("apply_gamma"):
        g = float(cfg_color["gamma"])
        a = np.clip(a, 0, None) ** (1.0 / g) * 256.0 ** (1.0 - 1.0 / g)
    im8 = np.clip(np.rint(a), 1, 255)
    im8 = np.where(v, im8, 0).astype(np.uint8)
    return im16, im8
