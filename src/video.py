"""Read a video and yield sampled, non-blurry frames."""
from dataclasses import dataclass

import cv2
import numpy as np

from . import config


@dataclass
class VideoInfo:
    fps: float
    frame_count: int
    duration_s: float
    width: int
    height: int


def video_info(path: str) -> VideoInfo:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return VideoInfo(fps, count, count / fps if fps else 0.0, w, h)


def blur_score(frame: np.ndarray) -> float:
    """Variance of the Laplacian: low values mean a blurry frame."""
    h, w = frame.shape[:2]
    if w > 640:  # normalise resolution so the threshold means the same for any video
        frame = cv2.resize(frame, (640, int(h * 640 / w)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def sample_frames(path: str, sample_fps: float = None, blur_threshold: float = None):
    """Yield (time_s, frame, is_blurry) for frames taken at about `sample_fps`."""
    sample_fps = sample_fps or config.SAMPLE_FPS
    blur_threshold = config.BLUR_THRESHOLD if blur_threshold is None else blur_threshold
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps / sample_fps))
    idx = 0
    try:
        while True:
            ok = cap.grab()
            if not ok:
                break
            if idx % step == 0:
                ok, frame = cap.retrieve()
                if not ok or frame is None:
                    break
                yield idx / fps, frame, blur_score(frame) < blur_threshold
            idx += 1
    finally:
        cap.release()
