import streamlit as st

from src import complaints

st.title("Citizen Complaint Portal")
st.caption("Report a pothole, check if it was already logged, and track the complaint to resolution.")

with st.form("citizen_complaint_form"):
    col1, col2 = st.columns(2)
    with col1:
        citizen_name = st.text_input("Citizen name")
        citizen_phone = st.text_input("Phone number")
        latitude = st.number_input("Latitude", format="%.6f", step=0.000001, value=12.9716)
    with col2:
        severity = st.selectbox("Severity", ["Minor", "Moderate", "Critical"])
        source_type = st.selectbox("Evidence type", ["photo", "video"])
        longitude = st.number_input("Longitude", format="%.6f", step=0.000001, value=77.5946)

    location_label = st.text_input("Location label (optional)")
    evidence = st.file_uploader("Upload a photo or video", type=["png", "jpg", "jpeg", "mp4", "mov"], key="citizen_evidence")
    submitted = st.form_submit_button("Submit complaint")

if submitted:
    if not citizen_name or not evidence:
        st.error("Name and evidence are required before submitting a complaint.")
        st.stop()

    path = f"data/uploads/{evidence.name}"
    with open(path, "wb") as f:
        f.write(evidence.getbuffer())

    complaint = complaints.register_complaint(
        citizen_name=citizen_name,
        citizen_phone=citizen_phone,
        latitude=float(latitude),
        longitude=float(longitude),
        severity=severity,
        source_type=source_type,
        evidence_path=path,
        location_label=location_label or "Citizen submitted report",
    )

    if complaint.get("is_duplicate"):
        st.warning("This pothole has already been reported. Your evidence has been linked to the existing complaint.")
    st.success(f"Complaint created or linked: {complaint.get('complaint_id')}")
    if complaint.get("status"):
        st.write(f"Status: {complaint['status']}")

st.divider()
all_complaints = complaints.list_complaints()
if not all_complaints:
    st.info("No complaints have been submitted yet.")
else:
    for complaint in all_complaints:
        with st.container(border=True):
            st.markdown(f"### {complaint['complaint_id']} — {complaint['status']}")
            st.write(f"Citizen: {complaint['citizen_name']} | Severity: {complaint['severity']}")
            st.write(f"Location: {complaint['latitude']}, {complaint['longitude']}")
            evidence_rows = complaints.get_evidence(complaint['complaint_id'])
            if evidence_rows:
                for ev in evidence_rows[-3:]:
                    if ev["evidence_type"].lower() in {"png", "jpg", "jpeg"}:
                        st.image(ev["file_path"], width=200)
                    else:
                        st.video(ev["file_path"])

            if complaint["status"] == "Resolved":
                repairs = complaints.get_repairs(complaint['complaint_id'])
                if repairs:
                    last_repair = repairs[-1]
                    if last_repair.get("after_photo_path"):
                        st.image(last_repair["after_photo_path"], caption="After repair")
                    st.write(last_repair.get("repair_description", ""))

                feedback_choice = st.radio(
                    "How is the repair?",
                    ["Problem solved", "Problem not solved"],
                    key=f"feedback_{complaint['complaint_id']}",
                    horizontal=True,
                )
                if st.button("Submit feedback", key=f"submit_feedback_{complaint['complaint_id']}"):
                    reason = st.text_input("Reason", key=f"reason_{complaint['complaint_id']}")
                    new_upload = st.file_uploader("New evidence if not solved", type=["png", "jpg", "jpeg", "mp4", "mov"], key=f"reopen_evidence_{complaint['complaint_id']}")
                    if feedback_choice == "Problem not solved" and new_upload is not None:
                        file_path = f"data/uploads/{new_upload.name}"
                        with open(file_path, "wb") as f:
                            f.write(new_upload.getbuffer())
                        complaints.submit_feedback(
                            complaint_id=complaint['complaint_id'],
                            citizen_name=complaint['citizen_name'],
                            choice=feedback_choice,
                            reason=reason,
                            new_evidence_path=file_path,
                        )
                        st.success("Complaint reopened and sent back to BBMP staff.")
                        st.rerun()
                    elif feedback_choice == "Problem solved":
                        complaints.submit_feedback(
                            complaint_id=complaint['complaint_id'],
                            citizen_name=complaint['citizen_name'],
                            choice=feedback_choice,
                            reason=reason,
                        )
                        st.success("Thanks for the feedback.")
                        st.rerun()
                    else:
                        st.warning("Please attach a new photo or video before marking the issue as not solved.")
