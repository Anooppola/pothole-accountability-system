"""Upload page: choose a road video, process it, see the potholes found."""
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from src import config, db, telegram_notify
from src.pipeline import process_video
from src.ui import PRIORITY_BADGE, SEVERITY_BADGE, TELEGRAM_LABEL, abs_path, badge, fmt_time

st.title("Pothole Detection and Road Accountability")
st.caption(
    "Upload a pre-recorded road video. The system finds potholes with YOLOv8-Seg, counts each "
    "pothole once, rates its severity and repair priority, and sends alerts to Telegram."
)

# ---------- Sidebar: settings + Telegram ----------
with st.sidebar:
    st.subheader("Settings")
    sample_fps = st.slider("Frames analysed per second", 1.0, 5.0, float(config.SAMPLE_FPS), 0.5,
                           help="Higher finds more but is slower.")
    conf = st.slider("Detection confidence", 0.10, 0.80, float(config.CONF_THRESHOLD), 0.05,
                     help="Lower finds more potholes but also more false alarms.")
    send_tg = st.checkbox("Send alerts to Telegram", value=config.telegram_configured(),
                          disabled=not config.telegram_configured())

    st.subheader("Telegram")
    if config.telegram_configured():
        st.success("Bot connected", icon=":material/check_circle:")
        if st.button("Send test message"):
            ok, msg = telegram_notify.test_connection()
            (st.success if ok else st.error)(msg)
    else:
        st.warning(
            "Not set up yet. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to the `.env` file, "
            "then restart the app.",
            icon=":material/info:",
        )

# ---------- Upload + process ----------
uploaded = st.file_uploader("Road video", type=["mp4", "mov", "avi", "mkv", "m4v"])

if uploaded is not None:
    col_v, col_go = st.columns([3, 2])
    with col_v:
        st.video(uploaded)
    with col_go:
        st.markdown(f"**{uploaded.name}**  \n{uploaded.size / 1e6:.1f} MB")
        go = st.button("Detect potholes", type="primary", icon=":material/search:", width="stretch")

    if go:
        stored = config.UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{Path(uploaded.name).name}"
        stored.write_bytes(uploaded.getbuffer())
        bar = st.progress(0.0, text="Starting...")

        def progress(frac, msg):
            bar.progress(min(1.0, max(0.0, frac)), text=msg)

        try:
            vid = process_video(stored, uploaded.name, progress, send_tg, sample_fps, conf)
            st.session_state["last_video"] = vid
        except Exception as e:  # show the problem instead of a stack trace
            st.error(f"Processing failed: {e}")
            st.stop()

# ---------- Results of the last processed video ----------
vid = st.session_state.get("last_video")
if vid:
    v = db.get_video(vid)
    potholes = [dict(p) for p in db.list_potholes(vid)]
    st.divider()
    st.subheader(f"Results: {v['filename']}")

    count = lambda key, val: sum(1 for p in potholes if p[key] == val)  # noqa: E731
    c = st.columns(5)
    c[0].metric("Unique potholes", len(potholes))
    c[1].metric("Critical", count("severity", "Critical"))
    c[2].metric("Moderate", count("severity", "Moderate"))
    c[3].metric("Minor", count("severity", "Minor"))
    c[4].metric("P1 Urgent", count("priority", "P1 Urgent"))
    st.caption(
        f"{v['raw_detections']} raw detections in {v['frames_analysed']} frames were merged into "
        f"{v['pothole_count']} unique potholes. {v['frames_blurry']} blurry frames skipped. "
        f"Processing time {v['processing_s']} s for a {v['duration_s']:.0f} s video."
    )

    if not potholes:
        st.info("No potholes found. Try lowering the detection confidence in the sidebar.")
    else:
        table = pd.DataFrame([{
            "ID": p["id"], "Severity": p["severity"], "Priority": p["priority"],
            "Time": fmt_time(p["best_time_s"]), "Frames": p["frames_seen"],
            "Confidence": f"{p['confidence']:.0%}", "Score": p["score"],
            "Telegram": p["telegram_status"],
        } for p in potholes])
        st.dataframe(table, hide_index=True, width="stretch")

        cols = st.columns(3)
        for i, p in enumerate(potholes):
            with cols[i % 3]:
                st.image(abs_path(p["image_path"]), width="stretch")
                st.markdown(
                    f"**{p['id']}** {badge(p['severity'], SEVERITY_BADGE)} "
                    f"{badge(p['priority'], PRIORITY_BADGE)}  \n"
                    f"at {fmt_time(p['best_time_s'])} {TELEGRAM_LABEL.get(p['telegram_status'], '')}"
                )
        st.page_link("views/review.py", label="Go to the Review page to approve or reject each pothole",
                     icon=":material/arrow_forward:")
