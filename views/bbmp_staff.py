import streamlit as st

from src import complaints

st.title("BBMP Staff Dashboard")
st.caption("Review complaints, inspect pothole locations, and manage repairs and closure.")

complaints_list = complaints.list_complaints()
if not complaints_list:
    st.info("No complaints have been submitted yet.")
    st.stop()

status_filter = st.selectbox("Filter by status", ["All", "Registered", "Under Review", "Assigned", "In Repair", "Resolved", "Reopened", "Duplicate"])
filtered = complaints_list if status_filter == "All" else [c for c in complaints_list if c["status"] == status_filter]

for complaint in filtered:
    with st.container(border=True):
        st.markdown(f"### {complaint['complaint_id']} — {complaint['status']}")
        st.write(f"Citizen: {complaint['citizen_name']} | Phone: {complaint['citizen_phone'] or 'N/A'}")
        st.write(f"Location: {complaint['latitude']}, {complaint['longitude']} | Severity: {complaint['severity']}")
        st.write(f"Evidence type: {complaint['source_type']} | Last updated: {complaint['updated_at']}")

        evidence_rows = complaints.get_evidence(complaint['complaint_id'])
        for ev in evidence_rows:
            if ev["evidence_type"].lower() in {"png", "jpg", "jpeg"}:
                st.image(ev["file_path"], width=200)
            else:
                st.video(ev["file_path"])

        with st.form(f"staff_update_{complaint['complaint_id']}"):
            next_status = st.selectbox(
                "Update status",
                ["Registered", "Under Review", "Assigned", "In Repair", "Pending Review", "Resolved", "Reopened", "Duplicate"],
                index=["Registered", "Under Review", "Assigned", "In Repair", "Pending Review", "Resolved", "Reopened", "Duplicate"].index(complaint["status"]) if complaint["status"] in ["Registered", "Under Review", "Assigned", "In Repair", "Pending Review", "Resolved", "Reopened", "Duplicate"] else 0,
                key=f"status_{complaint['complaint_id']}",
            )
            notes = st.text_area("Staff notes", key=f"notes_{complaint['complaint_id']}")
            submitted = st.form_submit_button("Save status")
            if submitted:
                complaints.update_status(complaint['complaint_id'], next_status, changed_by="staff", notes=notes)
                st.success(f"Status updated to {next_status}.")
                st.rerun()

        st.subheader("Repair record")
        repair_form = st.form(f"repair_form_{complaint['complaint_id']}")
        with repair_form:
            staff_id = st.text_input("Staff ID", key=f"staff_id_{complaint['complaint_id']}")
            before_photo = st.file_uploader("Before repair photo", type=["png", "jpg", "jpeg"], key=f"before_{complaint['complaint_id']}")
            after_photo = st.file_uploader("After repair photo", type=["png", "jpg", "jpeg"], key=f"after_{complaint['complaint_id']}")
            repair_description = st.text_area("Repair description", key=f"repair_desc_{complaint['complaint_id']}")
            if st.form_submit_button("Save repair update"):
                if not before_photo or not after_photo or not repair_description:
                    st.warning("Before photo, after photo, and repair description are required for a repair record.")
                else:
                    before_path = f"data/uploads/{complaint['complaint_id']}_before.jpg"
                    after_path = f"data/uploads/{complaint['complaint_id']}_after.jpg"
                    with open(before_path, "wb") as f:
                        f.write(before_photo.getbuffer())
                    with open(after_path, "wb") as f:
                        f.write(after_photo.getbuffer())
                    complaints.add_repair(
                        complaint_id=complaint['complaint_id'],
                        staff_id=staff_id or "staff",
                        before_photo_path=before_path,
                        after_photo_path=after_path,
                        repair_description=repair_description,
                    )
                    complaints.update_status(complaint['complaint_id'], "In Repair", changed_by="staff", notes="Repair work recorded.")
                    st.success("Repair update saved.")
                    st.rerun()

        repairs = complaints.get_repairs(complaint['complaint_id'])
        if repairs:
            st.write("Repair history:")
            for repair in repairs:
                st.write(f"- {repair['repair_date']}: {repair['repair_description']}")
                if repair.get("after_photo_path"):
                    st.image(repair["after_photo_path"], caption="Repair image")

        if complaint["status"] == "Resolved":
            feedbacks = complaints.get_feedback(complaint['complaint_id'])
            if feedbacks:
                st.write("Citizen feedback:")
                for item in feedbacks:
                    st.write(f"- {item['choice']}: {item['reason']}")

        if st.button("Mark resolved", key=f"resolve_{complaint['complaint_id']}"):
            complaints.mark_resolved(complaint['complaint_id'], changed_by="staff")
            st.success("Complaint marked as resolved.")
            st.rerun()

        st.divider()
