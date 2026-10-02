"""End-to-end test: a short video runs through the whole pipeline (uses the real model)."""
import cv2
import numpy as np

from src import config, db
from src.pipeline import process_video


def test_pipeline_runs_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "EVIDENCE_DIR", tmp_path / "evidence")

    # 4-second plain road video (no potholes)
    path = tmp_path / "road.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (640, 360))
    rng = np.random.default_rng(0)
    for _ in range(40):
        writer.write(np.clip(rng.normal(110, 25, (360, 640, 3)), 0, 255).astype(np.uint8))
    writer.release()

    vid = process_video(path, "road.mp4", send_telegram=False)
    v = db.get_video(vid)
    assert v["status"] == "done"
    assert v["frames_analysed"] + v["frames_blurry"] >= 7
    assert v["pothole_count"] == len(db.list_potholes(vid))
