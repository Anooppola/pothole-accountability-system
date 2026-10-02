"""Build a demo "dashcam-style" video from a folder of pothole photos.

Each photo becomes a 3-second clip that slowly zooms in, like a car approaching
the pothole. Useful for testing when you have no road video yet.

Usage:
    python scripts/make_demo_video.py <images_folder> <output.mp4> [--seconds 3]
"""
import argparse
import glob
import os

import cv2
import numpy as np


def approach_clip(img, seconds, fps, out_w, out_h):
    h, w = img.shape[:2]
    n = int(seconds * fps)
    for i in range(n):
        t = i / max(1, n - 1)
        zoom = 1.0 + 0.6 * t                       # zoom in by up to 60%
        cw, ch = w / zoom, h / zoom * (out_h / out_w) * (w / h)
        ch = min(ch, h)
        cx = w / 2
        cy = h * (0.45 + 0.10 * t)                 # drift down: pothole moves toward the car
        x1 = int(np.clip(cx - cw / 2, 0, w - cw))
        y1 = int(np.clip(cy - ch / 2, 0, h - ch))
        crop = img[y1:y1 + int(ch), x1:x1 + int(cw)]
        yield cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_LINEAR)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images")
    ap.add_argument("output")
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    files = sorted(
        f for f in glob.glob(os.path.join(args.images, "*"))
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    )
    if not files:
        raise SystemExit(f"No images found in {args.images}")
    out_w, out_h = 1280, 720
    writer = cv2.VideoWriter(args.output, cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (out_w, out_h))
    for f in files:
        img = cv2.imread(f)
        if img is None:
            continue
        for frame in approach_clip(img, args.seconds, args.fps, out_w, out_h):
            writer.write(frame)
    writer.release()
    print(f"Wrote {args.output} from {len(files)} images ({len(files) * args.seconds:.0f} s)")


if __name__ == "__main__":
    main()
