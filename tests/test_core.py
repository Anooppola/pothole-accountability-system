"""Unit tests for tracking, severity and Telegram formatting.  Run:  pytest -q"""
import numpy as np
import pytest

from src import config, severity, telegram_notify, tracker
from src.detector import Detection, remove_overlaps

H, W = 360, 640


def road_frame(seed=0, tint=(90, 90, 90)):
    rng = np.random.default_rng(seed)
    frame = np.clip(rng.normal(0, 12, (H, W, 3)) + np.array(tint), 0, 255).astype(np.uint8)
    return frame


def make_det(t, x1, y1, x2, y2, conf=0.7):
    mask = np.zeros((H, W), bool)
    mask[int(y1):int(y2), int(x1):int(x2)] = True
    ys, xs = np.nonzero(mask)
    return Detection(t, (x1, y1, x2, y2), conf, mask, mask.mean(), (xs.mean() / W, ys.mean() / H))


def paint(frame, det, color):
    frame[det.mask] = color
    return frame


# ---------- Tracking / deduplication ----------

def test_same_pothole_across_frames_is_one_event():
    tr = tracker.PotholeTracker()
    for i in range(5):  # pothole moves down and grows as the vehicle approaches
        d = make_det(i * 0.5, 280 - i * 5, 200 + i * 15, 360 + i * 5, 240 + i * 18)
        tr.update(d.time_s, paint(road_frame(i), d, (30, 40, 60)), [d])
    assert len(tr.finalize()) == 1


def test_two_potholes_in_same_frames_stay_separate():
    tr = tracker.PotholeTracker()
    for i in range(4):
        a = make_det(i * 0.5, 100, 220 + i * 10, 180, 260 + i * 10)
        b = make_det(i * 0.5, 450, 220 + i * 10, 530, 260 + i * 10)
        f = paint(paint(road_frame(i), a, (30, 40, 60)), b, (30, 40, 60))
        tr.update(i * 0.5, f, [a, b])
    assert len(tr.finalize()) == 2


def test_single_low_confidence_detection_is_dropped_as_noise():
    tr = tracker.PotholeTracker()
    d = make_det(0.0, 280, 220, 360, 260, conf=0.30)
    tr.update(0.0, paint(road_frame(), d, (30, 40, 60)), [d])
    assert tr.finalize() == []


def test_overlapping_masks_in_one_frame_are_reduced_to_one():
    a = make_det(0.0, 100, 200, 300, 300, conf=0.8)
    b = make_det(0.0, 120, 210, 280, 290, conf=0.4)  # inside a
    assert remove_overlaps([a, b]) == [a]


# ---------- Severity / priority ----------

@pytest.mark.parametrize("score,name", [(0.10, "Minor"), (0.39, "Minor"), (0.40, "Moderate"),
                                        (0.64, "Moderate"), (0.65, "Critical"), (1.0, "Critical")])
def test_severity_names(score, name):
    assert severity.severity_name(score) == name


def test_priority_rules():
    assert severity.priority_level("Critical", False) == 1
    assert severity.priority_level("Moderate", True) == 1
    assert severity.priority_level("Moderate", False) == 2
    assert severity.priority_level("Minor", True) == 2
    assert severity.priority_level("Minor", False) == 3


def test_bigger_pothole_scores_higher():
    frame = road_frame()
    small = make_det(0, 300, 300, 330, 320)
    big = make_det(0, 200, 250, 440, 340)
    s_small = severity.assess(frame, small.mask, small.area_ratio, small.centroid, 3).score
    s_big = severity.assess(frame, big.mask, big.area_ratio, big.centroid, 3).score
    assert s_big > s_small


def test_solidity_of_rectangle_is_one():
    assert severity.solidity(make_det(0, 100, 100, 200, 200).mask) == pytest.approx(1.0, abs=0.02)


def test_area_score_is_bounded_and_increasing():
    vals = [severity.area_score(a) for a in (0.001, 0.005, 0.02, 0.1, 0.5)]
    assert vals[0] == 0.0 and vals[-1] == 1.0
    assert vals == sorted(vals)


# ---------- Telegram ----------

def test_caption_escapes_html_and_fits_limit():
    p = {"id": "PH-2026-001", "severity": "Critical", "priority": "P1 Urgent", "in_path": 1,
         "best_time_s": 12.5, "frames_seen": 5, "confidence": 0.71, "score": 0.72}
    cap = telegram_notify.pothole_caption(p, "<road>&video.mp4")
    assert "PH-2026-001" in cap and "Critical" in cap and "P1 Urgent" in cap
    assert "&lt;road&gt;&amp;video.mp4" in cap
    assert len(cap) <= 1024


def test_not_configured_does_not_call_telegram(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    ok, err = telegram_notify.send_message("hello")
    assert not ok and "not configured" in err.lower()
