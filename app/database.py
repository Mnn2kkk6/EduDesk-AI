"""SQLite persistence, fictional seed data, support tickets, and audit events."""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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
ALLOWED_TICKET_STATUSES = {"open", "in_progress", "resolved"}

CATEGORY_TITLES = {
    "payment_access": "Kiểm tra thanh toán / quyền truy cập",
    "course_schedule": "Xác nhận lịch học",
    "technical_issue": "Hỗ trợ sự cố kỹ thuật",
    "refund_policy": "Tư vấn chính sách hoàn học phí",
    "other": "Yêu cầu hỗ trợ học tập",
}


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _event(
    conn: sqlite3.Connection,
    ticket_code: str,
    previous_status: str | None,
    new_status: str,
    note: str,
) -> None:
    conn.execute(
        """INSERT INTO ticket_events
           (ticket_code, previous_status, new_status, note, actor, created_at)
           VALUES (?, ?, ?, ?, 'EduDesk Demo', ?)""",
        (ticket_code, previous_status, new_status, note, _now_iso()),
    )


def init_db() -> None:
    """Create/migrate schema and seed fictional courses, enrollments, and tickets."""
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

            CREATE TABLE IF NOT EXISTS ticket_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_code TEXT NOT NULL,
                previous_status TEXT,
                new_status TEXT NOT NULL,
                note TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        # Add fields to existing local databases created by an earlier version.
        ticket_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(tickets)").fetchall()
        }
        if "title" not in ticket_columns:
            conn.execute("ALTER TABLE tickets ADD COLUMN title TEXT NOT NULL DEFAULT ''")
        if "course_id" not in ticket_columns:
            conn.execute("ALTER TABLE tickets ADD COLUMN course_id TEXT")
        if "updated_at" not in ticket_columns:
            conn.execute("ALTER TABLE tickets ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")

        student_count = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        if student_count == 0:
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

        # Backfill fields for tickets created by the first MVP version.
        conn.execute(
            """UPDATE tickets
               SET title = CASE category
                   WHEN 'payment_access' THEN 'Kiểm tra thanh toán / quyền truy cập'
                   WHEN 'course_schedule' THEN 'Xác nhận lịch học'
                   WHEN 'technical_issue' THEN 'Hỗ trợ sự cố kỹ thuật'
                   WHEN 'refund_policy' THEN 'Tư vấn chính sách hoàn học phí'
                   ELSE 'Yêu cầu hỗ trợ học tập'
               END
               WHERE title IS NULL OR title = ''"""
        )
        conn.execute(
            """UPDATE tickets
               SET course_id = (
                   SELECT e.course_id FROM enrollments e
                   WHERE e.student_id = tickets.student_id
                   ORDER BY CASE WHEN e.enrollment_status = 'active' THEN 0 ELSE 1 END
                   LIMIT 1
               )
               WHERE course_id IS NULL OR course_id = ''"""
        )
        conn.execute(
            "UPDATE tickets SET updated_at = created_at WHERE updated_at IS NULL OR updated_at = ''"
        )

        # Seed illustrative tickets independently of student seeding, so existing databases
        # from the first MVP also get a populated dashboard on their next startup.
        ticket_count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        if ticket_count == 0:
            now = datetime.now(timezone.utc)
            examples = [
                {
                    "ticket_code": "EDU-DEMO-001",
                    "student_id": "SV001",
                    "category": "payment_access",
                    "priority": "high",
                    "title": "Đã thanh toán nhưng chưa được mở khóa PY101",
                    "course_id": "PY101",
                    "summary": (
                        "Sinh viên xác nhận đã thanh toán khóa Python Beginner. "
                        "Bản ghi enrollment có payment_status=paid nhưng access_status=pending. "
                        "Cần đối chiếu trạng thái giao dịch và đồng bộ quyền truy cập trước khi đóng ticket."
                    ),
                    "status": "open",
                    "hours_ago": 1,
                    "note": "Ticket mẫu: cần kiểm tra chênh lệch giữa thanh toán và quyền truy cập.",
                },
                {
                    "ticket_code": "EDU-DEMO-002",
                    "student_id": "SV002",
                    "category": "technical_issue",
                    "priority": "medium",
                    "title": "Không thấy bài tập tuần 1 trên LMS",
                    "course_id": "SQL101",
                    "summary": (
                        "Sinh viên đã đăng ký SQL for Data Analysis và quyền truy cập đang active, "
                        "nhưng phản ánh mục bài tập tuần 1 không xuất hiện. Cần kiểm tra cấu hình "
                        "nội dung khóa học và yêu cầu sinh viên đăng xuất/đăng nhập lại nếu phù hợp."
                    ),
                    "status": "in_progress",
                    "hours_ago": 5,
                    "note": "Ticket mẫu: đã tiếp nhận, đang kiểm tra cấu hình nội dung LMS.",
                },
                {
                    "ticket_code": "EDU-DEMO-003",
                    "student_id": "SV003",
                    "category": "payment_access",
                    "priority": "medium",
                    "title": "Xác nhận trạng thái thanh toán ML201",
                    "course_id": "ML201",
                    "summary": (
                        "Bản ghi demo của sinh viên đang hiển thị payment_status=pending, "
                        "enrollment_status=pending và access_status=not_activated. Cần xác nhận "
                        "sinh viên đã hoàn tất thanh toán hay chưa trước khi cấp quyền truy cập."
                    ),
                    "status": "open",
                    "hours_ago": 9,
                    "note": "Ticket mẫu: chờ xác nhận thanh toán; chưa được tự động cấp quyền truy cập.",
                },
                {
                    "ticket_code": "EDU-DEMO-004",
                    "student_id": "SV002",
                    "category": "course_schedule",
                    "priority": "low",
                    "title": "Xác nhận ngày khai giảng SQL101",
                    "course_id": "SQL101",
                    "summary": (
                        "Sinh viên muốn xác nhận lịch học SQL for Data Analysis. "
                        "Dữ liệu khóa học ghi ngày khai giảng dự kiến 09/11/2026, thời lượng 4 tuần. "
                        "Đã trả lời dựa trên dữ liệu lịch học trong hệ thống demo."
                    ),
                    "status": "resolved",
                    "hours_ago": 28,
                    "note": "Ticket mẫu: đã xác nhận ngày khai giảng theo dữ liệu khóa học.",
                },
            ]
            for item in examples:
                created_at = (now - timedelta(hours=item.pop("hours_ago"))).isoformat(timespec="seconds")
                conn.execute(
                    """INSERT INTO tickets
                       (ticket_code, student_id, category, priority, title, course_id,
                        summary, status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item["ticket_code"],
                        item["student_id"],
                        item["category"],
                        item["priority"],
                        item["title"],
                        item["course_id"],
                        item["summary"],
                        item["status"],
                        created_at,
                        created_at,
                    ),
                )
                _event(
                    conn,
                    item["ticket_code"],
                    None,
                    item["status"],
                    item["note"],
                )


def get_student(student_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT student_id, full_name, email FROM students WHERE student_id = ?",
            (student_id.strip().upper(),),
        ).fetchone()
    return dict(row) if row else None


def get_students() -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT student_id, full_name, email FROM students ORDER BY student_id"
        ).fetchall()
    return [dict(row) for row in rows]


def get_courses() -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT course_id, title, level, start_date, duration_weeks, description
               FROM courses ORDER BY start_date"""
        ).fetchall()
    return [dict(row) for row in rows]


def get_enrollments() -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT e.student_id, s.full_name, e.course_id, c.title AS course_title,
                      e.payment_status, e.enrollment_status, e.access_status, c.start_date
               FROM enrollments e
               JOIN students s ON s.student_id = e.student_id
               JOIN courses c ON c.course_id = e.course_id
               ORDER BY e.student_id, e.course_id"""
        ).fetchall()
    return [dict(row) for row in rows]


def get_data_counts() -> dict[str, int]:
    with connection() as conn:
        return {
            "students": conn.execute("SELECT COUNT(*) FROM students").fetchone()[0],
            "courses": conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
            "enrollments": conn.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0],
            "tickets": conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0],
        }


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


def _infer_course_id(summary: str, student_id: str) -> str | None:
    match = re.search(r"\b(PY|SQL|ML)\s?-?\s?(\d{3})\b", summary.upper())
    if match:
        return f"{match.group(1)}{match.group(2)}"
    with connection() as conn:
        row = conn.execute(
            """SELECT course_id FROM enrollments WHERE student_id = ?
               ORDER BY CASE WHEN enrollment_status = 'active' THEN 0 ELSE 1 END LIMIT 1""",
            (student_id,),
        ).fetchone()
    return row["course_id"] if row else None


def create_support_ticket(
    student_id: str,
    category: str,
    priority: str,
    summary: str,
    course_id: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Create a support ticket with a specific title, course, detail, and audit event."""
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

    normalized_course = (course_id or "").strip().upper() or _infer_course_id(
        summary, normalized_student_id
    )
    if normalized_course:
        course = get_course_schedule(normalized_course)
        if not course.get("found"):
            normalized_course = None
    default_title = CATEGORY_TITLES[normalized_category]
    if normalized_course:
        default_title = f"{default_title}: {normalized_course}"
    normalized_title = (title or default_title).strip()[:160]
    detail = summary.strip()[:1500]
    now = _now_iso()
    ticket_code = f"EDU-{datetime.now(timezone.utc):%y%m%d}-{uuid.uuid4().hex[:5].upper()}"

    with connection() as conn:
        conn.execute(
            """INSERT INTO tickets
               (ticket_code, student_id, category, priority, title, course_id,
                summary, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
            (
                ticket_code,
                normalized_student_id,
                normalized_category,
                normalized_priority,
                normalized_title,
                normalized_course,
                detail,
                now,
                now,
            ),
        )
        _event(conn, ticket_code, None, "open", "Ticket được tạo bởi EduDesk AI.")

    return {
        "success": True,
        "ticket_code": ticket_code,
        "student_id": normalized_student_id,
        "category": normalized_category,
        "priority": normalized_priority,
        "title": normalized_title,
        "course_id": normalized_course,
        "summary": detail,
        "status": "open",
        "created_at": now,
    }


def list_tickets(
    student_id: str | None = None,
    limit: int = 100,
    status: str | None = None,
    priority: str | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    sql = """SELECT t.ticket_code, t.student_id, s.full_name, s.email,
                    t.category, t.priority, t.title, t.course_id,
                    c.title AS course_title, t.summary, t.status,
                    t.created_at, t.updated_at,
                    e.payment_status, e.enrollment_status, e.access_status
             FROM tickets t
             JOIN students s ON s.student_id = t.student_id
             LEFT JOIN courses c ON c.course_id = t.course_id
             LEFT JOIN enrollments e ON e.student_id = t.student_id AND e.course_id = t.course_id
             WHERE 1=1"""
    params: list[Any] = []
    if student_id:
        sql += " AND t.student_id = ?"
        params.append(student_id.strip().upper())
    if status:
        sql += " AND t.status = ?"
        params.append(status)
    if priority:
        sql += " AND t.priority = ?"
        params.append(priority)
    sql += " ORDER BY t.id DESC LIMIT ?"
    params.append(limit)
    with connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_ticket(ticket_code: str) -> dict[str, Any] | None:
    rows = list_tickets(limit=500)
    normalized_code = ticket_code.strip().upper()
    return next(
        (ticket for ticket in rows if ticket["ticket_code"].upper() == normalized_code),
        None,
    )


def list_ticket_events(ticket_code: str) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT previous_status, new_status, note, actor, created_at
               FROM ticket_events WHERE ticket_code = ? ORDER BY id""",
            (ticket_code.strip().upper(),),
        ).fetchall()
    return [dict(row) for row in rows]


def update_ticket_status(
    ticket_code: str,
    new_status: str,
    note: str = "",
) -> dict[str, Any] | None:
    normalized_code = ticket_code.strip().upper()
    normalized_status = new_status.strip().lower()
    if normalized_status not in ALLOWED_TICKET_STATUSES:
        raise ValueError(f"Unsupported status: {new_status}")

    with connection() as conn:
        current = conn.execute(
            "SELECT status FROM tickets WHERE ticket_code = ?",
            (normalized_code,),
        ).fetchone()
        if not current:
            return None
        old_status = current["status"]
        now = _now_iso()
        conn.execute(
            "UPDATE tickets SET status = ?, updated_at = ? WHERE ticket_code = ?",
            (normalized_status, now, normalized_code),
        )
        event_note = note.strip()[:500] or f"Trạng thái được cập nhật: {old_status} → {normalized_status}."
        _event(conn, normalized_code, old_status, normalized_status, event_note)

    return get_ticket(normalized_code)


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
                _now_iso(),
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
