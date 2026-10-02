"""Review page: every detected pothole with its evidence; approve or reject each one."""
import pandas as pd
import streamlit as st

from src import config, db
from src.pipeline import resend_pothole
from src.ui import (PRIORITY_BADGE, REVIEW_BADGE, SEVERITY_BADGE, TELEGRAM_LABEL, abs_path, badge,
                    fmt_time)

st.title("Review potholes")
st.caption("Check each detection. Approve real potholes; reject false alarms (shadows, patches, manholes).")

videos = db.list_videos()
if not videos:
    st.info("No videos processed yet. Upload one on the Upload page.")
    st.page_link("views/upload.py", label="Upload a video", icon=":material/upload:")
    st.stop()

# ---------- Filters ----------
labels = {"All videos": None}
labels.update({f"#{v['id']}  {v['filename']}  ({v['uploaded_at'][:16].replace('T', ' ')})": v["id"] for v in videos})
f1, f2, f3, f4 = st.columns([3, 2, 2, 2])
video_label = f1.selectbox("Video", list(labels))
sev_filter = f2.multiselect("Severity", ["Critical", "Moderate", "Minor"], default=[], placeholder="All")
pri_filter = f3.multiselect("Priority", list(config.PRIORITY_NAMES.values()), default=[], placeholder="All")
rev_filter = f4.multiselect("Review status", ["Pending", "Approved", "Rejected"], default=[], placeholder="All")

potholes = [dict(p) for p in db.list_potholes(labels[video_label])]
video_names = {v["id"]: v["filename"] for v in videos}
shown = [
    p for p in potholes
    if (not sev_filter or p["severity"] in sev_filter)
    and (not pri_filter or p["priority"] in pri_filter)
    and (not rev_filter or p["review_status"] in rev_filter)
]

# ---------- Summary ----------
m = st.columns(5)
m[0].metric("Potholes", len(potholes))
m[1].metric("Pending review", sum(p["review_status"] == "Pending" for p in potholes))
m[2].metric("Approved", sum(p["review_status"] == "Approved" for p in potholes))
m[3].metric("Rejected", sum(p["review_status"] == "Rejected" for p in potholes))
m[4].metric("Sent to Telegram", sum(p["telegram_status"] == "sent" for p in potholes))

if shown:
    csv = pd.DataFrame([{
        "id": p["id"], "video": video_names.get(p["video_id"], ""), "time": fmt_time(p["best_time_s"]),
        "severity": p["severity"], "priority": p["priority"], "score": p["score"],
        "confidence": p["confidence"], "frames_seen": p["frames_seen"], "in_driving_path": bool(p["in_path"]),
        "review_status": p["review_status"], "review_note": p["review_note"] or "",
        "telegram_status": p["telegram_status"],
    } for p in shown]).to_csv(index=False).encode()
    st.download_button("Download as CSV", csv, "pothole_report.csv", "text/csv", icon=":material/download:")
else:
    st.info("No potholes match these filters.")

# ---------- One card per pothole ----------
for p in shown:
    pid = p["id"]
    with st.container(border=True):
        left, right = st.columns([3, 2])
        with left:
            st.image(abs_path(p["image_path"]), width="stretch")
        with right:
            st.markdown(
                f"### {pid}\n"
                f"{badge(p['severity'], SEVERITY_BADGE)} {badge(p['priority'], PRIORITY_BADGE)} "
                f"{badge(p['review_status'], REVIEW_BADGE)} {TELEGRAM_LABEL.get(p['telegram_status'], '')}"
            )
            st.markdown(
                f"**Video:** {video_names.get(p['video_id'], '')} at {fmt_time(p['best_time_s'])}  \n"
                f"**Seen:** {p['frames_seen']} frames ({fmt_time(p['first_seen_s'])} to {fmt_time(p['last_seen_s'])})  \n"
                f"**Confidence:** {p['confidence']:.0%}  \n"
                f"**In driving path:** {'Yes' if p['in_path'] else 'No'}"
            )
            with st.expander("Why this severity?"):
                st.markdown(
                    f"Severity score **{p['score']:.2f}** (Minor < 0.40 <= Moderate < 0.65 <= Critical)\n\n"
                    f"- Size on screen: {p['area_ratio']:.2%} of frame "
                    f"(distance-corrected {p['corrected_area']:.2%})\n"
                    f"- Darker than surrounding road: {p['dark_ratio']:.0%} of the pothole\n"
                    f"- Edge regularity (solidity): {p['solidity']:.2f} (lower = more ragged)\n"
                    f"- Visible in {p['frames_seen']} frames\n\n"
                    "This is an estimate from the image, not a physical depth measurement."
                )
                st.image(abs_path(p["crop_path"]), caption="Close-up", width=280)
            if p["telegram_status"] == "failed" and p["telegram_error"]:
                st.caption(f"Telegram error: {p['telegram_error']}")

        # Full-width action row so the buttons never get squeezed
        n_col, b1, b2, b3 = st.columns([3, 2, 2, 2], vertical_alignment="bottom")
        note = n_col.text_input("Reviewer note", value=p["review_note"] or "", key=f"note_{pid}",
                                placeholder="optional, e.g. 'shadow, not a pothole'")
        if b1.button("Approve", key=f"ok_{pid}", icon=":material/check:", width="stretch",
                     type="primary" if p["review_status"] != "Approved" else "secondary"):
            db.update_pothole(pid, review_status="Approved", review_note=note, reviewed_at=db.now())
            st.rerun()
        if b2.button("Reject", key=f"no_{pid}", icon=":material/close:", width="stretch"):
            db.update_pothole(pid, review_status="Rejected", review_note=note, reviewed_at=db.now())
            st.rerun()
        if b3.button("Resend", key=f"tg_{pid}", icon=":material/send:", width="stretch",
                     disabled=not config.telegram_configured(), help="Send this pothole to Telegram again"):
            ok, err = resend_pothole(pid)
            st.toast("Sent to Telegram" if ok else f"Telegram failed: {err}")
            st.rerun()
