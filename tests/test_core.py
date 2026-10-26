from __future__ import annotations

from app import database
from app.knowledge_base import KnowledgeBase


def test_seed_data_contains_demo_courses(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "demo.db")
    database.init_db()

    courses = database.get_courses()
    course_ids = {course["course_id"] for course in courses}

    assert {"PY101", "SQL101", "ML201"}.issubset(course_ids)


def test_enrollment_status_finds_paid_but_pending_access(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "demo.db")
    database.init_db()

    status = database.get_enrollment_status("SV001", "PY101")

    assert status["found"] is True
    assert status["payment_status"] == "paid"
    assert status["access_status"] == "pending"


def test_create_ticket_and_list_it(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "demo.db")
    database.init_db()

    created = database.create_support_ticket(
        "SV001",
        "payment_access",
        "high",
        "Paid but course access is still pending.",
    )
    tickets = database.list_tickets(student_id="SV001")

    assert created["success"] is True
    assert created["ticket_code"].startswith("EDU-")
    assert len(tickets) == 1
    assert tickets[0]["category"] == "payment_access"


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
