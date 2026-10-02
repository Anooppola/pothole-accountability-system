"""End-to-end processing: video -> unique, rated potholes -> database, evidence, Telegram."""
import time

from . import config, db, detector, evidence, severity, telegram_notify, video
from .tracker import PotholeTracker


def _noop(fraction, message):
    pass


def process_video(path, video_name, progress=_noop, send_telegram=True,
                  sample_fps=None, conf=None) -> int:
    """Process one video file. Returns the video's database id.

    progress(fraction 0-1, message) is called as work advances (used by the web page).
    """
    db.init_db()
    video_id = db.create_video(video_name, str(path))
    started = time.time()
    try:
        info = video.video_info(path)
        db.update_video(video_id, duration_s=round(info.duration_s, 2))
        progress(0.0, "Loading the pothole model...")
        detector.load_model()

        # 1-3. Sample frames, detect, track
        tracker = PotholeTracker()
        analysed = blurry = raw = 0
        for time_s, frame, is_blurry in video.sample_frames(path, sample_fps):
            if is_blurry:
                blurry += 1
                continue
            dets = detector.detect(frame, time_s, conf)
            raw += len(dets)
            tracker.update(time_s, frame, dets)
            analysed += 1
            if info.duration_s:
                progress(min(0.85, 0.85 * time_s / info.duration_s),
                         f"Analysing video: {time_s:.0f}s of {info.duration_s:.0f}s, "
                         f"{raw} detections so far")

        # 4. Unique potholes
        progress(0.86, "Merging repeated detections into unique potholes...")
        tracks = sorted(tracker.finalize(), key=lambda t: t.start)

        # 5-6. Severity, priority, evidence, database
        saved = []
        for i, t in enumerate(tracks, 1):
            progress(0.86 + 0.06 * i / max(1, len(tracks)), f"Rating pothole {i} of {len(tracks)}...")
            b = t.best
            r = severity.assess(t.best_frame, b.mask, b.area_ratio, b.centroid, t.hits)
            record = {
                "video_id": video_id,
                "first_seen_s": round(t.start, 2),
                "last_seen_s": round(t.end, 2),
                "best_time_s": round(b.time_s, 2),
                "frames_seen": t.hits,
                "confidence": round(t.max_conf, 3),
                "area_ratio": round(r.area_ratio, 5),
                "corrected_area": round(r.corrected_area, 5),
                "dark_ratio": round(r.dark_ratio, 3),
                "solidity": round(r.solidity, 3),
                "in_path": int(r.in_path),
                "score": r.score,
                "severity": r.severity,
                "priority": r.priority,
            }
            pid = db.insert_pothole(record)
            img, crop = evidence.save_evidence(
                video_id, t.best_frame, b.mask, b.box, pid, r.severity, r.priority, b.time_s, video_name
            )
            db.update_pothole(pid, image_path=img, crop_path=crop)
            saved.append({**record, "id": pid, "image_path": img, "crop_path": crop})

        db.update_video(
            video_id, status="done", frames_analysed=analysed, frames_blurry=blurry,
            raw_detections=raw, pothole_count=len(saved),
            processing_s=round(time.time() - started, 1),
        )

        # 7. Telegram
        if send_telegram:
            notify_video(video_id, progress)
        else:
            status, note = (("skipped", "Not sent (Telegram alerts were switched off)")
                            if config.telegram_configured()
                            else ("not_configured", "Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env"))
            for p in saved:
                db.update_pothole(p["id"], telegram_status=status, telegram_error=note)
        progress(1.0, f"Done: {len(saved)} unique potholes found.")
        return video_id
    except Exception as e:
        db.update_video(video_id, status="failed", error=str(e)[:500],
                        processing_s=round(time.time() - started, 1))
        raise


def notify_video(video_id: int, progress=_noop):
    """Send the summary and one alert per pothole (most urgent first)."""
    v = db.get_video(video_id)
    potholes = [dict(p) for p in db.list_potholes(video_id)]
    if not config.telegram_configured():
        for p in potholes:
            db.update_pothole(p["id"], telegram_status="not_configured",
                              telegram_error="Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env")
        return 0
    progress(0.93, "Sending Telegram alerts...")
    telegram_notify.send_message(telegram_notify.summary_text(v["filename"], potholes))
    potholes.sort(key=lambda p: (p["priority"], -p["score"]))
    sent = 0
    for i, p in enumerate(potholes, 1):
        ok, err = telegram_notify.send_pothole(p, v["filename"])
        db.update_pothole(p["id"], telegram_status="sent" if ok else "failed", telegram_error=err)
        sent += ok
        progress(0.93 + 0.06 * i / max(1, len(potholes)), f"Telegram: sent {sent} of {len(potholes)}")
        time.sleep(0.4)  # stay well under Telegram's rate limits
    return sent


def resend_pothole(pid: str):
    p = db.get_pothole(pid)
    v = db.get_video(p["video_id"])
    ok, err = telegram_notify.send_pothole(dict(p), v["filename"])
    status = "sent" if ok else ("not_configured" if not config.telegram_configured() else "failed")
    db.update_pothole(pid, telegram_status=status, telegram_error=err)
    return ok, err
