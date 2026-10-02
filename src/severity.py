"""Estimated Visual Severity Proxy and repair priority.

A 2D camera cannot measure depth, so severity is an *estimate* built from what the
segmentation mask shows:
  - area      : how much road the pothole covers, corrected for distance from the camera
                (log scale, so small far potholes and large near ones both separate)
  - dark      : share of the pothole darker than the surrounding road (deeper holes
                hold shadow / water)
  - irregular : 1 - solidity; ragged, broken edges indicate advanced damage
  - persist   : how many sampled frames it stayed visible (bigger potholes stay in view)

    S = 0.55 * area + 0.20 * dark + 0.15 * irregular + 0.10 * persist   (each scaled 0-1)

Severity: Minor (S < 0.40), Moderate (S < 0.65), Critical (otherwise).
Weights and cut-offs are starting values in config.py, to be calibrated against
human severity labels (RQ2).
Priority also considers whether the pothole is in the vehicle's driving path.
"""
from dataclasses import dataclass

import cv2
import numpy as np

from . import config


@dataclass
class SeverityResult:
    area_ratio: float
    corrected_area: float
    dark_ratio: float
    solidity: float
    frames_seen: int
    in_path: bool
    score: float
    severity: str
    priority: str


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def corrected_area(area_ratio: float, cy: float) -> float:
    """Potholes far ahead (higher in the frame) look smaller; scale them up."""
    factor = (0.75 / max(cy, 0.3)) ** 2
    return area_ratio * float(np.clip(factor, 0.5, 3.0))


def area_score(c_area: float) -> float:
    """Log scale: AREA_MIN of the frame -> 0, AREA_MAX -> 1 (sizes span ~100x)."""
    if c_area <= config.AREA_MIN:
        return 0.0
    return _clip01(np.log(c_area / config.AREA_MIN) / np.log(config.AREA_MAX / config.AREA_MIN))


def dark_ratio(frame: np.ndarray, mask: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    m = mask.astype(np.uint8)
    k = max(5, int(0.03 * max(frame.shape[:2])))
    ring = cv2.dilate(m, np.ones((k, k), np.uint8)) - m
    inside = gray[m.astype(bool)]
    around = gray[ring.astype(bool)]
    if inside.size == 0 or around.size == 0:
        return 0.0
    return float((inside < np.median(around) - 15).mean())


def solidity(mask: np.ndarray) -> float:
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 1.0
    c = max(contours, key=cv2.contourArea)
    hull = cv2.contourArea(cv2.convexHull(c))
    return float(cv2.contourArea(c) / hull) if hull > 0 else 1.0


def in_driving_path(cx: float, cy: float) -> bool:
    """Centre of the lane, in the near half of the frame."""
    return 0.25 <= cx <= 0.75 and cy >= 0.45


def severity_name(score: float) -> str:
    for upper, name in config.SEVERITY_LEVELS:
        if score < upper:
            return name
    return config.SEVERITY_LEVELS[-1][1]


def priority_level(severity: str, in_path: bool) -> int:
    if severity == "Critical":
        return 1
    if severity == "Moderate":
        return 1 if in_path else 2
    return 2 if in_path else 3


def assess(frame: np.ndarray, mask: np.ndarray, area: float, centroid: tuple, frames_seen: int) -> SeverityResult:
    cx, cy = centroid
    c_area = corrected_area(area, cy)
    dark = dark_ratio(frame, mask)
    sol = solidity(mask)
    w = config.SEVERITY_WEIGHTS
    score = (
        w["area"] * area_score(c_area)
        + w["dark"] * _clip01(dark)
        + w["irregular"] * _clip01((1 - sol) / 0.4)
        + w["persist"] * _clip01(frames_seen / config.PERSIST_REF)
    )
    sev = severity_name(score)
    path = in_driving_path(cx, cy)
    return SeverityResult(
        area_ratio=area,
        corrected_area=c_area,
        dark_ratio=dark,
        solidity=sol,
        frames_seen=frames_seen,
        in_path=path,
        score=round(score, 3),
        severity=sev,
        priority=config.PRIORITY_NAMES[priority_level(sev, path)],
    )
