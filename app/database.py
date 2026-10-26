"""SQLite persistence layer and deterministic demo data."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import DB_PATH as DEFAULT_DB_PATH

DB_PATH = DEFAULT_DB_PATH

ALLOWED_CATEGORIES = {
    "payment_access",
    "course_schedule",
    "technical_issue",
    "refund_policy",
    "other",
}
ALLOWED_PRIORITIES = {"low", "medium", "high"}


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    """Yield a short-lived SQLite connection and always close it."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables and insert sample records on the first run."""
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                student_id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS courses (
                course_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                level TEXT NOT NULL,
                start_date TEXT NOT NULL,
                duration_weeks INTEGER NOT NULL,
                description TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS enrollments (
                enrollment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL REFERENCES students(student_id),
                course_id TEXT NOT NULL REFERENCES courses(course_id),
                payment_status TEXT NOT NULL,
                enrollment_status TEXT NOT NULL,
                access_status TEXT NOT NULL,
                UNIQUE(student_id, course_id)
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_code TEXT NOT NULL UNIQUE,
                student_id TEXT NOT NULL REFERENCES students(student_id),
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tool_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        count = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO students(student_id, full_name, email) VALUES (?, ?, ?)",
                [
                    ("SV001", "Nguyen An", "an@example.test"),
                    ("SV002", "Tran Binh", "binh@example.test"),
                    ("SV003", "Le Chi", "chi@example.test"),
                ],
            )
            conn.executemany(
                """INSERT INTO courses
                   (course_id, title, level, start_date, duration_weeks, description)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (
                        "PY101",
                        "Python Beginner",
                        "Beginner",
                        "2026-11-02",
                        6,
                        "Python fundamentals, functions, files, and small projects.",
                    ),
                    (
                        "SQL101",
                        "SQL for Data Analysis",
                        "Beginner",
                        "2026-11-09",
                        4,
                        "SELECT, JOIN, aggregation, and practical analysis queries.",
                    ),
                    (
                        "ML201",
                        "Machine Learning Foundations",
                        "Intermediate",
                        "2026-11-16",
                        8,
                        "Data preparation, model evaluation, and classical ML workflows.",
                    ),
                ],
            )
            conn.executemany(
                """INSERT INTO enrollments
                   (student_id, course_id, payment_status, enrollment_status, access_status)
                   VALUES (?, ?, ?, ?, ?)""",
                [
                    ("SV001", "PY101", "paid", "active", "pending"),
                    ("SV002", "SQL101", "paid", "active", "active"),
                    ("SV003", "ML201", "pending", "pending", "not_activated"),
                ],
            )


def get_student(student_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT student_id, full_name, email FROM students WHERE student_id = ?",
            (student_id.strip().upper(),),
        ).fetchone()
    return dict(row) if row else None


def get_courses() -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT course_id, title, level, start_date, duration_weeks, description
               FROM courses ORDER BY start_date"""
        ).fetchall()
    return [dict(row) for row in rows]


def get_enrollment_status(student_id: str, course_id: str) -> dict[str, Any]:
    """Look up one student's enrollment, payment, and learning access."""
    with connection() as conn:
        row = conn.execute(
            """SELECT s.student_id, s.full_name, c.course_id, c.title,
                      c.start_date, e.payment_status, e.enrollment_status, e.access_status
               FROM enrollments e
               JOIN students s ON s.student_id = e.student_id
               JOIN courses c ON c.course_id = e.course_id
               WHERE e.student_id = ? AND e.course_id = ?""",
            (student_id.strip().upper(), course_id.strip().upper()),
        ).fetchone()
    if not row:
        return {
            "found": False,
            "student_id": student_id.strip().upper(),
            "course_id": course_id.strip().upper(),
            "message": "No enrollment record found for this student and course.",
        }
    result = dict(row)
    result["found"] = True
    return result


def get_course_schedule(course_id: str) -> dict[str, Any]:
    """Return the demo schedule details for a course."""
    with connection() as conn:
        row = conn.execute(
            """SELECT course_id, title, level, start_date, duration_weeks, description
               FROM courses WHERE course_id = ?""",
            (course_id.strip().upper(),),
        ).fetchone()
    if not row:
        return {
            "found": False,
            "course_id": course_id.strip().upper(),
            "message": "Course not found. Available course IDs are PY101, SQL101, and ML201.",
        }
    return {"found": True, **dict(row)}


def create_support_ticket(
    student_id: str,
    category: str,
    priority: str,
    summary: str,
) -> dict[str, Any]:
    """Create a support ticket after validating all input fields."""
    normalized_student_id = student_id.strip().upper()
    normalized_category = category.strip().lower().replace("-", "_").replace(" ", "_")
    normalized_priority = priority.strip().lower()

    category_aliases = {
        "payment": "payment_access",
        "billing": "payment_access",
        "access": "payment_access",
        "schedule": "course_schedule",
        "technical": "technical_issue",
        "refund": "refund_policy",
    }
    normalized_category = category_aliases.get(normalized_category, normalized_category)

    if normalized_category not in ALLOWED_CATEGORIES:
        normalized_category = "other"
    if normalized_priority not in ALLOWED_PRIORITIES:
        normalized_priority = "medium"
    if not summary or not summary.strip():
        return {"success": False, "error": "Ticket summary must not be empty."}
    student = get_student(normalized_student_id)
    if not student:
        return {"success": False, "error": "Unknown student ID."}

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ticket_code = f"EDU-{datetime.now(timezone.utc):%y%m%d}-{uuid.uuid4().hex[:5].upper()}"
    with connection() as conn:
        conn.execute(
            """INSERT INTO tickets
               (ticket_code, student_id, category, priority, summary, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?)""",
            (
                ticket_code,
                normalized_student_id,
                normalized_category,
                normalized_priority,
                summary.strip()[:500],
                now,
            ),
        )
    return {
        "success": True,
        "ticket_code": ticket_code,
        "student_id": normalized_student_id,
        "category": normalized_category,
        "priority": normalized_priority,
        "summary": summary.strip()[:500],
        "status": "open",
        "created_at": now,
    }


def list_tickets(student_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with connection() as conn:
        if student_id:
            rows = conn.execute(
                """SELECT ticket_code, student_id, category, priority, summary, status, created_at
                   FROM tickets WHERE student_id = ? ORDER BY id DESC LIMIT ?""",
                (student_id.strip().upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT ticket_code, student_id, category, priority, summary, status, created_at
                   FROM tickets ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def record_tool_event(
    request_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> None:
    with connection() as conn:
        conn.execute(
            """INSERT INTO tool_events
               (request_id, tool_name, arguments_json, result_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                request_id,
                tool_name,
                json.dumps(arguments, ensure_ascii=False, default=str),
                json.dumps(result, ensure_ascii=False, default=str),
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )


def list_tool_events(request_id: str) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT tool_name, arguments_json, result_json, created_at
               FROM tool_events WHERE request_id = ? ORDER BY id""",
            (request_id,),
        ).fetchall()

    events = []
    for row in rows:
        item = dict(row)
        item["arguments"] = json.loads(item.pop("arguments_json"))
        item["result"] = json.loads(item.pop("result_json"))
        events.append(item)
    return events
