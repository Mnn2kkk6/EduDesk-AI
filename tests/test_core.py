from __future__ import annotations

from app import database
from app.knowledge_base import KnowledgeBase


def test_seed_data_contains_demo_courses(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "demo.db")
    database.init_db()

    courses = database.get_courses()
    course_ids = {course["course_id"] for course in courses}

    assert {"PY101", "SQL101", "ML201"}.issubset(course_ids)
    assert len(database.get_students()) == 3
    assert len(database.get_enrollments()) == 3


def test_enrollment_status_finds_paid_but_pending_access(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "demo.db")
    database.init_db()

    status = database.get_enrollment_status("SV001", "PY101")

    assert status["found"] is True
    assert status["payment_status"] == "paid"
    assert status["access_status"] == "pending"


def test_demo_ticket_data_is_seeded_and_specific(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "demo.db")
    database.init_db()

    tickets = database.list_tickets(limit=500)
    sample = next(ticket for ticket in tickets if ticket["ticket_code"] == "EDU-DEMO-001")

    assert len(tickets) >= 4
    assert sample["title"] == "Đã thanh toán nhưng chưa được mở khóa PY101"
    assert sample["full_name"] == "Nguyen An"
    assert sample["course_id"] == "PY101"
    assert sample["payment_status"] == "paid"
    assert sample["access_status"] == "pending"
    assert sample["status"] == "open"


def test_create_ticket_and_list_it(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "demo.db")
    database.init_db()

    created = database.create_support_ticket(
        "SV001",
        "payment_access",
        "high",
        "Payment is complete but course access is still pending for PY101.",
    )
    tickets = database.list_tickets(student_id="SV001")

    assert created["success"] is True
    assert created["ticket_code"].startswith("EDU-")
    assert created["course_id"] == "PY101"
    assert "PY101" in created["title"]
    assert any(ticket["ticket_code"] == created["ticket_code"] for ticket in tickets)


def test_ticket_status_update_adds_history(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "demo.db")
    database.init_db()

    updated = database.update_ticket_status(
        "EDU-DEMO-001",
        "in_progress",
        "Đã tiếp nhận và đang đối chiếu giao dịch thanh toán.",
    )
    events = database.list_ticket_events("EDU-DEMO-001")

    assert updated is not None
    assert updated["status"] == "in_progress"
    assert events[-1]["previous_status"] == "open"
    assert events[-1]["new_status"] == "in_progress"
    assert "đối chiếu giao dịch" in events[-1]["note"]


def test_tfidf_retriever_returns_relevant_source(tmp_path):
    docs = tmp_path / "knowledge"
    docs.mkdir()
    (docs / "refund.md").write_text(
        "Refund requests must be submitted within seven days of payment.",
        encoding="utf-8",
    )
    (docs / "schedule.md").write_text(
        "The Python beginner course starts on 2 November and lasts six weeks.",
        encoding="utf-8",
    )
    kb = KnowledgeBase([docs])

    results = kb.search("How many days are allowed for a refund?", top_k=2)

    assert results
    assert results[0]["source"] == "refund.md"
    assert results[0]["score"] > 0
