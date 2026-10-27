"""Streamlit UI for the EduDesk AI student support demo."""
from __future__ import annotations

import json
import os

import requests
import streamlit as st
from dotenv import load_dotenv

from app.config import API_URL

load_dotenv()
st.set_page_config(page_title="EduDesk AI", page_icon="🎓", layout="wide")

API_BASE = os.getenv("EDUDESK_API_URL", API_URL).rstrip("/")
STUDENT_OPTIONS = {
    "SV001 — Nguyen An (đã thanh toán, chưa có quyền truy cập)": "SV001",
    "SV002 — Tran Binh (đang học SQL101)": "SV002",
    "SV003 — Le Chi (chưa hoàn tất thanh toán ML201)": "SV003",
}
STATUS_LABELS = {
    "open": "Mới / Chờ xử lý",
    "in_progress": "Đang xử lý",
    "resolved": "Đã giải quyết",
}
PRIORITY_LABELS = {"high": "Cao", "medium": "Trung bình", "low": "Thấp"}
CATEGORY_LABELS = {
    "payment_access": "Thanh toán / quyền truy cập",
    "course_schedule": "Lịch học",
    "technical_issue": "Sự cố kỹ thuật",
    "refund_policy": "Hoàn học phí",
    "other": "Khác",
}


def api_get(path: str, timeout: int = 8, params: dict | None = None):
    return requests.get(f"{API_BASE}{path}", timeout=timeout, params=params)


def render_sources(sources: list[dict]) -> None:
    if not sources:
        st.caption("Không có đoạn tài liệu liên quan đủ điểm để hiển thị.")
        return
    with st.expander(f"Nguồn RAG ({len(sources)} đoạn)", expanded=False):
        for number, source in enumerate(sources, start=1):
            page = f", trang {source['page']}" if source.get("page") else ""
            st.markdown(
                f"**{number}. {source.get('source', 'unknown')}{page}** "
                f"· relevance {source.get('score', 0):.3f}"
            )
            st.write(source.get("text", ""))
            st.divider()


def render_tool_calls(tool_calls: list[dict]) -> None:
    if not tool_calls:
        return
    with st.expander(f"Agent trace — {len(tool_calls)} tool call(s)", expanded=False):
        for call in tool_calls:
            st.markdown(f"**{call.get('tool_name')}**")
            st.caption(call.get("created_at", ""))
            st.code(
                json.dumps(
                    {"arguments": call.get("arguments"), "result": call.get("result")},
                    ensure_ascii=False,
                    indent=2,
                ),
                language="json",
            )


def format_status(value: str | None) -> str:
    return STATUS_LABELS.get(value or "", value or "Chưa có")


def format_priority(value: str | None) -> str:
    return PRIORITY_LABELS.get(value or "", value or "Chưa có")


def suggested_next_action(ticket: dict) -> str:
    category = ticket.get("category")
    if category == "payment_access":
        if ticket.get("payment_status") == "paid" and ticket.get("access_status") != "active":
            return (
                "Đối chiếu trạng thái thanh toán với bản ghi enrollment, sau đó kiểm tra đồng bộ "
                "quyền truy cập. Chỉ đóng ticket khi quyền truy cập đã được xác nhận."
            )
        if ticket.get("payment_status") == "pending":
            return (
                "Xác minh trạng thái giao dịch trước khi cấp quyền học. Không tự động mở khóa "
                "khi dữ liệu thanh toán vẫn pending."
            )
        return "Kiểm tra thông tin thanh toán và trạng thái truy cập trong hệ thống."
    if category == "technical_issue":
        return (
            "Tái hiện lỗi, kiểm tra cấu hình nội dung khóa học và ghi lại kết quả kiểm tra trước "
            "khi chuyển ticket sang Đã giải quyết."
        )
    if category == "course_schedule":
        return "Đối chiếu ngày khai giảng và thời lượng trong danh mục khóa học, sau đó phản hồi sinh viên."
    if category == "refund_policy":
        return "Đối chiếu ngày thanh toán và tiến độ học với chính sách mẫu; chuyển nhân viên kiểm tra nếu thiếu dữ liệu."
    return "Đọc mô tả yêu cầu, kiểm tra dữ liệu liên quan và cập nhật tiến độ cho sinh viên."


def sla_target(priority: str) -> str:
    targets = {
        "high": "1 ngày làm việc",
        "medium": "2 ngày làm việc",
        "low": "3 ngày làm việc",
    }
    return targets.get(priority, "Chưa xác định") + " (SLA minh họa của demo)"


st.title("🎓 EduDesk AI")
st.caption("Student Support & Workflow Agent · RAG · Tool Calling · SQLite")

with st.sidebar:
    st.header("Demo settings")
    selected_label = st.selectbox("Sinh viên đang mô phỏng", list(STUDENT_OPTIONS))
    student_id = STUDENT_OPTIONS[selected_label]
    st.caption(f"Student ID: {student_id}")
    try:
        health_response = api_get("/api/v1/health")
        health_response.raise_for_status()
        health = health_response.json()
        if health.get("llm_configured"):
            st.success("Gemini API đã cấu hình")
        else:
            st.info("Demo Mode: RAG + tool rules, chưa cần API key")
        counts = health.get("data_counts", {})
        st.caption(
            f"Dữ liệu: {counts.get('students', 0)} sinh viên · "
            f"{counts.get('courses', 0)} khóa học · "
            f"{counts.get('enrollments', 0)} đăng ký · "
            f"{counts.get('tickets', 0)} ticket"
        )
        st.caption(f"Indexed chunks: {health.get('retrieval_chunks', 0)}")
    except requests.RequestException:
        st.error("Không kết nối được FastAPI")
        st.code("uvicorn app.main:app --reload", language="powershell")
        st.caption(f"API URL: {API_BASE}")

chat_tab, tickets_tab, data_tab, documents_tab = st.tabs(
    ["💬 Trợ lý AI", "🎫 Ticket dashboard", "🗂️ Dữ liệu demo", "📚 Tài liệu"]
)

with chat_tab:
    st.markdown(
        "Hỏi về chính sách, lịch học hoặc trạng thái đăng ký. "
        "Agent có thể tra cứu database và tạo ticket khi điều kiện phù hợp."
    )
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("mode"):
                if message["mode"] == "gemini":
                    st.caption("Đã dùng Gemini API")
                elif message["mode"] == "demo_fallback_after_api_error":
                    st.caption("Demo fallback sau lỗi API")
                else:
                    st.caption("Demo Mode — rule-based fallback")
            if message.get("warning"):
                st.warning(message["warning"])
            if message.get("sources"):
                render_sources(message["sources"])
            if message.get("tool_calls"):
                render_tool_calls(message["tool_calls"])

    prompt = st.chat_input("Ví dụ: Em đã thanh toán PY101 nhưng chưa truy cập được...")
    if prompt:
        prior_history = [
            {"role": item["role"], "content": item["content"]}
            for item in st.session_state.messages[-6:]
            if item["role"] in {"user", "assistant"}
        ]
        st.session_state.messages.append({"role": "user", "content": prompt})
        try:
            response = requests.post(
                f"{API_BASE}/api/v1/chat",
                json={
                    "student_id": student_id,
                    "message": prompt,
                    "history": prior_history,
                },
                timeout=120,
            )
            response.raise_for_status()
            payload = response.json()
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": payload.get("answer", "Không có câu trả lời."),
                    "mode": payload.get("mode"),
                    "warning": payload.get("warning"),
                    "sources": payload.get("sources", []),
                    "tool_calls": payload.get("tool_calls", []),
                }
            )
        except requests.HTTPError as exc:
            detail = exc.response.text[:500] if exc.response is not None else str(exc)
            st.session_state.messages.append(
                {"role": "assistant", "content": f"API trả về lỗi: {detail}"}
            )
        except requests.RequestException as exc:
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": f"Không gọi được backend tại {API_BASE}. Hãy kiểm tra terminal chạy FastAPI. Chi tiết: {exc}",
                }
            )
        st.rerun()

    if st.button("Xóa hội thoại", key="clear_chat"):
        st.session_state.messages = []
        st.rerun()

with tickets_tab:
    st.subheader("Ticket hỗ trợ")
    st.caption(
        "Ticket demo đã được nạp sẵn để bạn có thể xem dashboard ngay khi khởi động. "
        "Các ticket và quy trình xử lý đều dùng dữ liệu giả lập."
    )
    try:
        all_response = api_get("/api/v1/tickets", params={"limit": 500})
        all_response.raise_for_status()
        all_tickets = all_response.json().get("tickets", [])
        total = len(all_tickets)
        open_count = sum(ticket["status"] == "open" for ticket in all_tickets)
        progress_count = sum(ticket["status"] == "in_progress" for ticket in all_tickets)
        resolved_count = sum(ticket["status"] == "resolved" for ticket in all_tickets)
        high_count = sum(ticket["priority"] == "high" for ticket in all_tickets)

        metric_cols = st.columns(5)
        metric_cols[0].metric("Tổng ticket", total)
        metric_cols[1].metric("Chờ xử lý", open_count)
        metric_cols[2].metric("Đang xử lý", progress_count)
        metric_cols[3].metric("Đã giải quyết", resolved_count)
        metric_cols[4].metric("Ưu tiên cao", high_count)

        filter_cols = st.columns([1.2, 1.0, 1.2, 1.0])
        status_filter_label = filter_cols[0].selectbox(
            "Trạng thái",
            ["Tất cả"] + list(STATUS_LABELS.values()),
        )
        priority_filter_label = filter_cols[1].selectbox(
            "Mức ưu tiên",
            ["Tất cả"] + list(PRIORITY_LABELS.values()),
        )
        student_filter = filter_cols[2].selectbox(
            "Sinh viên",
            ["Tất cả"] + list(STUDENT_OPTIONS.values()),
            format_func=lambda sid: "Tất cả sinh viên" if sid == "Tất cả" else sid,
        )
        filter_cols[3].write("")
        filter_cols[3].write("")
        if filter_cols[3].button("Làm mới dữ liệu", use_container_width=True):
            st.rerun()

        query_params: dict[str, str | int] = {"limit": 500}
        status_reverse = {label: key for key, label in STATUS_LABELS.items()}
        priority_reverse = {label: key for key, label in PRIORITY_LABELS.items()}
        if status_filter_label != "Tất cả":
            query_params["status"] = status_reverse[status_filter_label]
        if priority_filter_label != "Tất cả":
            query_params["priority"] = priority_reverse[priority_filter_label]
        if student_filter != "Tất cả":
            query_params["student_id"] = student_filter

        filtered_response = api_get("/api/v1/tickets", params=query_params)
        filtered_response.raise_for_status()
        visible_tickets = filtered_response.json().get("tickets", [])

        if visible_tickets:
            st.markdown("#### Danh sách ticket")
            ticket_table = [
                {
                    "Mã ticket": ticket["ticket_code"],
                    "Tiêu đề": ticket.get("title", ""),
                    "Sinh viên": f"{ticket.get('full_name', '')} ({ticket['student_id']})",
                    "Khóa học": (
                        f"{ticket.get('course_id') or '—'} — {ticket.get('course_title') or 'Chưa gắn khóa học'}"
                    ),
                    "Loại yêu cầu": CATEGORY_LABELS.get(ticket["category"], ticket["category"]),
                    "Ưu tiên": format_priority(ticket["priority"]),
                    "Trạng thái": format_status(ticket["status"]),
                    "Cập nhật": ticket.get("updated_at", ""),
                }
                for ticket in visible_tickets
            ]
            st.dataframe(ticket_table, use_container_width=True, hide_index=True)

            code_to_ticket = {ticket["ticket_code"]: ticket for ticket in visible_tickets}
            selected_code = st.selectbox(
                "Chọn ticket để xem hồ sơ chi tiết",
                list(code_to_ticket),
                format_func=lambda code: (
                    f"{code} · {code_to_ticket[code].get('title', '')}"
                ),
            )
            detail_response = api_get(f"/api/v1/tickets/{selected_code}")
            detail_response.raise_for_status()
            detail_payload = detail_response.json()
            ticket = detail_payload["ticket"]
            events = detail_payload.get("events", [])

            st.divider()
            st.markdown(f"### {ticket.get('title') or ticket['ticket_code']}")
            st.caption(f"Mã ticket: {ticket['ticket_code']}")
            detail_cols = st.columns(4)
            detail_cols[0].metric("Trạng thái", format_status(ticket["status"]))
            detail_cols[1].metric("Ưu tiên", format_priority(ticket["priority"]))
            detail_cols[2].metric("Hạn phản hồi mục tiêu", sla_target(ticket["priority"]).split(" (")[0])
            detail_cols[3].metric("Loại yêu cầu", CATEGORY_LABELS.get(ticket["category"], ticket["category"]))

            info_left, info_right = st.columns(2)
            with info_left:
                st.markdown("#### Thông tin sinh viên")
                st.write(f"**Họ tên:** {ticket.get('full_name')}")
                st.write(f"**Mã sinh viên:** {ticket['student_id']}")
                st.write(f"**Email demo:** {ticket.get('email')}")
                st.write(
                    f"**Khóa học:** {ticket.get('course_id') or 'Chưa xác định'} — "
                    f"{ticket.get('course_title') or 'Chưa gắn khóa học'}"
                )
            with info_right:
                st.markdown("#### Trạng thái dữ liệu liên quan")
                payment_status = ticket.get("payment_status") or "unknown"
                enrollment_status = ticket.get("enrollment_status") or "unknown"
                access_status = ticket.get("access_status") or "unknown"
                st.write(f"**Thanh toán:** {payment_status}")
                st.write(f"**Đăng ký:** {enrollment_status}")
                st.write(f"**Quyền truy cập:** {access_status}")
                st.write(f"**Tạo lúc:** {ticket.get('created_at')}")
                st.write(f"**Cập nhật lúc:** {ticket.get('updated_at')}")

            st.markdown("#### Mô tả sự cố / yêu cầu")
            st.info(ticket.get("summary") or "Chưa có mô tả.")
            st.markdown("#### Hướng xử lý đề xuất")
            st.write(suggested_next_action(ticket))
            st.caption(
                sla_target(ticket["priority"])
                + ". Đây là mục tiêu minh họa của dữ liệu giả lập, không phải cam kết SLA thực tế."
            )

            st.markdown("#### Lịch sử xử lý")
            if events:
                for event in events:
                    previous = event.get("previous_status") or "Khởi tạo"
                    st.markdown(
                        f"- **{event.get('created_at')}** · {event.get('actor')} · "
                        f"{format_status(previous)} → {format_status(event.get('new_status'))}"
                    )
                    st.caption(event.get("note", ""))
            else:
                st.caption("Chưa có sự kiện lịch sử.")

            st.markdown("#### Cập nhật ticket")
            update_cols = st.columns([1, 2, 1])
            current_status = ticket["status"]
            status_order = ["open", "in_progress", "resolved"]
            new_status = update_cols[0].selectbox(
                "Trạng thái mới",
                status_order,
                index=status_order.index(current_status),
                format_func=format_status,
                key=f"status_{selected_code}",
            )
            update_note = update_cols[1].text_input(
                "Ghi chú xử lý",
                placeholder="Ví dụ: Đã kiểm tra log đồng bộ quyền truy cập...",
                key=f"note_{selected_code}",
            )
            update_cols[2].write("")
            update_cols[2].write("")
            if update_cols[2].button("Lưu cập nhật", key=f"save_{selected_code}", use_container_width=True):
                try:
                    update_response = requests.patch(
                        f"{API_BASE}/api/v1/tickets/{selected_code}/status",
                        json={"status": new_status, "note": update_note},
                        timeout=10,
                    )
                    update_response.raise_for_status()
                    st.success("Đã cập nhật ticket và ghi lịch sử xử lý.")
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"Không cập nhật được ticket: {exc}")
        else:
            st.info("Không có ticket khớp bộ lọc.")
    except requests.RequestException as exc:
        st.error(f"Không tải được ticket: {exc}")

with data_tab:
    st.subheader("Dữ liệu giả lập đang được ứng dụng sử dụng")
    st.caption(
        "Đây là dữ liệu seed phục vụ demo, không phải dữ liệu người dùng thật. "
        "Bạn có thể kiểm tra quan hệ giữa sinh viên, khóa học, đăng ký và ticket tại đây."
    )
    try:
        students_response = api_get("/api/v1/students")
        students_response.raise_for_status()
        students = students_response.json().get("students", [])

        courses_response = api_get("/api/v1/courses")
        courses_response.raise_for_status()
        courses = courses_response.json().get("courses", [])

        enrollments_response = api_get("/api/v1/enrollments")
        enrollments_response.raise_for_status()
        enrollments = enrollments_response.json().get("enrollments", [])

        count_cols = st.columns(3)
        count_cols[0].metric("Sinh viên mẫu", len(students))
        count_cols[1].metric("Khóa học mẫu", len(courses))
        count_cols[2].metric("Bản ghi đăng ký", len(enrollments))

        with st.expander("Danh sách sinh viên", expanded=True):
            st.dataframe(students, use_container_width=True, hide_index=True)
        with st.expander("Danh mục khóa học", expanded=True):
            st.dataframe(courses, use_container_width=True, hide_index=True)
        with st.expander("Trạng thái đăng ký / thanh toán / quyền truy cập", expanded=True):
            st.dataframe(enrollments, use_container_width=True, hide_index=True)
    except requests.RequestException as exc:
        st.error(f"Không tải được dữ liệu demo: {exc}")

with documents_tab:
    st.subheader("Knowledge base")
    st.write(
        "Tài liệu mặc định nằm trong data/knowledge_base. Có thể nạp thêm PDF, MD hoặc TXT "
        "(tối đa 10 MB). Những file upload được lưu trong thư mục local data/uploads."
    )
    uploaded_file = st.file_uploader("Chọn tài liệu", type=["pdf", "md", "txt"])
    if uploaded_file is not None and st.button("Tải lên và lập chỉ mục"):
        try:
            response = requests.post(
                f"{API_BASE}/api/v1/documents/upload",
                files={
                    "file": (
                        uploaded_file.name,
                        uploaded_file.getvalue(),
                        uploaded_file.type or "application/octet-stream",
                    )
                },
                timeout=60,
            )
            response.raise_for_status()
            result = response.json()
            st.success(result.get("message", "Uploaded"))
            st.json(result)
        except requests.HTTPError as exc:
            st.error(exc.response.text[:500] if exc.response is not None else str(exc))
        except requests.RequestException as exc:
            st.error(f"Không tải được tài liệu: {exc}")

    try:
        response = api_get("/api/v1/documents")
        response.raise_for_status()
        document_payload = response.json()
        st.metric("Tổng đoạn đã index", document_payload.get("chunks", 0))
        st.write("Tài liệu được tìm thấy:")
        st.write(document_payload.get("documents", []))
    except requests.RequestException as exc:
        st.warning(f"Chưa lấy được danh sách tài liệu: {exc}")

st.divider()
st.caption(
    "Dữ liệu sinh viên, khóa học, ticket và chính sách là dữ liệu giả lập. "
    "Không dùng cho dữ liệu cá nhân hoặc nghiệp vụ thật."
)
