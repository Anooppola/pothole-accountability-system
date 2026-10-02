"""Temporal association + deduplication: many frame detections -> unique potholes.

1. Frame-to-frame tracking: a detection continues a track if its box overlaps the
   track's last box, or if it is close by and has moved down the frame (potholes move
   toward the bottom of the frame as the vehicle approaches).
2. Filtering: tracks seen only once with low confidence are dropped as noise.
3. Merging: tracks that follow each other within a short time gap, never appear in the
   same frame, and look alike (colour histogram) are merged into one pothole.
"""
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import config
from .detector import Detection


def box_iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def appearance_hist(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Hue-saturation histogram of the pothole pixels, used to compare potholes."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], mask.astype(np.uint8), [30, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist


def hist_similarity(h1, h2) -> float:
    return float(cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL))


def best_view_score(det: Detection) -> float:
    """Prefer confident, large (near) views for evidence and severity."""
    return det.conf * (det.area_ratio ** 0.5)


@dataclass
class Track:
    track_id: int
    detections: list = field(default_factory=list)
    best: Detection = None
    best_frame: np.ndarray = field(default=None, repr=False)
    hist: np.ndarray = field(default=None, repr=False)       # appearance of the best view
    last_hist: np.ndarray = field(default=None, repr=False)  # appearance of the latest view
    frame_times: set = field(default_factory=set)

    @property
    def last(self) -> Detection:
        return self.detections[-1]

    @property
    def start(self) -> float:
        return self.detections[0].time_s

    @property
    def end(self) -> float:
        return self.detections[-1].time_s

    @property
    def hits(self) -> int:
        return len(self.frame_times)

    @property
    def max_conf(self) -> float:
        return max(d.conf for d in self.detections)

    def add(self, det: Detection, frame: np.ndarray):
        # Masks are only needed for the best view; drop them for the rest to save memory.
        self.detections.append(det)
        self.frame_times.add(round(det.time_s, 3))
        self.last_hist = appearance_hist(frame, det.mask)
        if self.best is None or best_view_score(det) > best_view_score(self.best):
            if self.best is not None:
                self.best.mask = None
            self.best = det
            self.best_frame = frame.copy()
            self.hist = self.last_hist
        else:
            det.mask = None

    def absorb(self, other: "Track"):
        self.detections = sorted(self.detections + other.detections, key=lambda d: d.time_s)
        self.frame_times |= other.frame_times
        if best_view_score(other.best) > best_view_score(self.best):
            self.best, self.best_frame, self.hist = other.best, other.best_frame, other.hist


class PotholeTracker:
    def __init__(self):
        self.active: list = []
        self.finished: list = []
        self._next_id = 1

    def _match_score(self, track: Track, det: Detection, frame: np.ndarray) -> float:
        iou = box_iou(track.last.box, det.box)
        if iou >= config.TRACK_IOU:
            score = 1.0 + iou
        else:
            (tx, ty), (dx, dy) = track.last.centroid, det.centroid
            dist = ((tx - dx) ** 2 + (ty - dy) ** 2) ** 0.5
            moved_down = dy >= ty - 0.05
            if not (dist < 0.20 and moved_down):
                return 0.0
            score = 1.0 - dist  # 0.8-1.0, always below any IoU match
        # The pothole must also look the same (guards against scene cuts / neighbours).
        if hist_similarity(track.last_hist, appearance_hist(frame, det.mask)) < config.TRACK_HIST_SIM:
            return 0.0
        return score

    def update(self, time_s: float, frame: np.ndarray, detections: list):
        # End tracks that have not been seen for a while.
        still = []
        for t in self.active:
            (self.finished if time_s - t.end > config.TRACK_MAX_GAP_S else still).append(t)
        self.active = still

        # Greedy matching: best (track, detection) pairs first.
        pairs = []
        for ti, t in enumerate(self.active):
            for di, d in enumerate(detections):
                s = self._match_score(t, d, frame)
                if s > 0:
                    pairs.append((s, ti, di))
        pairs.sort(reverse=True)
        used_t, used_d = set(), set()
        for s, ti, di in pairs:
            if ti in used_t or di in used_d:
                continue
            self.active[ti].add(detections[di], frame)
            used_t.add(ti)
            used_d.add(di)

        for di, d in enumerate(detections):
            if di not in used_d:
                t = Track(self._next_id)
                self._next_id += 1
                t.add(d, frame)
                self.active.append(t)

    def finalize(self) -> list:
        tracks = self.finished + self.active
        self.active, self.finished = [], []
        tracks = [
            t for t in tracks
            if t.hits >= config.MIN_HITS or t.max_conf >= config.SINGLE_HIT_CONF
        ]
        return merge_tracks(tracks)


def merge_tracks(tracks: list) -> list:
    """Merge tracks that are really the same pothole seen twice."""
    tracks = sorted(tracks, key=lambda t: t.start)
    merged = []
    for t in tracks:
        target = None
        for m in merged:
            gap = t.start - m.end
            overlap = bool(m.frame_times & t.frame_times)  # both seen in one frame -> different potholes
            if overlap or gap > config.MERGE_GAP_S or gap < -config.MERGE_GAP_S:
                continue
            (ex, ey), (sx, sy) = m.last.centroid, t.detections[0].centroid
            if ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5 > config.MERGE_MAX_DIST:
                continue
            if hist_similarity(m.hist, t.hist) >= config.MERGE_HIST_SIM:
                target = m
                break
        if target is not None:
            target.absorb(t)
        else:
            merged.append(t)
    return merged
