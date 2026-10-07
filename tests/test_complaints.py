from src import complaints, config


def test_duplicate_location_reuses_existing_complaint(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "complaints.db")
    complaints.init_db()

    first = complaints.register_complaint(
        citizen_name="Alice",
        citizen_phone="9999999999",
        latitude=12.9716,
        longitude=77.5946,
        severity="Moderate",
        source_type="photo",
        evidence_path="/tmp/photo1.jpg",
    )

    second = complaints.register_complaint(
        citizen_name="Bob",
        citizen_phone="8888888888",
        latitude=12.97162,
        longitude=77.59462,
        severity="Critical",
        source_type="video",
        evidence_path="/tmp/video1.mp4",
    )

    assert first["complaint_id"] == second["complaint_id"]
    assert second["duplicate_of"] == first["complaint_id"]
    assert second["status"] == "Duplicate"
    assert len(complaints.list_complaints()) == 1


def test_repair_and_reopen_workflow(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "complaints2.db")
    complaints.init_db()

    complaint = complaints.register_complaint(
        citizen_name="Charlie",
        citizen_phone="7777777777",
        latitude=12.9,
        longitude=77.5,
        severity="Minor",
        source_type="photo",
        evidence_path="/tmp/before.jpg",
    )

    complaints.update_status(complaint["complaint_id"], "In Repair", changed_by="staff_01")
    complaints.add_repair(
        complaint_id=complaint["complaint_id"],
        staff_id="staff_01",
        before_photo_path="/tmp/before.jpg",
        after_photo_path="/tmp/after.jpg",
        repair_description="Filled pothole and patched road surface.",
    )
    complaints.mark_resolved(complaint["complaint_id"], changed_by="staff_01")

    complaints.submit_feedback(
        complaint_id=complaint["complaint_id"],
        citizen_name="Charlie",
        choice="Problem not solved",
        reason="Pothole came back after rain.",
        new_evidence_path="/tmp/reopen.jpg",
    )

    reopened = complaints.get_complaint(complaint["complaint_id"])
    assert reopened["status"] == "Reopened"
    assert reopened["reopened_count"] == 1
    assert len(complaints.list_status_history(complaint["complaint_id"])) >= 3
