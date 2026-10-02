"""YOLOv8-Seg pothole detector: frame in, list of pothole detections out."""
from dataclasses import dataclass, field
from functools import lru_cache

import cv2
import numpy as np

from . import config


@dataclass
class Detection:
    time_s: float
    box: tuple                 # x1, y1, x2, y2 in pixels
    conf: float
    mask: np.ndarray = field(repr=False)   # bool array, same size as the frame
    area_ratio: float = 0.0    # mask area / frame area
    centroid: tuple = (0.0, 0.0)  # (x, y) normalised 0-1


def ensure_model() -> str:
    """Download the pretrained model the first time it is needed."""
    if not config.MODEL_FILE.exists():
        from huggingface_hub import hf_hub_download
        import shutil

        downloaded = hf_hub_download(config.MODEL_REPO, config.MODEL_REPO_FILE)
        shutil.copy(downloaded, config.MODEL_FILE)
    return str(config.MODEL_FILE)


@lru_cache(maxsize=1)
def load_model():
    from ultralytics import YOLO

    return YOLO(ensure_model())


def detect(frame: np.ndarray, time_s: float, conf: float = None) -> list:
    """Run the model on one frame and return filtered detections."""
    conf = config.CONF_THRESHOLD if conf is None else conf
    model = load_model()
    h, w = frame.shape[:2]
    result = model.predict(
        frame, conf=conf, imgsz=config.IMG_SIZE, device=config.DEVICE, verbose=False
    )[0]
    if result.masks is None or result.boxes is None or len(result.boxes) == 0:
        return []

    detections = []
    polygons = result.masks.xy  # polygons in original-frame pixel coordinates
    for i, box in enumerate(result.boxes):
        poly = polygons[i]
        if poly is None or len(poly) < 3:
            continue
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(mask, [poly.astype(np.int32)], 1)
        area = float(mask.sum()) / (h * w)
        if area < config.MIN_MASK_AREA:
            continue
        ys, xs = np.nonzero(mask)
        cx, cy = xs.mean() / w, ys.mean() / h
        if cy < config.ROI_TOP:
            continue
        x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
        detections.append(
            Detection(
                time_s=time_s,
                box=(x1, y1, x2, y2),
                conf=float(box.conf[0]),
                mask=mask.astype(bool),
                area_ratio=area,
                centroid=(float(cx), float(cy)),
            )
        )
    return detections
