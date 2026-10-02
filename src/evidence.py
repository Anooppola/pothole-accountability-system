"""Evidence images: the best frame with the pothole highlighted, plus a close-up crop."""
from pathlib import Path

import cv2
import numpy as np

from . import config

# BGR colours per severity
SEVERITY_COLORS = {
    "Minor": (80, 175, 76),      # green
    "Moderate": (0, 165, 255),   # amber
    "Critical": (40, 40, 220),   # red
}


def _fmt_time(seconds: float) -> str:
    m, s = divmod(max(0.0, seconds), 60)
    return f"{int(m):02d}:{s:04.1f}"


def annotate(frame, mask, box, pothole_id, severity, priority, time_s, video_name):
    img = frame.copy()
    color = SEVERITY_COLORS.get(severity, (255, 255, 255))
    h, w = img.shape[:2]

    # Semi-transparent mask + outline
    overlay = img.copy()
    overlay[mask.astype(bool)] = color
    img = cv2.addWeighted(overlay, 0.40, img, 0.60, 0)
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    thick = max(2, w // 400)
    cv2.drawContours(img, contours, -1, color, thick)
    x1, y1, x2, y2 = (int(v) for v in box)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thick)

    # Header bar
    scale = max(0.6, w / 1600)
    font = cv2.FONT_HERSHEY_SIMPLEX
    bar_h = int(46 * scale)
    cv2.rectangle(img, (0, 0), (w, bar_h), (25, 25, 25), -1)
    cv2.rectangle(img, (0, 0), (int(12 * scale), bar_h), color, -1)
    text = f"{pothole_id}  |  {severity}  |  {priority}"
    cv2.putText(img, text, (int(24 * scale), int(31 * scale)), font, scale, (255, 255, 255), max(1, int(2 * scale)), cv2.LINE_AA)

    # Footer
    foot = f"Video: {video_name}   Time: {_fmt_time(time_s)}"
    fs = scale * 0.7
    (tw, th), _ = cv2.getTextSize(foot, font, fs, 1)
    cv2.rectangle(img, (0, h - th - int(18 * scale)), (tw + int(24 * scale), h), (25, 25, 25), -1)
    cv2.putText(img, foot, (int(12 * scale), h - int(10 * scale)), font, fs, (230, 230, 230), 1, cv2.LINE_AA)
    return img


def crop(frame, box, pad: float = 0.4, max_w: int = 480):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    x1, x2 = int(max(0, x1 - pad * bw)), int(min(w, x2 + pad * bw))
    y1, y2 = int(max(0, y1 - pad * bh)), int(min(h, y2 + pad * bh))
    c = frame[y1:y2, x1:x2]
    if c.size == 0:
        return frame
    if c.shape[1] > max_w:
        c = cv2.resize(c, (max_w, int(c.shape[0] * max_w / c.shape[1])), interpolation=cv2.INTER_AREA)
    return c


def save_evidence(video_id, frame, mask, box, pothole_id, severity, priority, time_s, video_name):
    """Write the annotated frame and crop; return their paths (relative to the project)."""
    out_dir = config.EVIDENCE_DIR / f"video_{video_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    full = out_dir / f"{pothole_id}.jpg"
    close = out_dir / f"{pothole_id}_crop.jpg"
    cv2.imwrite(str(full), annotate(frame, mask, box, pothole_id, severity, priority, time_s, video_name),
                [cv2.IMWRITE_JPEG_QUALITY, 90])
    cv2.imwrite(str(close), crop(frame, box), [cv2.IMWRITE_JPEG_QUALITY, 90])
    return _rel(full), _rel(close)


def _rel(p: Path) -> str:
    """Project-relative path when possible (portable), otherwise absolute."""
    try:
        return str(p.relative_to(config.ROOT))
    except ValueError:
        return str(p)
