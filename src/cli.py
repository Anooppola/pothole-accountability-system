"""Process a video from the command line (no web page needed).

Usage:
    python -m src.cli path/to/video.mp4 [--no-telegram] [--fps 2] [--conf 0.25]
"""
import argparse
import shutil
import uuid
from pathlib import Path

from . import config, db
from .pipeline import process_video


def main():
    ap = argparse.ArgumentParser(description="Detect and rate potholes in a road video.")
    ap.add_argument("video")
    ap.add_argument("--no-telegram", action="store_true", help="do not send Telegram alerts")
    ap.add_argument("--fps", type=float, default=None, help=f"frames per second to analyse (default {config.SAMPLE_FPS})")
    ap.add_argument("--conf", type=float, default=None, help=f"detection confidence (default {config.CONF_THRESHOLD})")
    args = ap.parse_args()

    src = Path(args.video)
    if not src.exists():
        raise SystemExit(f"File not found: {src}")
    stored = config.UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{src.name}"
    shutil.copy(src, stored)

    def progress(frac, msg):
        print(f"[{frac:5.0%}] {msg}")

    vid = process_video(stored, src.name, progress, not args.no_telegram, args.fps, args.conf)
    v = db.get_video(vid)
    print(f"\nVideo #{vid}: {v['pothole_count']} unique potholes from {v['raw_detections']} raw detections "
          f"({v['frames_analysed']} frames analysed, {v['frames_blurry']} blurry skipped) in {v['processing_s']}s")
    for p in db.list_potholes(vid):
        print(f"  {p['id']}  {p['severity']:<9} {p['priority']:<11} score {p['score']:.2f}  "
              f"at {p['best_time_s']:.1f}s  telegram: {p['telegram_status']}")


if __name__ == "__main__":
    main()
